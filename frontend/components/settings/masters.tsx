"use client";

import { Plus } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api, post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { GST_RATES, inr, STATES, today } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { invalidateLists, PartyPicker } from "../pickers";
import { Amount, Badge, Button, Card, Checkbox, ErrorBox, Field, Input, Modal, Notice, Select, Spinner, Table, Textarea, useToast } from "../ui";

function useSaver(onSaved: () => void) {
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const save = async (method: "POST" | "PUT", url: string, body: unknown, msg = "Saved.") => {
    setBusy(true); setErr(null);
    try { await api(url, { method, body }); invalidateLists(); toast(msg); onSaved(); return true; }
    catch (e) { setErr((e as Error).message); return false; }
    finally { setBusy(false); }
  };
  return { busy, err, setErr, save };
}

// ---------------- Parties ----------------
type Party = {
  id: number; code: string; name: string; is_customer: boolean; is_supplier: boolean; gstin: string | null; pan: string | null;
  contact_person: string | null; phone: string | null; email: string | null; address: string | null; city: string | null; district: string | null;
  state_code: string; state_name: string; pincode: string | null; payment_term_id: number | null; payment_term: string | null;
  credit_limit: string; tally_ledger_name: string | null; is_active: boolean; notes: string | null; balance: string;
};
type Term = { id: number; name: string; days: number; is_active: boolean };

const blankParty = (): Omit<Party, "id" | "payment_term" | "balance"> => ({
  code: "", name: "", is_customer: true, is_supplier: false, gstin: "", pan: "", contact_person: "", phone: "", email: "", address: "",
  city: "", district: "", state_code: "33", state_name: "Tamil Nadu", pincode: "", payment_term_id: null, credit_limit: "0", tally_ledger_name: "", is_active: true, notes: "",
});

