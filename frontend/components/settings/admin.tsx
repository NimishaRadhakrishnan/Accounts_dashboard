"use client";

import { Lock, Plus, Unlock, Upload } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { api, del, post, put, qs } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { d, dt, STATES } from "@/lib/format";
import { useApi, useDebounced } from "@/lib/hooks";
import { Badge, Button, Card, Checkbox, ErrorBox, Field, Input, Modal, Notice, Pager, Select, Spinner, Table, Textarea, useConfirm, useToast } from "../ui";

// ---------------- Company ----------------
type Company = Record<string, string | boolean | null> & { is_sample_data: boolean };

export function CompanyTab() {
  const { can } = useAuth();
  const toast = useToast();
  const { data, reload } = useApi<Company | null>("/api/company");
  const [f, setF] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [logoKey, setLogoKey] = useState(0);
  const logoRef = useRef<HTMLInputElement>(null);
  const manage = can("settings.manage");
  const keys = ["legal_name", "trade_name", "gstin", "pan", "cin", "address", "city", "state_code", "state_name", "pincode", "phone", "email", "bank_details_for_invoice", "signatory_name", "signatory_designation", "invoice_terms"];
  useEffect(() => { if (data) setF(Object.fromEntries(keys.map((k) => [k, (data[k] as string) ?? ""]))); }, [data]); // eslint-disable-line react-hooks/exhaustive-deps
  if (!data) return <Spinner />;
  const inp = (k: string, label: string, extra: Partial<React.ComponentProps<typeof Input>> = {}, cls = "") => (
    <Field label={label} className={cls}><Input disabled={!manage} value={f[k] ?? ""} onChange={(e) => setF({ ...f, [k]: e.target.value })} {...extra} /></Field>
  );
  return (
    <div className="space-y-6">
      {data.is_sample_data && <Notice tone="warn">These are SAMPLE company details. Replace them with the confirmed details before printing real invoices (checklist items C1–C3).</Notice>}
      <Card title="Company profile (printed on invoices)">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {inp("legal_name", "Legal name", {}, "lg:col-span-2")}{inp("trade_name", "Trade name")}
          {inp("gstin", "GSTIN", { maxLength: 15 })}{inp("pan", "PAN", { maxLength: 10 })}{inp("cin", "CIN")}
          <Field label="Address" className="sm:col-span-2 lg:col-span-3"><Textarea disabled={!manage} rows={2} value={f.address ?? ""} onChange={(e) => setF({ ...f, address: e.target.value })} /></Field>
          {inp("city", "City")}
          <Field label="State"><Select disabled={!manage} value={f.state_code} onChange={(e) => setF({ ...f, state_code: e.target.value, state_name: STATES.find((s) => s.code === e.target.value)?.name ?? "" })}>
            {STATES.map((s) => <option key={s.code} value={s.code}>{s.name} ({s.code})</option>)}</Select></Field>
          {inp("pincode", "PIN code", { maxLength: 6 })}{inp("phone", "Phone")}{inp("email", "Email")}
          {inp("signatory_name", "Authorised signatory")}{inp("signatory_designation", "Designation")}
          <Field label="Bank details printed on invoice" className="sm:col-span-2 lg:col-span-3"><Textarea disabled={!manage} rows={2} value={f.bank_details_for_invoice ?? ""} onChange={(e) => setF({ ...f, bank_details_for_invoice: e.target.value })} /></Field>
          <Field label="Invoice terms" className="sm:col-span-2 lg:col-span-3"><Textarea disabled={!manage} rows={3} value={f.invoice_terms ?? ""} onChange={(e) => setF({ ...f, invoice_terms: e.target.value })} /></Field>
        </div>
        {err && <div className="mt-4"><Notice tone="bad">{err}</Notice></div>}
        {manage && <div className="mt-5 flex justify-end"><Button variant="primary" busy={busy} onClick={async () => {
          setBusy(true); setErr(null);
          const body = Object.fromEntries(Object.entries(f).map(([k, v]) => [k, v === "" && !["legal_name", "state_code", "state_name"].includes(k) ? null : v]));
          try { await put("/api/company", body); toast("Company profile saved."); reload(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
        }}>Save profile</Button></div>}
      </Card>
      <Card title="Logo" actions={manage && <>
        <input ref={logoRef} type="file" accept="image/png,image/jpeg" className="hidden" onChange={async (e) => {
          const file = e.target.files?.[0]; if (!file) return;
          const fd = new FormData(); fd.append("file", file);
          try { await api("/api/company/logo", { method: "POST", form: fd }); toast("Logo uploaded."); setLogoKey((k) => k + 1); } catch (x) { toast((x as Error).message, "bad"); }
          e.target.value = "";
        }} />
        <Button size="sm" icon={<Upload className="h-3.5 w-3.5" />} onClick={() => logoRef.current?.click()}>Upload PNG/JPG</Button></>}>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img key={logoKey} src={`/api/company/logo?v=${logoKey}`} alt="Company logo" className="h-20 w-auto rounded border border-line bg-white object-contain p-2"
          onError={(e) => ((e.target as HTMLImageElement).style.display = "none")} />
        <p className="mt-2 text-xs text-muted">Printed on the top-left of every invoice. Square PNG with transparent background works best.</p>
      </Card>
    </div>
  );
}

// ---------------- Numbering, periods, limits ----------------
type Series = { id: number; doc_type: string; fy_label: string; prefix: string; next_number: number; preview: string };
type LockT = { id: number; year: number; month: number; locked_at: string };
type Setting = { key: string; value: string; description: string };
const DOC_NAMES: Record<string, string> = { sales_invoice: "Sales invoice", credit_note: "Credit note", purchase_bill: "Purchase bill (our ref.)", debit_note: "Debit note", receipt: "Receipt", payment: "Payment", expense: "Expense", contra: "Transfer" };
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function ControlsTab() {
  const { can } = useAuth();
  const toast = useToast();
  const confirm = useConfirm();
  const series = useApi<Series[]>(can("settings.manage") ? "/api/number-series" : null);
  const locks = useApi<LockT[]>("/api/period-locks");
  const settings = useApi<Setting[]>("/api/settings");
  const [edit, setEdit] = useState<Series | null>(null);
  const [lockYM, setLockYM] = useState(() => { const t = new Date(); t.setMonth(t.getMonth() - 1); return `${t.getFullYear()}-${String(t.getMonth() + 1).padStart(2, "0")}`; });
  const [vals, setVals] = useState<Record<string, string>>({});
  useEffect(() => { if (settings.data) setVals(Object.fromEntries(settings.data.map((s) => [s.key, s.value]))); }, [settings.data]);
  const run = async (fn: () => Promise<unknown>, ok: string, after: () => void) => { try { await fn(); toast(ok); after(); } catch (e) { toast((e as Error).message, "bad"); } };

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card title="Approval rules">
        <div className="space-y-4">
          {[["expense_approval_limit", "Expenses above ₹ need approval"], ["payment_approval_limit", "Supplier payments above ₹ need approval"]].map(([k, label]) => (
            <div key={k} className="flex items-end gap-2">
              <Field label={label} className="flex-1"><Input type="number" min="0" disabled={!can("settings.manage")} value={vals[k] ?? ""} onChange={(e) => setVals({ ...vals, [k]: e.target.value })} /></Field>
              {can("settings.manage") && <Button onClick={() => run(() => put(`/api/settings/${k}`, { value: vals[k] }), "Saved.", settings.reload)}>Save</Button>}
            </div>
          ))}
          <Checkbox label="Purchase bills must be verified by a different person (maker-checker)" disabled={!can("settings.manage")} checked={vals.purchase_maker_checker === "true"}
            onChange={(e) => run(() => put("/api/settings/purchase_maker_checker", { value: e.target.checked ? "true" : "false" }), "Saved.", settings.reload)} />
        </div>
      </Card>

      <Card title="Lock closed months" pad={false}>
        <div className="p-5">
          <p className="text-sm text-muted">After a month is checked and reported, lock it so no one can add, edit or cancel entries dated in it.</p>
          {can("periods.lock") && <div className="mt-3 flex gap-2">
            <Input type="month" className="w-auto" value={lockYM} onChange={(e) => setLockYM(e.target.value)} />
            <Button icon={<Lock className="h-4 w-4" />} onClick={() => { const [y, m] = lockYM.split("-").map(Number); run(() => post("/api/period-locks", { year: y, month: m }), "Month locked.", locks.reload); }}>Lock month</Button>
          </div>}
        </div>
        {locks.data && <Table<LockT> rows={locks.data} rowKey={(r) => r.id} empty="No months locked." cols={[
          { key: "m", label: "Month", render: (r) => <span className="font-medium">{MONTHS[r.month - 1]} {r.year}</span> },
          { key: "at", label: "Locked on", render: (r) => <span className="text-muted">{dt(r.locked_at)}</span> },
          { key: "u", label: "", align: "right", render: (r) => can("periods.lock") && <Button size="sm" variant="ghost" icon={<Unlock className="h-3.5 w-3.5" />}
            onClick={async () => { if (await confirm({ title: `Unlock ${MONTHS[r.month - 1]} ${r.year}?`, message: "Entries dated in that month can then be added, changed or cancelled again.", yes: "Yes, unlock" })) run(() => del(`/api/period-locks/${r.id}`), "Month unlocked.", locks.reload); }}>Unlock</Button> },
        ]} />}
      </Card>

      {can("settings.manage") && (
        <Card title="Document numbering (this financial year)" pad={false} className="lg:col-span-2">
          {series.error ? <div className="p-4"><ErrorBox message={series.error} /></div> : !series.data ? <Spinner /> : (
            <Table<Series> rows={series.data} rowKey={(r) => r.id} onRowClick={setEdit} cols={[
              { key: "t", label: "Document", render: (r) => DOC_NAMES[r.doc_type] ?? r.doc_type },
              { key: "p", label: "Prefix", render: (r) => r.prefix },
              { key: "n", label: "Next number", render: (r) => <span className="font-mono text-sm">{r.preview}</span> },
            ]} />
          )}
          <p className="px-5 pb-4 text-xs text-muted">GST rules: invoice numbers must be unique for the year, in order, and at most 16 characters. Prefixes can be changed only before the first number is used.</p>
        </Card>
      )}
      <Modal open={!!edit} onClose={() => setEdit(null)} title={`Numbering — ${edit ? DOC_NAMES[edit.doc_type] : ""}`} footer={edit && <>
        <Button onClick={() => setEdit(null)}>Close</Button>
        <Button variant="primary" onClick={() => run(() => put(`/api/number-series/${edit.id}`, { prefix: edit.prefix, next_number: edit.next_number }), "Numbering saved.", () => { setEdit(null); series.reload(); })}>Save</Button></>}>
        {edit && <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Prefix" hint="Capital letters / digits"><Input value={edit.prefix} maxLength={6} onChange={(e) => setEdit({ ...edit, prefix: e.target.value.toUpperCase() })} /></Field>
          <Field label="Next number" hint="e.g. continue from Tally"><Input type="number" min="1" value={edit.next_number} onChange={(e) => setEdit({ ...edit, next_number: Number(e.target.value) })} /></Field>
          <p className="text-sm text-muted sm:col-span-2">Next will be <span className="font-mono text-ink">{edit.prefix}/{edit.fy_label}/{String(edit.next_number).padStart(4, "0")}</span></p>
        </div>}
      </Modal>
    </div>
  );
}

// ---------------- Users & roles ----------------
type U = { id: number; full_name: string; username: string; email: string | null; role: { code: string; name: string }; is_active: boolean; must_change_password: boolean; last_login_at: string | null; locked: boolean };
type Roles = { permissions: { code: string; label: string; group: string }[]; roles: { code: string; name: string; description: string; users: number; permissions: string[] }[] };

export function UsersTab() {
  const { me } = useAuth();
  const toast = useToast();
  const users = useApi<U[]>("/api/users");
  const roles = useApi<Roles>("/api/roles");
  const [edit, setEdit] = useState<{ id?: number; full_name: string; username: string; email: string; role_code: string; is_active: boolean; temp_password: string } | null>(null);
  const [reset, setReset] = useState<U | null>(null);
  const [temp, setTemp] = useState("");
  const [roleEdit, setRoleEdit] = useState<{ code: string; name: string; permissions: string[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const saveUser = async () => {
    if (!edit) return;
    setBusy(true); setErr(null);
    try {
      if (edit.id) await put(`/api/users/${edit.id}`, { full_name: edit.full_name, email: edit.email || null, role_code: edit.role_code, is_active: edit.is_active });
      else await post("/api/users", { full_name: edit.full_name, username: edit.username, email: edit.email || null, role_code: edit.role_code, temp_password: edit.temp_password });
      toast(edit.id ? "User updated." : "User created. Share the temporary password privately."); setEdit(null); users.reload(); roles.reload();
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };

  const groups = roles.data ? Array.from(new Set(roles.data.permissions.map((p) => p.group))) : [];

  return (
    <div className="space-y-6">
      <Card pad={false} title="Users" actions={<Button size="sm" variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => { setErr(null); setEdit({ full_name: "", username: "", email: "", role_code: "accountant", is_active: true, temp_password: "" }); }}>Add user</Button>}>
        {!users.data ? <Spinner /> : <Table<U> rows={users.data} rowKey={(r) => r.id} onRowClick={(r) => { setErr(null); setEdit({ id: r.id, full_name: r.full_name, username: r.username, email: r.email ?? "", role_code: r.role.code, is_active: r.is_active, temp_password: "" }); }} cols={[
          { key: "n", label: "Name", render: (r) => <span><span className="font-medium">{r.full_name}</span><span className="block text-xs text-muted">{r.username}</span></span> },
          { key: "r", label: "Role", render: (r) => r.role.name },
          { key: "l", label: "Last sign-in", render: (r) => <span className="text-muted">{r.last_login_at ? dt(r.last_login_at) : "Never"}</span> },
          { key: "s", label: "Status", render: (r) => <span className="flex gap-1">{r.is_active ? <Badge kind="active" /> : <Badge kind="inactive" />}{r.locked && <Badge kind="locked">Locked out</Badge>}{r.must_change_password && <Badge kind="pending_approval">Temp password</Badge>}</span> },
          { key: "a", label: "", align: "right", render: (r) => <Button size="sm" variant="ghost" onClick={(e) => { e.stopPropagation(); setTemp(""); setErr(null); setReset(r); }}>Reset password</Button> },
        ]} />}
      </Card>

      <Card pad={false} title="Roles & permissions">
        {!roles.data ? <Spinner /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead><tr className="border-b border-line bg-soft-2/60">
                <th className="px-4 py-2.5 text-left text-sm font-semibold text-muted">Permission</th>
                {roles.data.roles.map((r) => <th key={r.code} className="px-3 py-2.5 text-center text-sm font-semibold text-muted">
                  {r.code === "super_admin" ? r.name : <button className="underline-offset-2 hover:text-ink hover:underline" onClick={() => setRoleEdit({ code: r.code, name: r.name, permissions: r.permissions })}>{r.name}</button>}
                  <span className="block font-normal">{r.users} user{r.users === 1 ? "" : "s"}</span></th>)}
              </tr></thead>
              <tbody>
                {groups.map((g) => [
                  <tr key={g}><td colSpan={1 + roles.data!.roles.length} className="bg-page px-4 pb-1 pt-3 text-xs font-semibold text-muted">{g}</td></tr>,
                  ...roles.data!.permissions.filter((p) => p.group === g).map((p) => (
                    <tr key={p.code} className="border-b border-line/60">
                      <td className="px-4 py-1.5">{p.label}</td>
                      {roles.data!.roles.map((r) => <td key={r.code} className="text-center">{r.permissions.includes(p.code) ? <span className="text-ok">●</span> : <span className="text-soft">○</span>}</td>)}
                    </tr>)),
                ])}
              </tbody>
            </table>
            <p className="px-4 py-3 text-xs text-muted">Click a role name to change what it can do. Super Admin always has everything.</p>
          </div>
        )}
      </Card>

      <Modal open={!!edit} onClose={() => setEdit(null)} title={edit?.id ? `Edit ${edit.full_name}` : "New user"} footer={edit && <>
        <Button onClick={() => setEdit(null)}>Close</Button><Button variant="primary" busy={busy} onClick={saveUser}>Save</Button></>}>
        {edit && <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Full name" required className="sm:col-span-2"><Input value={edit.full_name} onChange={(e) => setEdit({ ...edit, full_name: e.target.value })} /></Field>
          <Field label="Username" required hint="Letters, numbers, dot, dash"><Input disabled={!!edit.id} value={edit.username} onChange={(e) => setEdit({ ...edit, username: e.target.value.toLowerCase() })} /></Field>
          <Field label="Email"><Input type="email" value={edit.email} onChange={(e) => setEdit({ ...edit, email: e.target.value })} /></Field>
          <Field label="Role" required><Select value={edit.role_code} onChange={(e) => setEdit({ ...edit, role_code: e.target.value })}>
            {(roles.data?.roles ?? []).map((r) => <option key={r.code} value={r.code}>{r.name}</option>)}</Select></Field>
          {!edit.id && <Field label="Temporary password" required hint="10+ characters, letters and numbers. They must change it at first sign-in."><Input value={edit.temp_password} onChange={(e) => setEdit({ ...edit, temp_password: e.target.value })} /></Field>}
          {edit.id && edit.id !== me?.id && <Checkbox label="Account active" checked={edit.is_active} onChange={(e) => setEdit({ ...edit, is_active: e.target.checked })} />}
          {err && <div className="sm:col-span-2"><Notice tone="bad">{err}</Notice></div>}
        </div>}
      </Modal>

      <Modal open={!!reset} onClose={() => setReset(null)} title={`Reset password — ${reset?.full_name}`} footer={reset && <>
        <Button onClick={() => setReset(null)}>Close</Button>
        <Button variant="primary" busy={busy} onClick={async () => {
          setBusy(true); setErr(null);
          try { await post(`/api/users/${reset.id}/reset-password`, { temp_password: temp }); toast("Password reset. They must change it at sign-in."); setReset(null); users.reload(); }
          catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
        }}>Reset</Button></>}>
        <div className="space-y-3">
          <Notice>Passwords are stored encrypted and cannot be viewed by anyone. Set a temporary one, share it privately, and the user will choose their own at next sign-in. This also unlocks a locked-out account and signs them out everywhere.</Notice>
          <Field label="Temporary password"><Input value={temp} onChange={(e) => setTemp(e.target.value)} /></Field>
          {err && <Notice tone="bad">{err}</Notice>}
        </div>
      </Modal>

      <Modal open={!!roleEdit} onClose={() => setRoleEdit(null)} wide title={`Permissions — ${roleEdit?.name}`} footer={roleEdit && <>
        <Button onClick={() => setRoleEdit(null)}>Close</Button>
        <Button variant="primary" busy={busy} onClick={async () => {
          setBusy(true);
          try { await put(`/api/roles/${roleEdit.code}`, { permissions: roleEdit.permissions }); toast("Role updated."); setRoleEdit(null); roles.reload(); }
          catch (e) { toast((e as Error).message, "bad"); } finally { setBusy(false); }
        }}>Save</Button></>}>
        {roleEdit && roles.data && <div className="grid gap-x-6 gap-y-4 sm:grid-cols-2">
          {groups.map((g) => <div key={g}>
            <div className="mb-1.5 text-xs font-semibold text-muted">{g}</div>
            <div className="space-y-1.5">{roles.data!.permissions.filter((p) => p.group === g).map((p) => (
              <div key={p.code}><Checkbox label={p.label} checked={roleEdit.permissions.includes(p.code)}
                onChange={(e) => setRoleEdit({ ...roleEdit, permissions: e.target.checked ? [...roleEdit.permissions, p.code] : roleEdit.permissions.filter((x) => x !== p.code) })} /></div>))}
            </div>
          </div>)}
        </div>}
      </Modal>
    </div>
  );
}

// ---------------- Audit log ----------------
type Log = { id: number; at: string; username: string | null; action: string; entity: string; entity_id: string | null; summary: string | null; old_value: unknown; new_value: unknown; ip: string | null };

export function AuditTab() {
  const [q, setQ] = useState("");
  const [action, setAction] = useState("");
  const [page, setPage] = useState(1);
  const [sel, setSel] = useState<Log | null>(null);
  const dq = useDebounced(q);
  const { data, error } = useApi<{ items: Log[]; total: number; page: number; page_size: number }>(`/api/audit-logs${qs({ q: dq, action, page })}`);
  return (
    <Card pad={false} title="Audit log" actions={<span className="text-xs text-muted">Permanent record — cannot be edited or deleted</span>}>
      <div className="flex flex-wrap gap-2 border-b border-line px-4 py-3">
        <Input className="w-72" placeholder="Search description" value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
        <Select className="w-auto" value={action} onChange={(e) => { setAction(e.target.value); setPage(1); }}>
          <option value="">All actions</option>
          {["create", "update", "post", "approve", "reject", "cancel", "allocate", "export", "login", "login_failed", "locked", "password_reset", "lock", "unlock"].map((a) => <option key={a}>{a}</option>)}
        </Select>
      </div>
      {error ? <div className="p-4"><ErrorBox message={error} /></div> : !data ? <Spinner /> : <>
        <Table<Log> rows={data.items} rowKey={(r) => r.id} onRowClick={(r) => setSel(r)} cols={[
          { key: "at", label: "When", render: (r) => <span className="whitespace-nowrap text-muted">{dt(r.at)}</span> },
          { key: "u", label: "User", render: (r) => r.username ?? "—" },
          { key: "a", label: "Action", render: (r) => <span className="rounded bg-soft-2 px-1.5 py-0.5 text-xs">{r.action}</span> },
          { key: "s", label: "What", render: (r) => r.summary },
          { key: "ip", label: "IP", render: (r) => <span className="text-xs text-muted">{r.ip}</span> },
        ]} />
        <Pager page={data.page} pageSize={data.page_size} total={data.total} onPage={setPage} />
      </>}
      <Modal open={!!sel} onClose={() => setSel(null)} wide title="Audit entry">
        {sel && <div className="space-y-3 text-sm">
          <p><span className="text-muted">{dt(sel.at)}</span> · {sel.username} · {sel.action} {sel.entity} #{sel.entity_id}</p>
          <p>{sel.summary}</p>
          {sel.old_value != null && <div><div className="mb-1 text-xs font-semibold text-muted">Before</div><pre className="max-h-60 overflow-auto rounded-lg bg-soft-2 p-3 text-xs">{JSON.stringify(sel.old_value, null, 2)}</pre></div>}
          {sel.new_value != null && <div><div className="mb-1 text-xs font-semibold text-muted">After</div><pre className="max-h-60 overflow-auto rounded-lg bg-soft-2 p-3 text-xs">{JSON.stringify(sel.new_value, null, 2)}</pre></div>}
        </div>}
      </Modal>
    </Card>
  );
}

// ---------------- Tally ledger names ----------------
type TL = { code: string; name: string; type: string; tally_ledger_name: string | null };

export function TallyTab() {
  const toast = useToast();
  const { data, reload } = useApi<TL[]>("/api/tally-ledgers");
  const [vals, setVals] = useState<Record<string, string>>({});
  useEffect(() => { if (data) setVals(Object.fromEntries(data.map((x) => [x.code, x.tally_ledger_name ?? ""]))); }, [data]);
  if (!data) return <Spinner />;
  return (
    <Card pad={false} title="Tally ledger names" actions={<span className="text-xs text-muted">Dealer, supplier and bank names are set on their own records</span>}>
      <Table<TL> rows={data} rowKey={(r) => r.code} cols={[
        { key: "n", label: "Ledger here", render: (r) => <span>{r.name}<span className="block text-xs capitalize text-muted">{r.type}</span></span> },
        { key: "t", label: "Exact ledger name in Tally", render: (r) => <Input value={vals[r.code] ?? ""} onChange={(e) => setVals({ ...vals, [r.code]: e.target.value })} /> },
        { key: "s", label: "", align: "right", render: (r) => <Button size="sm" disabled={(vals[r.code] ?? "") === (r.tally_ledger_name ?? "") || !vals[r.code]}
          onClick={async () => { try { await put("/api/tally-ledgers", { account_code: r.code, tally_ledger_name: vals[r.code] }); toast("Saved."); reload(); } catch (e) { toast((e as Error).message, "bad"); } }}>Save</Button> },
      ]} />
      <p className="px-5 py-3 text-xs text-muted">Last checked: {d(new Date().toISOString())}. Confirm these with whoever maintains Tally before the first import.</p>
    </Card>
  );
}
