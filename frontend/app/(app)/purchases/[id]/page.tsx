"use client";

import { CheckCircle2, Pencil, Trash2, Undo2, XCircle } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { del, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { today } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { DocForm, fromServer, toPayload } from "@/components/doc-form";
import { Attachments, DocLines, DocMeta, DocTotals, LinkedList, type Doc } from "@/components/doc-view";
import { Button, Card, DocStatus, ErrorBox, Field, Input, LinkButton, Modal, Notice, PageHeader, ReasonModal, Spinner, useConfirm, useToast } from "@/components/ui";

type Bill = Doc & {
  supplier_bill_no: string; created_by_id: number; verified_by_id: number | null;
  debit_notes: { id: number; number: string; date: string; grand_total: string; status: string; reason: string }[];
  payments: { id: number; number: string | null; date: string; amount: string; status: string }[];
};

export default function BillPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { me, can } = useAuth();
  const toast = useToast();
  const confirm = useConfirm();
  const { data: bill, error, reload } = useApi<Bill>(`/api/purchase-bills/${id}`);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [dnOpen, setDnOpen] = useState(false);
  const [dnReason, setDnReason] = useState("");
  const [dnBusy, setDnBusy] = useState(false);
  const [dnErr, setDnErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!bill) return <Spinner />;
  const ownBill = bill.created_by_id === me?.id;
  const canEdit = (bill.status === "draft" && can("purchases.create")) || (bill.status === "posted" && can("purchases.edit_posted") && !bill.is_opening && Number(bill.settled) === 0);

  return (
    <>
      <PageHeader title={`Supplier bill ${bill.supplier_bill_no}`} subtitle={<span className="inline-flex flex-wrap items-center gap-2"><DocStatus {...bill} draftLabel="verify" /><span>{bill.party.name}</span>{bill.number && <span>· our number {bill.number}</span>}</span>}
        actions={<>
          {canEdit && <LinkButton href={`/purchases/${bill.id}/edit`} icon={<Pencil className="h-5 w-5" />}>Change</LinkButton>}
          {bill.status === "draft" && can("purchases.create") && <Button variant="danger" icon={<Trash2 className="h-4 w-4" />}
            onClick={async () => { if (!(await confirm({ title: "Delete this bill?", message: "It has not been checked yet, so it is not in the accounts. Nothing else changes.", yes: "Yes, delete it", danger: true }))) return; try { await del(`/api/purchase-bills/${bill.id}`); toast("Bill deleted."); router.push("/purchases"); } catch (e) { toast((e as Error).message, "bad"); } }}>Delete</Button>}
          {bill.status === "posted" && !bill.is_opening && can("purchases.create") && Number(bill.balance) > 0 &&
            <Button icon={<Undo2 className="h-4 w-4" />} onClick={() => { setDnErr(null); setDnReason(""); setDnOpen(true); }}>Goods sent back</Button>}
          {bill.status === "posted" && can("purchases.cancel") && <Button variant="danger" icon={<XCircle className="h-4 w-4" />} onClick={() => setCancelOpen(true)}>Cancel this bill</Button>}
          {bill.status === "draft" && can("purchases.verify") && <Button variant="primary" busy={busy} disabled={ownBill} title={ownBill ? "You entered this bill, so someone else must check it" : undefined}
            icon={<CheckCircle2 className="h-4 w-4" />}
            onClick={async () => { setBusy(true); try { await post(`/api/purchase-bills/${bill.id}/verify`); toast("Bill checked and added to the accounts."); reload(); } catch (e) { toast((e as Error).message, "bad"); } finally { setBusy(false); } }}>
            I have checked it — approve</Button>}
        </>} />

      {bill.status === "draft" && <div className="mb-4"><Notice tone="warn">This bill is waiting to be checked. Compare every figure with the paper bill. If it matches, press “I have checked it — approve”.{ownBill && can("purchases.verify") && " You entered this bill yourself, so another person must check it."}</Notice></div>}
      {bill.status === "cancelled" && <div className="mb-4"><Notice tone="bad">This bill was cancelled. Reason: {bill.cancel_reason}</Notice></div>}

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          <Card><DocMeta doc={bill} partyLabel="Supplier" extra={[["Supplier's bill no.", bill.supplier_bill_no]]} /></Card>
          <Card title="Items" pad={false}><DocLines doc={bill} /></Card>
          {bill.notes && <Card title="Notes"><p className="whitespace-pre-line text-sm text-muted">{bill.notes}</p></Card>}
        </div>
        <div className="space-y-6">
          <Card title="Money"><DocTotals doc={bill} /></Card>
          <LinkedList title="Payments made for this bill" empty="Not paid yet." rows={bill.payments} />
          <LinkedList title="Goods sent back (debit notes)" empty="None." rows={bill.debit_notes.map((n) => ({ ...n, amount: n.grand_total, extra: n.reason }))} />
          <Attachments entity="purchase_bill" id={bill.id} canUpload={can("purchases.create")} />
          <Link href={`/outstanding/${bill.party.id}`} className="block text-base font-medium text-accent-strong hover:underline">See everything for {bill.party.name} →</Link>
        </div>
      </div>

      <ReasonModal open={cancelOpen} onClose={() => setCancelOpen(false)} title={`Cancel bill ${bill.supplier_bill_no}?`} confirmLabel="Yes, cancel this bill"
        note="The bill will be removed from the accounts but kept on record as cancelled."
        onConfirm={async (reason) => { await post(`/api/purchase-bills/${bill.id}/cancel`, { reason }); toast("Bill cancelled."); reload(); }} />

      <Modal open={dnOpen} onClose={() => setDnOpen(false)} wide title={`Goods sent back — against bill ${bill.supplier_bill_no}`}>
        <div className="space-y-4">
          <Notice>Use this when we return goods to the supplier or they reduce the price. For each item, type how many went back. Press “Remove” on the others. This makes a debit note.</Notice>
          <Field label="Why were they sent back?" required><Input value={dnReason} onChange={(e) => setDnReason(e.target.value)} placeholder="e.g. Short supply" /></Field>
          <DocForm kind="purchase" note busy={dnBusy} error={dnErr} submitLabels={{ post: "Save" }}
            initial={{ ...fromServer(bill), date: today(), lines: fromServer(bill).lines.map((l) => ({ ...l, qty: "" })) }}
            onSubmit={async (doc) => {
              if (dnReason.trim().length < 3) return setDnErr("Please write why the goods were sent back.");
              setDnBusy(true); setDnErr(null);
              try {
                const p = toPayload(doc);
                await post("/api/debit-notes", { purchase_bill_id: bill.id, date: doc.date, reason: dnReason.trim(), notes: p.notes, lines: p.lines });
                toast("Saved. We now owe the supplier less on this bill.");
                setDnOpen(false); reload();
              } catch (e) { setDnErr((e as Error).message); } finally { setDnBusy(false); }
            }} />
        </div>
      </Modal>
    </>
  );
}