export function PartiesTab() {
  const { can } = useAuth();
  const toast = useToast();
  const [kind, setKind] = useState<"customer" | "supplier">("customer");
  const [q, setQ] = useState("");
  const { data, error, reload } = useApi<Party[]>(`/api/parties?kind=${kind}`);
  const terms = useApi<Term[]>("/api/payment-terms");
  const [edit, setEdit] = useState<(ReturnType<typeof blankParty> & { id?: number }) | null>(null);
  const [opening, setOpening] = useState(false);
  const { busy, err, setErr, save } = useSaver(() => { setEdit(null); reload(); });
  const rows = useMemo(() => (data ?? []).filter((p) => !q || `${p.name} ${p.code} ${p.city} ${p.gstin}`.toLowerCase().includes(q.toLowerCase())), [data, q]);
  const manage = can("masters.manage");
  const nz = (v: string | null | undefined) => (v === "" ? null : v);

  return (
    <Card pad={false}>
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-4 py-3">
        <Select className="w-auto" value={kind} onChange={(e) => setKind(e.target.value as "customer")}><option value="customer">Dealers / customers</option><option value="supplier">Suppliers</option></Select>
        <Input className="w-64" placeholder="Search" value={q} onChange={(e) => setQ(e.target.value)} />
        <span className="text-xs text-muted">{rows.length} shown</span>
        {manage && <div className="ml-auto flex gap-2">
          <Button size="sm" onClick={() => setOpening(true)}>Opening balance</Button>
          <Button size="sm" variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => { setErr(null); setEdit({ ...blankParty(), is_customer: kind === "customer", is_supplier: kind === "supplier" }); }}>Add {kind === "customer" ? "dealer" : "supplier"}</Button>
        </div>}
      </div>
      {error ? <div className="p-4"><ErrorBox message={error} /></div> : !data ? <Spinner /> : (
        <Table<Party> rows={rows} rowKey={(r) => r.id} onRowClick={manage ? (r) => { setErr(null); setEdit({ ...r, gstin: r.gstin ?? "", pan: r.pan ?? "" }); } : undefined} cols={[
          { key: "code", label: "Code", render: (r) => <span className="text-muted">{r.code}</span> },
          { key: "name", label: "Name", render: (r) => <span className="font-medium">{r.name}</span> },
          { key: "place", label: "Place", render: (r) => `${r.city ?? ""}${r.district ? `, ${r.district}` : ""} · ${r.state_name}` },
          { key: "gstin", label: "GSTIN", render: (r) => r.gstin ?? <span className="text-muted">Unregistered</span> },
          { key: "terms", label: "Credit", render: (r) => <span className="text-muted">{r.payment_term ?? "—"}{Number(r.credit_limit) > 0 && ` · ${inr(r.credit_limit)}`}</span> },
          { key: "bal", label: "Balance", align: "right", render: (r) => <Amount value={kind === "supplier" ? -Number(r.balance) : r.balance} /> },
          { key: "st", label: "", render: (r) => !r.is_active && <Badge kind="inactive" /> },
        ]} />
      )}

      <Modal open={!!edit} onClose={() => setEdit(null)} wide title={edit?.id ? `Edit ${edit.name}` : "New party"} footer={edit && <>
        <Button onClick={() => setEdit(null)}>Close</Button>
        <Button variant="primary" busy={busy} disabled={!edit.code || edit.name.length < 2} onClick={() => save(edit.id ? "PUT" : "POST", edit.id ? `/api/parties/${edit.id}` : "/api/parties", {
          ...edit, id: undefined, payment_term: undefined, balance: undefined, credit_days: undefined,
          gstin: nz(edit.gstin?.toUpperCase()), pan: nz(edit.pan?.toUpperCase()), pincode: nz(edit.pincode), email: nz(edit.email), tally_ledger_name: nz(edit.tally_ledger_name),
        })}>Save</Button></>}>
        {edit && (
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Code" required><Input value={edit.code} maxLength={20} onChange={(e) => setEdit({ ...edit, code: e.target.value })} /></Field>
            <Field label="Name" required className="sm:col-span-2"><Input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
            <div className="flex gap-6 sm:col-span-3">
              <Checkbox label="Dealer / customer" checked={edit.is_customer} onChange={(e) => setEdit({ ...edit, is_customer: e.target.checked })} />
              <Checkbox label="Supplier" checked={edit.is_supplier} onChange={(e) => setEdit({ ...edit, is_supplier: e.target.checked })} />
              <Checkbox label="Active" checked={edit.is_active} onChange={(e) => setEdit({ ...edit, is_active: e.target.checked })} />
            </div>
            <Field label="GSTIN" hint="Leave blank if unregistered"><Input value={edit.gstin ?? ""} maxLength={15} onChange={(e) => setEdit({ ...edit, gstin: e.target.value.toUpperCase() })} /></Field>
            <Field label="PAN"><Input value={edit.pan ?? ""} maxLength={10} onChange={(e) => setEdit({ ...edit, pan: e.target.value.toUpperCase() })} /></Field>
            <Field label="State" required hint="Decides CGST+SGST or IGST">
              <Select value={edit.state_code} onChange={(e) => setEdit({ ...edit, state_code: e.target.value, state_name: STATES.find((s) => s.code === e.target.value)?.name ?? "" })}>
                {STATES.map((s) => <option key={s.code} value={s.code}>{s.name} ({s.code})</option>)}
              </Select>
            </Field>
            <Field label="Address" className="sm:col-span-3"><Textarea rows={2} value={edit.address ?? ""} onChange={(e) => setEdit({ ...edit, address: e.target.value })} /></Field>
            <Field label="Town / city"><Input value={edit.city ?? ""} onChange={(e) => setEdit({ ...edit, city: e.target.value })} /></Field>
            <Field label="District"><Input value={edit.district ?? ""} onChange={(e) => setEdit({ ...edit, district: e.target.value })} /></Field>
            <Field label="PIN code"><Input value={edit.pincode ?? ""} maxLength={6} onChange={(e) => setEdit({ ...edit, pincode: e.target.value.replace(/\D/g, "") })} /></Field>
            <Field label="Contact person"><Input value={edit.contact_person ?? ""} onChange={(e) => setEdit({ ...edit, contact_person: e.target.value })} /></Field>
            <Field label="Phone"><Input value={edit.phone ?? ""} onChange={(e) => setEdit({ ...edit, phone: e.target.value })} /></Field>
            <Field label="Email"><Input type="email" value={edit.email ?? ""} onChange={(e) => setEdit({ ...edit, email: e.target.value })} /></Field>
            <Field label="Payment terms">
              <Select value={edit.payment_term_id ?? ""} onChange={(e) => setEdit({ ...edit, payment_term_id: e.target.value ? Number(e.target.value) : null })}>
                <option value="">Immediate</option>{(terms.data ?? []).map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
              </Select>
            </Field>
            <Field label="Credit limit ₹" hint="0 = no limit"><Input type="number" min="0" value={edit.credit_limit} onChange={(e) => setEdit({ ...edit, credit_limit: e.target.value || "0" })} /></Field>
            <Field label="Ledger name in Tally" hint="If different from the name"><Input value={edit.tally_ledger_name ?? ""} onChange={(e) => setEdit({ ...edit, tally_ledger_name: e.target.value })} /></Field>
            <Field label="Notes" className="sm:col-span-3"><Textarea rows={2} value={edit.notes ?? ""} onChange={(e) => setEdit({ ...edit, notes: e.target.value })} /></Field>
            {err && <div className="sm:col-span-3"><Notice tone="bad">{err}</Notice></div>}
          </div>
        )}
      </Modal>
      <OpeningModal open={opening} onClose={() => setOpening(false)} kind={kind} onDone={() => { toast("Opening balance added."); reload(); }} />
    </Card>
  );
}

