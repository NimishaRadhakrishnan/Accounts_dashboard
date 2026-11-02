"use client";

import { FileDown, Pencil, Send, Trash2, Undo2, XCircle } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { del, openPdf, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { d } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { blankLine, DocForm, fromServer, toPayload } from "@/components/doc-form";
import { Attachments, DocLines, DocMeta, DocTotals, LinkedList, type Doc } from "@/components/doc-view";
import { Button, Card, DocStatus, ErrorBox, Field, Input, LinkButton, Modal, Notice, PageHeader, ReasonModal, Spinner, useConfirm, useToast } from "@/components/ui";

type Invoice = Doc & {
  reference: string | null;
  credit_notes: { id: number; number: string; date: string; grand_total: string; status: string; reason: string }[];
  receipts: { id: number; number: string; date: string; amount: string; status: string }[];
};

export default function InvoicePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { can } = useAuth();
  const toast = useToast();
  const confirm = useConfirm();
  const { data: inv, error, reload } = useApi<Invoice>(`/api/sales-invoices/${id}`);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [cnOpen, setCnOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [cnBusy, setCnBusy] = useState(false);
  const [cnErr, setCnErr] = useState<string | null>(null);
  const [cnReason, setCnReason] = useState("");

  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!inv) return <Spinner />;

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true);
    try { await fn(); toast(ok); reload(); } catch (e) { toast((e as Error).message, "bad"); } finally { setBusy(false); }
  };
  const canEdit = (inv.status === "draft" && can("sales.create")) || (inv.status === "posted" && can("sales.edit_posted") && !inv.is_opening && Number(inv.settled) === 0);

  return (
    <>
      <PageHeader
        title={inv.number ? `Invoice ${inv.number}` : "Unfinished invoice (draft)"}
        subtitle={<span className="inline-flex flex-wrap items-center gap-2"><DocStatus {...inv} /><span>{inv.party.name}</span>{inv.posted_at && <span>· saved on {d(inv.posted_at.slice(0, 10))}</span>}</span>}
        actions={<>
          <Button icon={<FileDown className="h-4 w-4" />} onClick={() => openPdf(`/api/sales-invoices/${inv.id}/pdf`).catch((e) => toast(e.message, "bad"))}>{inv.status === "draft" ? "See how it will print" : "Print / Download PDF"}</Button>
          {canEdit && <LinkButton href={`/sales/${inv.id}/edit`} icon={<Pencil className="h-5 w-5" />}>Change</LinkButton>}
          {inv.status === "draft" && can("sales.create") && <Button variant="danger" busy={busy} icon={<Trash2 className="h-4 w-4" />}
            onClick={async () => { if (await confirm({ title: "Delete this unfinished invoice?", message: "It has no number yet and is not in the accounts, so nothing else changes.", yes: "Yes, delete it", danger: true })) act(async () => { await del(`/api/sales-invoices/${inv.id}`); router.push("/sales"); }, "Unfinished invoice deleted."); }}>Delete</Button>}
          {inv.status === "posted" && !inv.is_opening && can("sales.create") && Number(inv.balance) > 0 &&
            <Button icon={<Undo2 className="h-4 w-4" />} onClick={() => { setCnErr(null); setCnReason(""); setCnOpen(true); }}>Goods returned</Button>}
          {inv.status === "posted" && can("sales.cancel") && <Button variant="danger" icon={<XCircle className="h-4 w-4" />} onClick={() => setCancelOpen(true)}>Cancel this invoice</Button>}
          {inv.status === "draft" && can("sales.post") && <Button variant="primary" busy={busy} icon={<Send className="h-4 w-4" />}
            onClick={async () => { if (await confirm({ title: "Make this invoice final?", message: "It will get its invoice number and be added to the accounts. After this, only the Accounts Manager can change it.", yes: "Yes, save as final" })) act(() => post(`/api/sales-invoices/${inv.id}/post`), "Invoice saved. You can print it now."); }}>Save as final invoice</Button>}
        </>} />

      {inv.status === "cancelled" && <div className="mb-4"><Notice tone="bad">This invoice was cancelled. Reason: {inv.cancel_reason}. Its number is not used again.</Notice></div>}

      <div className="grid gap-6 xl:grid-cols-3">
        <div className="space-y-6 xl:col-span-2">
          {inv.status === "draft" && <Notice tone="warn">This invoice is not final yet. It has no number and is not in the accounts. When it is ready, press “Save as final invoice”.</Notice>}
          <Card><DocMeta doc={inv} partyLabel="Dealer" extra={[["Dealer's order no.", inv.reference || "—"]]} /></Card>
          <Card title="Items" pad={false}><DocLines doc={inv} /></Card>
          {inv.notes && <Card title="Notes"><p className="whitespace-pre-line text-sm text-muted">{inv.notes}</p></Card>}
        </div>
        <div className="space-y-6">
          <Card title="Money"><DocTotals doc={inv} /></Card>
          <LinkedList title="Payments received for this invoice" empty="No payment received yet." rows={inv.receipts.map((r) => ({ ...r }))} />
          <LinkedList title="Goods returned (credit notes)" empty="No returns." rows={inv.credit_notes.map((c) => ({ ...c, amount: c.grand_total, extra: c.reason }))} />
          <Attachments entity="sales_invoice" id={inv.id} canUpload={can("sales.create")} />
          <Link href={`/outstanding/${inv.party.id}`} className="block text-base font-medium text-accent-strong hover:underline">See everything for {inv.party.name} →</Link>
        </div>
      </div>

      <ReasonModal open={cancelOpen} onClose={() => setCancelOpen(false)} title={`Cancel invoice ${inv.number}?`} confirmLabel="Yes, cancel this invoice"
        note="The invoice will be removed from the accounts but kept on record as cancelled. If the dealer has already paid against it, remove that payment first."
        onConfirm={async (reason) => { await post(`/api/sales-invoices/${inv.id}/cancel`, { reason }); toast("Invoice cancelled."); reload(); }} />

      <Modal open={cnOpen} onClose={() => setCnOpen(false)} wide title={`Goods returned — against invoice ${inv.number}`}>
        <div className="space-y-4">
          <Notice>Use this when the dealer returns goods or the price must be reduced. For each item, type how many came back. Press “Remove” on items that were not returned. This makes a credit note.</Notice>
          <Field label="Why were the goods returned?" required>
            <Input value={cnReason} onChange={(e) => setCnReason(e.target.value)} placeholder="For example: damaged in transport" />
          </Field>
          <DocForm kind="sales" note busy={cnBusy} error={cnErr} submitLabels={{ post: "Save return" }}
            initial={{ ...fromServer(inv), lines: inv.lines.length ? fromServer(inv).lines.map((l) => ({ ...l, qty: "" })) : [blankLine()], date: new Date().toISOString().slice(0, 10) }}
            onSubmit={async (doc) => {
              if (cnReason.trim().length < 3) return setCnErr("Please write why the goods came back.");
              setCnBusy(true); setCnErr(null);
              try {
                const p = toPayload(doc);
                await post("/api/credit-notes", { sales_invoice_id: inv.id, date: doc.date, reason: cnReason.trim(), notes: p.notes, lines: p.lines });
                toast("Return saved. The dealer now owes less on this invoice.");
                setCnOpen(false); reload();
              } catch (e) { setCnErr((e as Error).message); } finally { setCnBusy(false); }
            }} />
        </div>
      </Modal>
    </>
  );
}
