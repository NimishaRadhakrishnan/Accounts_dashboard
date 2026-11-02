"use client";

import { ArrowDownLeft, ArrowLeftRight, ArrowUpRight, CheckCircle2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { get, post, qs } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { d, inr, MODES } from "@/lib/format";
import { useApi, useDebounced, useQueryParam } from "@/lib/hooks";
import { emptyFilter, ListBar } from "@/components/list-bar";
import { AllocGrid, MoneyModal, TransferModal, type OpenItem } from "@/components/money-form";
import { Amount, Badge, Button, Card, ErrorBox, Modal, Notice, PageHeader, Pager, ReasonModal, Spinner, Table, Tabs, useToast } from "@/components/ui";

type MoneyV = {
  id: number; number: string | null; date: string; status: string; party: { id: number; name: string }; bank_account: { name: string };
  amount: string; mode: string; reference: string | null; allocations: { doc_id: number; number: string; date: string; amount: string }[];
  allocated: string; unallocated: string; notes: string | null; cancel_reason: string | null; created_by_id: number;
};
type Contra = { id: number; number: string; date: string; status: string; from_account: { name: string }; to_account: { name: string }; amount: string; reference: string | null };
type Page<T> = { items: T[]; total: number; page: number; page_size: number };
type TabT = "receipts" | "payments" | "transfers";

const modeLabel = (m: string) => MODES.find((x) => x.value === m)?.label ?? m;

export default function PaymentsPage() {
  const { me, can } = useAuth();
  const toast = useToast();
  const tabParam = useQueryParam("tab");
  const newParam = useQueryParam("new");
  const [tab, setTab] = useState<TabT>("receipts");
  const [f, setF] = useState(emptyFilter());
  const [modal, setModal] = useState<"receipt" | "payment" | "transfer" | null>(null);
  const [sel, setSel] = useState<MoneyV | null>(null);
  const [cancel, setCancel] = useState<{ url: string; title: string } | null>(null);
  const [allocOpen, setAllocOpen] = useState(false);
  const [openItems, setOpenItems] = useState<OpenItem[]>([]);
  const [alloc, setAlloc] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (tabParam === "payments" || tabParam === "transfers") setTab(tabParam); }, [tabParam]);
  useEffect(() => { if (newParam === "receipt" || newParam === "payment") setModal(newParam); }, [newParam]);

  const fq = useDebounced(f);
  const path = { receipts: "/api/receipts", payments: "/api/payments", transfers: "/api/contra" }[tab];
  const { data, error, loading, reload } = useApi<Page<MoneyV & Contra>>(path + qs({ q: fq.q, status: fq.status, date_from: fq.date_from, date_to: fq.date_to, page: fq.page }));
  const pending = useApi<Page<MoneyV>>(can("payments.view") ? "/api/payments?status=pending_approval&page_size=1" : null);

  const isR = tab === "receipts";
  const refresh = () => { reload(); pending.reload(); };

  async function act(url: string, ok: string) {
    setBusy(true);
    try { await post(url); toast(ok); setSel(null); refresh(); } catch (e) { toast((e as Error).message, "bad"); } finally { setBusy(false); }
  }

  async function openAlloc(v: MoneyV) {
    setAlloc({});
    setOpenItems(await get<OpenItem[]>(`/api/parties/${v.party.id}/${isR ? "open-invoices" : "open-bills"}`));
    setAllocOpen(true);
  }

  return (
    <>
      <PageHeader title="Payments & Receipts" subtitle="Money that came in from dealers, money we paid to suppliers, and cash moved to or from the bank."
        actions={<>
          {can("contra.create") && <Button icon={<ArrowLeftRight className="h-5 w-5" />} onClick={() => setModal("transfer")}>Move cash ↔ bank</Button>}
          {can("payments.create") && <Button icon={<ArrowUpRight className="h-5 w-5" />} onClick={() => setModal("payment")}>We paid a supplier</Button>}
          {can("receipts.create") && <Button variant="primary" icon={<ArrowDownLeft className="h-5 w-5" />} onClick={() => setModal("receipt")}>A dealer paid us</Button>}
        </>} />
      <Tabs value={tab} onChange={(t) => { setTab(t); setF(emptyFilter()); }} items={[
        { value: "receipts", label: "Money received" },
        { value: "payments", label: "Money paid", count: pending.data?.total },
        { value: "transfers", label: "Cash ↔ Bank" },
      ]} />
      <Card pad={false}>
        <ListBar f={f} setF={setF} placeholder="Name, number or UTR" statuses={tab === "payments"
          ? [{ value: "pending_approval", label: "Waiting for approval" }, { value: "posted", label: "Saved" }, { value: "rejected", label: "Rejected" }, { value: "cancelled", label: "Cancelled" }]
          : [{ value: "posted", label: "Saved" }, { value: "cancelled", label: "Cancelled" }]} />
        {error ? <div className="p-4"><ErrorBox message={error} onRetry={reload} /></div> : loading && !data ? <Spinner /> : data && (
          <>
            {tab === "transfers" ? (
              <Table<Contra> rows={data.items} rowKey={(r) => r.id} empty="No cash or bank transfers yet." cols={[
                { key: "no", label: "No", render: (r) => <span className="font-medium">{r.number}</span> },
                { key: "date", label: "Date", render: (r) => d(r.date) },
                { key: "from", label: "From", render: (r) => r.from_account.name },
                { key: "to", label: "To", render: (r) => r.to_account.name },
                { key: "ref", label: "Note", render: (r) => <span className="text-muted">{r.reference}</span> },
                { key: "amt", label: "Amount", align: "right", render: (r) => <Amount value={r.amount} /> },
                { key: "st", label: "", render: (r) => r.status === "posted" && can("payments.cancel")
                  ? <Button size="sm" variant="danger" onClick={(e) => { e.stopPropagation(); setCancel({ url: `/api/contra/${r.id}/cancel`, title: `Cancel transfer ${r.number}?` }); }}>Cancel this</Button>
                  : <Badge kind={r.status} /> },
              ]} />
            ) : (
              <Table<MoneyV> rows={data.items} rowKey={(r) => r.id} onRowClick={setSel} empty={isR ? "No money received yet." : "No payments yet."} cols={[
                { key: "no", label: "Number", render: (r) => <span className="font-medium">{r.number ?? <span className="text-muted">Not yet</span>}</span> },
                { key: "date", label: "Date", render: (r) => d(r.date) },
                { key: "party", label: isR ? "Dealer" : "Supplier", render: (r) => r.party.name },
                { key: "mode", label: "How", render: (r) => <span className="text-muted">{modeLabel(r.mode)} · {r.bank_account.name}</span> },
                { key: "amt", label: "Amount", align: "right", render: (r) => <Amount value={r.amount} strong /> },
                { key: "adv", label: "Advance (not linked)", align: "right", render: (r) => Number(r.unallocated) > 0 && r.status === "posted" ? <span className="num text-warn">{inr(r.unallocated)}</span> : "" },
                { key: "st", label: "Status", render: (r) => <Badge kind={r.status} /> },
              ]} />
            )}
            <Pager page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => setF({ ...f, page: p })} />
          </>
        )}
      </Card>

      <MoneyModal kind="receipt" open={modal === "receipt"} onClose={() => setModal(null)} onDone={() => { toast("Money received is saved."); if (tab === "receipts") refresh(); else setTab("receipts"); }} />
      <MoneyModal kind="payment" open={modal === "payment"} onClose={() => setModal(null)} onDone={() => { toast("Payment is saved."); if (tab === "payments") refresh(); else setTab("payments"); }} />
      <TransferModal open={modal === "transfer"} onClose={() => setModal(null)} onDone={() => { toast("Transfer is saved."); if (tab === "transfers") refresh(); else setTab("transfers"); }} />

      <Modal open={!!sel} onClose={() => setSel(null)} title={sel ? `${isR ? "Money received" : "Money paid"} ${sel.number ?? "(waiting for approval)"}` : ""}
        footer={sel && <>
          {sel.status === "posted" && Number(sel.unallocated) > 0 && can(isR ? "receipts.create" : "payments.create") && <Button onClick={() => openAlloc(sel)}>Link advance to bills</Button>}
          {sel.status === "posted" && can(isR ? "receipts.cancel" : "payments.cancel") && <Button variant="danger" icon={<XCircle className="h-4 w-4" />}
            onClick={() => setCancel({ url: `/api/${isR ? "receipts" : "payments"}/${sel.id}/cancel`, title: `Cancel ${sel.number}?` })}>Cancel this entry</Button>}
          {sel.status === "pending_approval" && can("payments.approve") && <>
            <Button variant="danger" onClick={() => setCancel({ url: `/api/payments/${sel.id}/reject`, title: "Do not approve this payment?" })}>Do not approve</Button>
            <Button variant="primary" busy={busy} disabled={sel.created_by_id === me?.id} title={sel.created_by_id === me?.id ? "You entered this, so someone else must approve it" : undefined}
              icon={<CheckCircle2 className="h-4 w-4" />} onClick={() => act(`/api/payments/${sel.id}/approve`, "Payment approved and saved.")}>Approve payment</Button>
          </>}
        </>}>
        {sel && (
          <div className="space-y-4 text-base">
            {sel.status === "pending_approval" && <Notice tone="warn">This payment is large, so a manager must approve it. Until then it is not in the accounts.</Notice>}
            {sel.cancel_reason && <Notice tone="bad">{sel.status === "rejected" ? "Not approved" : "Cancelled"}. Reason: {sel.cancel_reason}</Notice>}
            <dl className="grid grid-cols-2 gap-3">
              <div><dt className="text-sm text-muted">{isR ? "Dealer" : "Supplier"}</dt><dd className="font-medium">{sel.party.name}</dd></div>
              <div><dt className="text-sm text-muted">Date</dt><dd className="font-medium">{d(sel.date)}</dd></div>
              <div><dt className="text-sm text-muted">Amount</dt><dd className="num font-semibold">{inr(sel.amount)}</dd></div>
              <div><dt className="text-sm text-muted">How</dt><dd>{modeLabel(sel.mode)} · {sel.bank_account.name}</dd></div>
              <div className="col-span-2"><dt className="text-sm text-muted">UTR / cheque no.</dt><dd>{sel.reference || "—"}</dd></div>
            </dl>
            <div>
              <h4 className="mb-1.5 text-base font-semibold">This money was for</h4>
              {sel.allocations.length ? (
                <ul className="divide-y divide-line rounded-lg border border-line">
                  {sel.allocations.map((a) => <li key={a.doc_id} className="flex justify-between px-3 py-2"><span>{a.number} <span className="text-muted">· {d(a.date)}</span></span><span className="num">{inr(a.amount)}</span></li>)}
                </ul>
              ) : <p className="text-muted">Not linked to any {isR ? "invoice" : "bill"} yet.</p>}
              {Number(sel.unallocated) > 0 && <p className="mt-2 font-medium text-warn">Advance (not linked to any {isR ? "invoice" : "bill"}): {inr(sel.unallocated)}</p>}
            </div>
            {sel.notes && <p className="whitespace-pre-line text-muted">{sel.notes}</p>}
          </div>
        )}
      </Modal>

      <Modal open={allocOpen} onClose={() => setAllocOpen(false)} wide title="Link the advance to unpaid bills"
        footer={sel && <><Button onClick={() => setAllocOpen(false)}>Close</Button>
          <Button variant="primary" busy={busy} onClick={async () => {
            setBusy(true);
            try {
              const allocations = Object.entries(alloc).filter(([, v]) => Number(v) > 0).map(([k, v]) => ({ doc_id: Number(k), amount: v }));
              await post(`/api/${isR ? "receipts" : "payments"}/${sel.id}/allocate`, { allocations });
              toast("Linked."); setAllocOpen(false); setSel(null); refresh();
            } catch (e) { toast((e as Error).message, "bad"); } finally { setBusy(false); }
          }}>Save</Button></>}>
        {sel && <AllocGrid items={openItems} alloc={alloc} setAlloc={setAlloc} amount={Number(sel.unallocated)} />}
      </Modal>

      <ReasonModal open={!!cancel} onClose={() => setCancel(null)} title={cancel?.title ?? ""} confirmLabel="Confirm"
        note="This entry will be removed from the accounts. Any invoices or bills it paid will show as unpaid again."
        onConfirm={async (reason) => { await post(cancel!.url, { reason }); toast("Done."); setSel(null); refresh(); }} />
    </>
  );
}