function OpeningModal({ open, onClose, kind, onDone }: { open: boolean; onClose: () => void; kind: "customer" | "supplier"; onDone: () => void }) {
  const [f, setF] = useState({ party_id: null as number | null, ref_no: "", date: today(), due_date: "", amount: "", notes: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (open) { setF({ party_id: null, ref_no: "", date: today(), due_date: "", amount: "", notes: "" }); setErr(null); } }, [open]);
  return (
    <Modal open={open} onClose={onClose} title={`Opening outstanding — ${kind === "customer" ? "dealer invoice" : "supplier bill"}`} footer={<>
      <Button onClick={onClose}>Close</Button>
      <Button variant="primary" busy={busy} disabled={!f.party_id || !f.ref_no || !(Number(f.amount) > 0)} onClick={async () => {
        setBusy(true); setErr(null);
        try { await post(kind === "customer" ? "/api/sales-invoices/opening" : "/api/purchase-bills/opening", { ...f, due_date: f.due_date || null, notes: f.notes || null }); onDone(); onClose(); }
        catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
      }}>Add</Button></>}>
      <div className="space-y-4">
        <Notice>Use this once at go-live for each unpaid invoice/bill carried from Tally/Excel. It is not exported back to Tally.</Notice>
        <Field label={kind === "customer" ? "Dealer" : "Supplier"} required><PartyPicker kind={kind} value={f.party_id} onChange={(p) => setF({ ...f, party_id: p?.id ?? null })} /></Field>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Original invoice / bill no." required><Input value={f.ref_no} maxLength={40} onChange={(e) => setF({ ...f, ref_no: e.target.value })} /></Field>
          <Field label="Amount still due ₹" required><Input type="number" step="0.01" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Field>
          <Field label="Original date" required><Input type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
          <Field label="Due date"><Input type="date" value={f.due_date} onChange={(e) => setF({ ...f, due_date: e.target.value })} /></Field>
        </div>
        {err && <Notice tone="bad">{err}</Notice>}
      </div>
    </Modal>
  );
}

// ---------------- Products ----------------
type Product = { id: number; code: string; name: string; category: string | null; hsn_code: string | null; unit: string; gst_rate: string; sale_price: string; purchase_price: string; is_active: boolean };
const blankProduct = { code: "", name: "", category: "", hsn_code: "", unit: "Nos", gst_rate: "5", sale_price: "0", purchase_price: "0", is_active: true };

