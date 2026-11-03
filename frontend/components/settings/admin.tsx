"use client";

import { Plus } from "lucide-react";
import { useState } from "react";
import { post, put, qs } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { dt } from "@/lib/format";
import { useApi, useDebounced } from "@/lib/hooks";
import { Badge, Button, Card, Checkbox, ErrorBox, Field, Input, Modal, Notice, Pager, Select, Spinner, Table, useToast } from "../ui";

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

