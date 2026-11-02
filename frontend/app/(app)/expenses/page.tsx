"use client";

import { CheckCircle2, Plus, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { post, qs } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { d, GST_RATES, inr, today } from "@/lib/format";
import { useApi, useDebounced, useQueryParam } from "@/lib/hooks";
import { emptyFilter, ListBar } from "@/components/list-bar";
import { BankSelect, CategorySelect } from "@/components/pickers";
import { Attachments } from "@/components/doc-view";
import { Amount, Badge, Button, Card, Checkbox, cx, ErrorBox, Field, Input, MissingList, Modal, Notice, PageHeader, Pager, ReasonModal, Select, Spinner, Table, Tabs, Textarea, useToast } from "@/components/ui";

type Exp = {
  id: number; number: string | null; date: string; status: string; category: { id: number; name: string }; bank_account: { name: string };
  payee: string; description: string; mode: string; bill_no: string | null; supplier_gstin: string | null; supply_type: string;
  amount: string; gst_rate: string; gst_claimable: boolean; cgst: string; sgst: string; igst: string; total: string;
  created_by_id: number; reject_reason: string | null; cancel_reason: string | null; notes: string | null;
};
type Page<T> = { items: T[]; total: number; page: number; page_size: number };

const PAY_WAYS = [{ value: "cash", label: "Cash" }, { value: "upi", label: "UPI" }, { value: "neft", label: "Bank transfer" }, { value: "cheque", label: "Cheque" }];

function NewExpense({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: (status: string) => void }) {
  const blank = { date: today(), category_id: "" as number | "", bank_account_id: "" as number | "", payee: "", description: "", mode: "cash", bill_no: "", supplier_gstin: "", supply_type: "intra", amount: "", gst_rate: "0", gst_claimable: false, notes: "" };
  const [f, setF] = useState(blank);
  const [tried, setTried] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (open) { setF(blank); setErr(null); setTried(false); } }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  const amt = Number(f.amount) || 0;
  const tax = Math.round(amt * Number(f.gst_rate)) / 100;
  const missing = [
    !f.category_id && "Choose the type of expense",
    f.payee.trim().length < 2 && "Type who was paid",
    f.description.trim().length < 2 && "Type what it was for",
    !(amt > 0) && "Type the amount",
    !f.bank_account_id && "Choose where the money was paid from",
    f.gst_claimable && f.supplier_gstin.length !== 15 && "Type the shop's GSTIN (15 letters/numbers) or untick the GST credit box",
  ].filter(Boolean) as string[];
  return (
    <Modal open={open} onClose={onClose} wide title="Add an expense" footer={<>
      <Button onClick={onClose}>Close without saving</Button>
      <Button variant="primary" size="lg" busy={busy} onClick={async () => {
        setTried(true);
        if (missing.length) return;
        setBusy(true); setErr(null);
        try {
          const r = await post<{ status: string }>("/api/expenses", { ...f, bill_no: f.bill_no || null, supplier_gstin: f.supplier_gstin || null, notes: f.notes || null });
          onDone(r.status); onClose();
        } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
      }}>Save</Button></>}>
      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Type of expense" required><CategorySelect value={f.category_id} onChange={(v) => setF({ ...f, category_id: v })} /></Field>
        <Field label="Date" required><Input type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
        <Field label="Who was paid?" required hint="Shop or person name"><Input value={f.payee} maxLength={200} onChange={(e) => setF({ ...f, payee: e.target.value })} /></Field>
        <Field label="What was it for?" required hint="For example: diesel for delivery van"><Input value={f.description} maxLength={300} onChange={(e) => setF({ ...f, description: e.target.value })} /></Field>
        <Field label="How much? (₹)" required hint={f.gst_rate !== "0" ? "Amount before GST" : "The full amount paid"}>
          <Input type="number" inputMode="decimal" step="0.01" min="0" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} className="min-h-13 text-xl" />
        </Field>
        <Field label="Bill number (if any)"><Input value={f.bill_no} maxLength={40} onChange={(e) => setF({ ...f, bill_no: e.target.value })} /></Field>
        <div className="sm:col-span-2">
          <div className="mb-1.5 text-base font-medium">How was it paid?</div>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" role="radiogroup" aria-label="How was it paid">
            {PAY_WAYS.map((m) => (
              <button key={m.value} type="button" role="radio" aria-checked={f.mode === m.value} onClick={() => setF({ ...f, mode: m.value, bank_account_id: "" })}
                className={cx("min-h-12 rounded-lg border-2 px-3 text-base font-semibold", f.mode === m.value ? "border-sidebar bg-sidebar text-white" : "border-soft bg-white hover:border-accent")}>
                {f.mode === m.value ? "● " : "○ "}{m.label}
              </button>
            ))}
          </div>
        </div>
        <Field label="Paid from" required><BankSelect value={f.bank_account_id} onChange={(v) => setF({ ...f, bank_account_id: v })} kind={f.mode === "cash" ? "cash" : "bank"} /></Field>
        <Field label="Does the bill show GST?" hint="If not sure, leave it at 0%">
          <Select value={f.gst_rate} onChange={(e) => setF({ ...f, gst_rate: e.target.value, gst_claimable: e.target.value === "0" ? false : f.gst_claimable })}>
            {GST_RATES.map((g) => <option key={g} value={g}>{g === "0" ? "No GST (0%)" : `${g}% GST`}</option>)}
          </Select>
        </Field>
        {f.gst_rate !== "0" && <>
          <div className="sm:col-span-2"><Checkbox label="The bill has our company GSTIN — claim the GST back" checked={f.gst_claimable} onChange={(e) => setF({ ...f, gst_claimable: e.target.checked })} /></div>
          {f.gst_claimable && <>
            <Field label="Shop's GSTIN" required><Input value={f.supplier_gstin} maxLength={15} onChange={(e) => setF({ ...f, supplier_gstin: e.target.value.toUpperCase() })} /></Field>
            <Field label="Shop is in"><Select value={f.supply_type} onChange={(e) => setF({ ...f, supply_type: e.target.value })}><option value="intra">Tamil Nadu</option><option value="inter">Another state</option></Select></Field>
          </>}
        </>}
        <Field label="Note (optional)" className="sm:col-span-2"><Textarea rows={2} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} /></Field>
        <div className="flex items-center justify-between rounded-lg bg-sidebar px-4 py-3 text-xl font-semibold text-white sm:col-span-2"><span>Total paid</span><span className="num">{inr(amt + tax)}</span></div>
        <p className="text-sm text-muted sm:col-span-2">After saving, open the expense to add a photo of the bill.</p>
        {tried && <div className="sm:col-span-2"><MissingList items={missing} /></div>}
        {err && <div className="sm:col-span-2"><Notice tone="bad">{err}</Notice></div>}
      </div>
    </Modal>
  );
}