export function ProductsTab() {
  const { can } = useAuth();
  const { data, error, reload } = useApi<Product[]>("/api/products");
  const [edit, setEdit] = useState<(typeof blankProduct & { id?: number }) | null>(null);
  const { busy, err, setErr, save } = useSaver(() => { setEdit(null); reload(); });
  return (
    <Card pad={false} title="Products" actions={can("masters.manage") && <Button size="sm" variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => { setErr(null); setEdit({ ...blankProduct }); }}>Add product</Button>}>
      {error ? <div className="p-4"><ErrorBox message={error} /></div> : !data ? <Spinner /> : (
        <Table<Product> rows={data} rowKey={(r) => r.id} onRowClick={can("masters.manage") ? (r) => { setErr(null); setEdit({ ...r, category: r.category ?? "", hsn_code: r.hsn_code ?? "", gst_rate: String(Number(r.gst_rate)) }); } : undefined} cols={[
          { key: "code", label: "Code", render: (r) => <span className="text-muted">{r.code}</span> },
          { key: "name", label: "Name", render: (r) => <span className="font-medium">{r.name}</span> },
          { key: "cat", label: "Category", render: (r) => r.category },
          { key: "hsn", label: "HSN", render: (r) => r.hsn_code },
          { key: "gst", label: "GST", align: "right", render: (r) => `${Number(r.gst_rate)}%` },
          { key: "price", label: "Sale price", align: "right", render: (r) => <span><Amount value={r.sale_price} /> <span className="text-xs text-muted">/{r.unit}</span></span> },
          { key: "st", label: "", render: (r) => !r.is_active && <Badge kind="inactive" /> },
        ]} />
      )}
      <Modal open={!!edit} onClose={() => setEdit(null)} title={edit?.id ? `Edit ${edit.name}` : "New product"} footer={edit && <>
        <Button onClick={() => setEdit(null)}>Close</Button>
        <Button variant="primary" busy={busy} onClick={() => save(edit.id ? "PUT" : "POST", edit.id ? `/api/products/${edit.id}` : "/api/products", { ...edit, id: undefined, hsn_code: edit.hsn_code || null, category: edit.category || null })}>Save</Button></>}>
        {edit && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Code" required><Input value={edit.code} onChange={(e) => setEdit({ ...edit, code: e.target.value })} /></Field>
            <Field label="Category" hint="e.g. Bio-fertilizer"><Input value={edit.category} onChange={(e) => setEdit({ ...edit, category: e.target.value })} /></Field>
            <Field label="Name" required className="sm:col-span-2"><Input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
            <Field label="HSN code" hint="4–8 digits"><Input value={edit.hsn_code} maxLength={8} onChange={(e) => setEdit({ ...edit, hsn_code: e.target.value.replace(/\D/g, "") })} /></Field>
            <Field label="GST %"><Select value={edit.gst_rate} onChange={(e) => setEdit({ ...edit, gst_rate: e.target.value })}>{GST_RATES.map((g) => <option key={g}>{g}</option>)}</Select></Field>
            <Field label="Unit"><Input value={edit.unit} onChange={(e) => setEdit({ ...edit, unit: e.target.value })} /></Field>
            <Field label="Sale price ₹ (before GST)"><Input type="number" step="0.01" value={edit.sale_price} onChange={(e) => setEdit({ ...edit, sale_price: e.target.value || "0" })} /></Field>
            <Checkbox label="Active" checked={edit.is_active} onChange={(e) => setEdit({ ...edit, is_active: e.target.checked })} />
            {err && <div className="sm:col-span-2"><Notice tone="bad">{err}</Notice></div>}
          </div>
        )}
      </Modal>
    </Card>
  );
}

// ---------------- Banks ----------------
type Bank = { id: number; name: string; kind: "bank" | "cash"; bank_name: string | null; last4: string | null; ifsc: string | null; opening_balance: string; opening_date: string | null; tally_ledger_name: string | null; is_active: boolean; balance: string };
const blankBank = { name: "", kind: "bank" as "bank" | "cash", bank_name: "", last4: "", ifsc: "", opening_balance: "0", opening_date: "", tally_ledger_name: "", is_active: true };

export function BanksTab() {
  const { can } = useAuth();
  const { data, error, reload } = useApi<Bank[]>("/api/bank-accounts");
  const [edit, setEdit] = useState<(typeof blankBank & { id?: number }) | null>(null);
  const { busy, err, setErr, save } = useSaver(() => { setEdit(null); reload(); });
  const nz = (v: string) => (v ? v : null);
  return (
    <Card pad={false} title="Bank accounts & cash" actions={can("masters.manage") && <Button size="sm" variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => { setErr(null); setEdit({ ...blankBank }); }}>Add account</Button>}>
      {error ? <div className="p-4"><ErrorBox message={error} /></div> : !data ? <Spinner /> : (
        <Table<Bank> rows={data} rowKey={(r) => r.id} onRowClick={can("masters.manage") ? (r) => { setErr(null); setEdit({ ...r, bank_name: r.bank_name ?? "", last4: r.last4 ?? "", ifsc: r.ifsc ?? "", opening_date: r.opening_date ?? "", tally_ledger_name: r.tally_ledger_name ?? "" }); } : undefined} cols={[
          { key: "name", label: "Name", render: (r) => <span className="font-medium">{r.name}</span> },
          { key: "kind", label: "Type", render: (r) => r.kind === "cash" ? "Cash" : `${r.bank_name ?? "Bank"}${r.last4 ? ` ••${r.last4}` : ""}` },
          { key: "ob", label: "Opening", align: "right", render: (r) => <Amount value={r.opening_balance} muted /> },
          { key: "bal", label: "Balance now", align: "right", render: (r) => <Amount value={r.balance} strong /> },
          { key: "st", label: "", render: (r) => !r.is_active && <Badge kind="inactive" /> },
        ]} />
      )}
      <Modal open={!!edit} onClose={() => setEdit(null)} title={edit?.id ? `Edit ${edit.name}` : "New account"} footer={edit && <>
        <Button onClick={() => setEdit(null)}>Close</Button>
        <Button variant="primary" busy={busy} onClick={() => save(edit.id ? "PUT" : "POST", edit.id ? `/api/bank-accounts/${edit.id}` : "/api/bank-accounts",
          { ...edit, id: undefined, balance: undefined, bank_name: nz(edit.bank_name), last4: nz(edit.last4), ifsc: nz(edit.ifsc.toUpperCase()), opening_date: nz(edit.opening_date), tally_ledger_name: nz(edit.tally_ledger_name) })}>Save</Button></>}>
        {edit && (
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Display name" required className="sm:col-span-2"><Input value={edit.name} onChange={(e) => setEdit({ ...edit, name: e.target.value })} /></Field>
            <Field label="Type"><Select value={edit.kind} onChange={(e) => setEdit({ ...edit, kind: e.target.value as "bank" })}><option value="bank">Bank account</option><option value="cash">Cash</option></Select></Field>
            {edit.kind === "bank" && <>
              <Field label="Bank name"><Input value={edit.bank_name} onChange={(e) => setEdit({ ...edit, bank_name: e.target.value })} /></Field>
              <Field label="Last 4 digits" hint="Full account numbers are never stored"><Input value={edit.last4} maxLength={4} onChange={(e) => setEdit({ ...edit, last4: e.target.value.replace(/\D/g, "") })} /></Field>
              <Field label="IFSC"><Input value={edit.ifsc} maxLength={11} onChange={(e) => setEdit({ ...edit, ifsc: e.target.value.toUpperCase() })} /></Field>
            </>}
            <Field label="Opening balance ₹"><Input type="number" step="0.01" value={edit.opening_balance} onChange={(e) => setEdit({ ...edit, opening_balance: e.target.value || "0" })} /></Field>
            <Field label="As on date"><Input type="date" value={edit.opening_date} onChange={(e) => setEdit({ ...edit, opening_date: e.target.value })} /></Field>
            <Field label="Ledger name in Tally"><Input value={edit.tally_ledger_name} onChange={(e) => setEdit({ ...edit, tally_ledger_name: e.target.value })} /></Field>
            <Checkbox label="Active" checked={edit.is_active} onChange={(e) => setEdit({ ...edit, is_active: e.target.checked })} />
            {err && <div className="sm:col-span-2"><Notice tone="bad">{err}</Notice></div>}
          </div>
        )}
      </Modal>
    </Card>
  );
}

// ---------------- Categories & terms ----------------
type Cat = { id: number; name: string; is_active: boolean; tally_ledger_name: string | null };