export default function ExpensesPage() {
  const { me, can } = useAuth();
  const toast = useToast();
  const tabParam = useQueryParam("tab");
  const newParam = useQueryParam("new");
  const [newOpen, setNewOpen] = useState(false);
  const [tab, setTab] = useState<"all" | "approval">("all");
  useEffect(() => { if (tabParam === "approval") setTab("approval"); }, [tabParam]);
  useEffect(() => { if (newParam) setNewOpen(true); }, [newParam]);
  const [f, setF] = useState(emptyFilter());
  const [cat, setCat] = useState<number | "">("");
  const [sel, setSel] = useState<Exp | null>(null);
  const [reason, setReason] = useState<{ url: string; title: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const fq = useDebounced(f);
  const status = tab === "approval" ? "pending_approval" : fq.status;
  const { data, error, loading, reload } = useApi<Page<Exp>>("/api/expenses" + qs({ q: fq.q, status, date_from: fq.date_from, date_to: fq.date_to, page: fq.page, category_id: cat }));
  const pending = useApi<Page<Exp>>("/api/expenses?status=pending_approval&page_size=1");
  const refresh = () => { reload(); pending.reload(); };

  return (
    <>
      <PageHeader title="Expenses" subtitle="Daily spending like fuel, rent, travel and office items. Large amounts need a manager to approve."
        actions={can("expenses.create") && <Button variant="primary" icon={<Plus className="h-5 w-5" />} onClick={() => setNewOpen(true)}>Add an expense</Button>} />
      <Tabs value={tab} onChange={(t) => { setTab(t); setF(emptyFilter()); }} items={[{ value: "all", label: "All expenses" }, { value: "approval", label: "Waiting for approval", count: pending.data?.total }]} />
      <Card pad={false}>
        <ListBar f={f} setF={setF} placeholder="Paid to, or what for" statuses={tab === "all" ? [{ value: "posted", label: "Saved" }, { value: "pending_approval", label: "Waiting for approval" }, { value: "rejected", label: "Not approved" }, { value: "cancelled", label: "Cancelled" }] : undefined}>
          <label><span className="mb-1.5 block text-sm font-medium">Type</span><CategorySelect allowAll className="w-auto" value={cat} onChange={(v) => { setCat(v); setF({ ...f, page: 1 }); }} /></label>
        </ListBar>
        {error ? <div className="p-4"><ErrorBox message={error} onRetry={reload} /></div> : loading && !data ? <Spinner /> : data && (
          <>
            <Table<Exp> rows={data.items} rowKey={(r) => r.id} onRowClick={setSel} empty={tab === "approval" ? "Nothing is waiting for approval." : "No expenses found."} cols={[
              { key: "no", label: "Number", render: (r) => <span className="font-medium">{r.number ?? <span className="text-muted">—</span>}</span> },
              { key: "date", label: "Date", render: (r) => d(r.date) },
              { key: "cat", label: "Type", render: (r) => r.category.name },
              { key: "payee", label: "Paid to", render: (r) => <span>{r.payee}<span className="block max-w-xs truncate text-sm text-muted">{r.description}</span></span> },
              { key: "from", label: "Paid from", render: (r) => <span className="text-muted">{r.bank_account.name}</span> },
              { key: "total", label: "Amount", align: "right", render: (r) => <Amount value={r.total} strong /> },
              { key: "st", label: "Status", render: (r) => <Badge kind={r.status} /> },
            ]} />
            <Pager page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => setF({ ...f, page: p })} />
          </>
        )}
      </Card>

      <NewExpense open={newOpen} onClose={() => setNewOpen(false)} onDone={(st) => { toast(st === "posted" ? "Expense saved." : "Expense saved. It is large, so it now waits for a manager to approve."); refresh(); }} />

      <Modal open={!!sel} onClose={() => setSel(null)} wide title={sel ? `Expense ${sel.number ?? "(waiting for approval)"}` : ""} footer={sel && <>
        {sel.status === "posted" && can("expenses.cancel") && <Button variant="danger" icon={<XCircle className="h-4 w-4" />} onClick={() => setReason({ url: `/api/expenses/${sel.id}/cancel`, title: "Cancel this expense?" })}>Cancel this expense</Button>}
        {sel.status === "pending_approval" && can("expenses.approve") && <>
          <Button variant="danger" onClick={() => setReason({ url: `/api/expenses/${sel.id}/reject`, title: "Do not approve this expense?" })}>Do not approve</Button>
          <Button variant="primary" busy={busy} disabled={sel.created_by_id === me?.id} title={sel.created_by_id === me?.id ? "You entered this, so someone else must approve it" : undefined} icon={<CheckCircle2 className="h-4 w-4" />}
            onClick={async () => { setBusy(true); try { await post(`/api/expenses/${sel.id}/approve`); toast("Expense approved."); setSel(null); refresh(); } catch (e) { toast((e as Error).message, "bad"); } finally { setBusy(false); } }}>Approve expense</Button>
        </>}
      </>}>
        {sel && (
          <div className="space-y-4 text-base">
            {sel.reject_reason && <Notice tone="bad">Not approved. Reason: {sel.reject_reason}</Notice>}
            {sel.cancel_reason && <Notice tone="bad">Cancelled. Reason: {sel.cancel_reason}</Notice>}
            <dl className="grid gap-3 sm:grid-cols-3">
              {[["Date", d(sel.date)], ["Type", sel.category.name], ["Paid to", sel.payee], ["What for", sel.description], ["Bill no.", sel.bill_no || "—"], ["Paid from", sel.bank_account.name],
                ["Amount", inr(sel.amount)], ["GST", `${Number(sel.gst_rate)}% · ${inr(Number(sel.cgst) + Number(sel.sgst) + Number(sel.igst))}${sel.gst_claimable ? " (credit claimed)" : ""}`], ["Total", inr(sel.total)]]
                .map(([k, v]) => <div key={k}><dt className="text-sm text-muted">{k}</dt><dd className="font-medium">{v}</dd></div>)}
            </dl>
            {sel.notes && <p className="text-muted">{sel.notes}</p>}
            <Attachments entity="expense" id={sel.id} canUpload={can("expenses.create")} />
          </div>
        )}
      </Modal>

      <ReasonModal open={!!reason} onClose={() => setReason(null)} title={reason?.title ?? ""} confirmLabel="Confirm"
        onConfirm={async (r) => { await post(reason!.url, { reason: r }); toast("Done."); setSel(null); refresh(); }} />
    </>
  );
}