export function CategoriesTermsTab() {
  const { can } = useAuth();
  const cats = useApi<Cat[]>("/api/expense-categories");
  const terms = useApi<Term[]>("/api/payment-terms");
  const [cat, setCat] = useState<{ id?: number; name: string; tally_ledger_name: string; is_active: boolean } | null>(null);
  const [term, setTerm] = useState<{ id?: number; name: string; days: string; is_active: boolean } | null>(null);
  const c = useSaver(() => { setCat(null); cats.reload(); });
  const t = useSaver(() => { setTerm(null); terms.reload(); });
  const manage = can("masters.manage");
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card pad={false} title="Expense categories" actions={manage && <Button size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setCat({ name: "", tally_ledger_name: "", is_active: true })}>Add</Button>}>
        {!cats.data ? <Spinner /> : <Table<Cat> rows={cats.data} rowKey={(r) => r.id} onRowClick={manage ? (r) => setCat({ ...r, tally_ledger_name: r.tally_ledger_name ?? "" }) : undefined} cols={[
          { key: "n", label: "Category", render: (r) => r.name }, { key: "t", label: "Tally ledger", render: (r) => <span className="text-muted">{r.tally_ledger_name}</span> },
          { key: "s", label: "", render: (r) => !r.is_active && <Badge kind="inactive" /> }]} />}
      </Card>
      <Card pad={false} title="Payment terms" actions={manage && <Button size="sm" icon={<Plus className="h-4 w-4" />} onClick={() => setTerm({ name: "", days: "30", is_active: true })}>Add</Button>}>
        {!terms.data ? <Spinner /> : <Table<Term> rows={terms.data} rowKey={(r) => r.id} onRowClick={manage ? (r) => setTerm({ ...r, days: String(r.days) }) : undefined} cols={[
          { key: "n", label: "Name", render: (r) => r.name }, { key: "d", label: "Days", align: "right", render: (r) => r.days },
          { key: "s", label: "", render: (r) => !r.is_active && <Badge kind="inactive" /> }]} />}
      </Card>
      <Modal open={!!cat} onClose={() => setCat(null)} title={cat?.id ? "Edit category" : "New category"} footer={cat && <>
        <Button onClick={() => setCat(null)}>Close</Button>
        <Button variant="primary" busy={c.busy} onClick={() => c.save(cat.id ? "PUT" : "POST", cat.id ? `/api/expense-categories/${cat.id}` : "/api/expense-categories", { name: cat.name, tally_ledger_name: cat.tally_ledger_name || null, is_active: cat.is_active })}>Save</Button></>}>
        {cat && <div className="space-y-4">
          <Field label="Name" required><Input value={cat.name} onChange={(e) => setCat({ ...cat, name: e.target.value })} /></Field>
          <Field label="Ledger name in Tally"><Input value={cat.tally_ledger_name} onChange={(e) => setCat({ ...cat, tally_ledger_name: e.target.value })} /></Field>
          <Checkbox label="Active" checked={cat.is_active} onChange={(e) => setCat({ ...cat, is_active: e.target.checked })} />
          {c.err && <Notice tone="bad">{c.err}</Notice>}
        </div>}
      </Modal>
      <Modal open={!!term} onClose={() => setTerm(null)} title={term?.id ? "Edit term" : "New payment term"} footer={term && <>
        <Button onClick={() => setTerm(null)}>Close</Button>
        <Button variant="primary" busy={t.busy} onClick={() => t.save(term.id ? "PUT" : "POST", term.id ? `/api/payment-terms/${term.id}` : "/api/payment-terms", { name: term.name, days: Number(term.days), is_active: term.is_active })}>Save</Button></>}>
        {term && <div className="space-y-4">
          <Field label="Name" required><Input value={term.name} onChange={(e) => setTerm({ ...term, name: e.target.value })} /></Field>
          <Field label="Credit days" required><Input type="number" min="0" max="365" value={term.days} onChange={(e) => setTerm({ ...term, days: e.target.value })} /></Field>
          <Checkbox label="Active" checked={term.is_active} onChange={(e) => setTerm({ ...term, is_active: e.target.checked })} />
          {t.err && <Notice tone="bad">{t.err}</Notice>}
        </div>}
      </Modal>
    </div>
  );
}
