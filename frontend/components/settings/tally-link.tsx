"use client";

import { CheckCircle2, Copy, Download, KeyRound, Plus, XCircle } from "lucide-react";
import { useState } from "react";
import { del, download, post, put } from "@/lib/api";
import { ago, dt, inr } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { Badge, Button, Card, ErrorBox, Field, Input, Modal, Notice, Select, Spinner, Table, useConfirm, useToast } from "../ui";

type Status = {
  connected: boolean; company?: string; books_from?: string; agent_version?: string; last_seen_at?: string; last_data_at?: string;
  last_full_at?: string; last_error?: string | null; last_error_at?: string | null;
  freshness?: { minutes_ago: number | null; stale: boolean };
  vouchers?: number; from?: string; to?: string; not_counted?: number; ledgers?: number;
  check?: { what: string; ours: string; tally: string; match: boolean }[]; check_possible?: boolean;
  categories?: Record<string, number>; groups_not_used?: string[];
  runs: { at: string; mode: string; ok: boolean; vouchers: number; skipped: number; message: string | null }[];
  keys: { id: number; label: string; hint: string; created_at: string; last_used_at: string | null }[];
  category_labels: Record<string, string>;
};

const WHAT: Record<string, string> = { bank: "Bank balances", cash: "Cash in hand", debtors: "Dealers owe us", creditors: "We owe suppliers", tax: "GST & taxes" };

export function TallyLinkTab() {
  const toast = useToast();
  const confirm = useConfirm();
  const { data: s, error, reload } = useApi<Status>("/api/tally/status");
  const [newKey, setNewKey] = useState<string | null>(null);
  const [label, setLabel] = useState("Office Tally computer");
  const [keyOpen, setKeyOpen] = useState(false);
  const [mapOpen, setMapOpen] = useState(false);

  if (error) return <ErrorBox message={error} onRetry={reload} />;
  if (!s) return <Spinner />;
  const healthy = s.connected && !s.freshness?.stale && !s.last_error;

  return (
    <div className="space-y-6">
      <Card title="Is the dashboard getting figures from Tally?">
        {!s.connected ? (
          <Notice tone="warn">Not yet. Follow the steps below on the computer where Tally runs.</Notice>
        ) : (
          <div className="space-y-4">
            <div className={`flex items-center gap-3 rounded-lg px-4 py-3 text-lg ${healthy ? "bg-ok-bg text-ok" : "bg-warn-bg text-warn"}`}>
              {healthy ? <CheckCircle2 className="h-6 w-6" /> : <XCircle className="h-6 w-6" />}
              <span>
                {healthy ? "Yes — working." : "There is a problem."} Last contact {ago(s.freshness?.minutes_ago)}.
                {s.last_error && <><br /><span className="text-base">Last problem ({dt(s.last_error_at)}): {s.last_error}</span></>}
              </span>
            </div>
            <dl className="grid gap-4 text-base sm:grid-cols-2 lg:grid-cols-4">
              <div><dt className="text-sm text-muted">Company in Tally</dt><dd className="font-medium">{s.company}</dd></div>
              <div><dt className="text-sm text-muted">Entries copied</dt><dd className="font-medium">{s.vouchers?.toLocaleString("en-IN")} <span className="text-sm font-normal text-muted">({s.from} to {s.to})</span></dd></div>
              <div><dt className="text-sm text-muted">Last new data</dt><dd className="font-medium">{dt(s.last_data_at)}</dd></div>
              <div><dt className="text-sm text-muted">Last full re-read</dt><dd className="font-medium">{dt(s.last_full_at)}</dd></div>
            </dl>
            {!!s.not_counted && <p className="text-base text-muted">{s.not_counted} entries are left out on purpose (cancelled, optional/post-dated, or not balanced in Tally).</p>}
          </div>
        )}
      </Card>

      {s.connected && (
        <Card title="Do the figures match Tally?">
          {s.check_possible ? (
            <table className="w-full text-base">
              <thead><tr className="border-b-2 border-line text-left text-sm text-ink"><th className="py-2">Balance today</th><th className="py-2 text-right">Worked out here</th><th className="py-2 text-right">Tally says</th><th className="py-2 text-right">Same?</th></tr></thead>
              <tbody>
                {s.check?.map((c) => (
                  <tr key={c.what} className="border-b border-line">
                    <td className="py-2.5">{WHAT[c.what] ?? c.what}</td>
                    <td className="num py-2.5 text-right">{inr(c.ours)}</td>
                    <td className="num py-2.5 text-right">{inr(c.tally)}</td>
                    <td className="py-2.5 text-right">{c.match ? <Badge kind="paid">✓ Yes</Badge> : <Badge kind="rejected">✕ No</Badge>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <p className="text-base text-muted">Balances are taken directly from Tally&apos;s own closing figures. (A full cross-check needs every entry since the books began.)</p>}
          <div className="mt-5 flex flex-wrap items-center gap-3">
            <p className="text-base text-muted">How Tally&apos;s groups are read: {Object.entries(s.categories ?? {}).map(([k, v]) => `${v} ${s.category_labels[k]?.toLowerCase() ?? k}`).join(", ")} ledgers.</p>
            <Button size="sm" onClick={() => setMapOpen(true)}>Check group mapping</Button>
          </div>
          {!!s.groups_not_used?.length && <div className="mt-3"><Notice tone="info">These groups are not used in any figure: {s.groups_not_used.join(", ")}. That is normal for assets, loans and capital. If one of them holds sales, expenses, dealers or banks, set it in “Check group mapping”.</Notice></div>}
        </Card>
      )}

      <Card title="Set up the Tally computer (once)">
        <ol className="list-decimal space-y-3 pl-6 text-base">
          <li><b>In Tally:</b> press F1 (Help) → Settings → Connectivity → set <i>TallyPrime acts as</i> to <b>Both</b> and <i>Port</i> to <b>9000</b>. Restart Tally.</li>
          <li><b>Install Python</b> from python.org (tick “Add Python to PATH” during install).</li>
          <li>
            <b>Download the connector</b> and unzip it into <code className="rounded bg-soft-2 px-1">C:\VishakanConnector</code>.{" "}
            <Button size="sm" icon={<Download className="h-4 w-4" />} onClick={() => download("/api/tally/connector.zip", "vishakan-tally-connector.zip").catch((e) => toast(e.message, "bad"))}>Download connector</Button>
          </li>
          <li><b>Create a connector key</b> below, open <code className="rounded bg-soft-2 px-1">connector.ini</code> in Notepad, and paste the key and this website&apos;s address.</li>
          <li>Double-click <b>1-test-connection.bat</b>. Both lines must show ✓.</li>
          <li>Double-click <b>2-install-auto-update.bat</b>. From now on Windows sends new figures every 10 minutes while the computer is on.</li>
        </ol>
        <p className="mt-4 text-sm text-muted">The connector only reads from Tally. It never changes anything in Tally. A full guide is inside the download (SETUP-GUIDE.txt).</p>
      </Card>

      <Card title="Connector keys" actions={<Button size="sm" variant="primary" icon={<Plus className="h-4 w-4" />} onClick={() => { setNewKey(null); setKeyOpen(true); }}>Create connector key</Button>}>
        {s.keys.length ? (
          <ul className="divide-y divide-line">
            {s.keys.map((k) => (
              <li key={k.id} className="flex flex-wrap items-center gap-3 py-3 text-base">
                <KeyRound className="h-5 w-5 text-muted" />
                <span className="font-medium">{k.label}</span><span className="text-muted">…{k.hint}</span>
                <span className="text-sm text-muted">last used {k.last_used_at ? dt(k.last_used_at) : "never"}</span>
                <Button size="sm" variant="danger" className="ml-auto" onClick={async () => {
                  if (await confirm({ title: `Turn off “${k.label}”?`, message: "The connector using this key will stop sending figures until it gets a new key.", yes: "Yes, turn it off", danger: true })) {
                    await del(`/api/tally/keys/${k.id}`); toast("Key turned off."); reload();
                  }
                }}>Turn off</Button>
              </li>
            ))}
          </ul>
        ) : <p className="text-base text-muted">No keys yet.</p>}
      </Card>

      <Card title="Recent updates from Tally" pad={false}>
        <Table rows={s.runs.map((r, i) => ({ ...r, i }))} rowKey={(r) => r.i} empty="Nothing received yet." cols={[
          { key: "at", label: "When", render: (r) => <span className="whitespace-nowrap">{dt(r.at)}</span> },
          { key: "mode", label: "Type", render: (r) => ({ full: "Full re-read", changes: "New / changed entries", heartbeat: "Check (no changes)", error: "Problem", masters: "Lists only" } as Record<string, string>)[r.mode] ?? r.mode },
          { key: "msg", label: "Result", render: (r) => <span className={r.ok ? "" : "text-bad"}>{r.message}</span> },
        ]} />
      </Card>

      <Modal open={keyOpen} onClose={() => { setKeyOpen(false); reload(); }} title="Create connector key" footer={!newKey ? <>
        <Button onClick={() => setKeyOpen(false)}>Close</Button>
        <Button variant="primary" onClick={async () => { try { const r = await post<{ key: string }>("/api/tally/keys", { label }); setNewKey(r.key); } catch (e) { toast((e as Error).message, "bad"); } }}>Create</Button>
      </> : <Button variant="primary" onClick={() => { setKeyOpen(false); reload(); }}>Done</Button>}>
        {!newKey ? (
          <Field label="Name for this key" hint="So you know which computer uses it"><Input value={label} onChange={(e) => setLabel(e.target.value)} /></Field>
        ) : (
          <div className="space-y-4">
            <Notice tone="warn">Copy this key now and paste it into connector.ini (token = …). It will not be shown again.</Notice>
            <div className="break-all rounded-lg border-2 border-soft bg-soft-2 p-3 font-mono text-base">{newKey}</div>
            <Button icon={<Copy className="h-4 w-4" />} onClick={() => navigator.clipboard.writeText(newKey).then(() => toast("Key copied."))}>Copy key</Button>
          </div>
        )}
      </Modal>
      {mapOpen && <GroupMap labels={s.category_labels} onClose={() => { setMapOpen(false); reload(); }} />}
    </div>
  );
}

function GroupMap({ labels, onClose }: { labels: Record<string, string>; onClose: () => void }) {
  const toast = useToast();
  const { data } = useApi<{ groups: { name: string; parent: string | null; category: string }[]; overrides: Record<string, string> }>("/api/tally/groups");
  const [map, setMap] = useState<Record<string, string> | null>(null);
  const cur = map ?? data?.overrides ?? {};
  return (
    <Modal open onClose={onClose} wide title="How Tally groups are read" footer={<>
      <Button onClick={onClose}>Close</Button>
      <Button variant="primary" onClick={async () => { try { await put("/api/tally/group-map", { mapping: cur }); toast("Saved. Figures now use the new mapping."); onClose(); } catch (e) { toast((e as Error).message, "bad"); } }}>Save</Button>
    </>}>
      <p className="mb-4 text-base text-muted">Each group is read automatically from Tally&apos;s own main groups. Change one only if it is wrong — for example a dealer group created under the wrong parent.</p>
      {!data ? <Spinner /> : (
        <table className="w-full text-base">
          <thead><tr className="border-b-2 border-line text-left text-sm"><th className="py-2">Group in Tally</th><th className="py-2">Under</th><th className="py-2">Counted as</th></tr></thead>
          <tbody>
            {data.groups.map((g) => (
              <tr key={g.name} className="border-b border-line">
                <td className="py-2">{g.name}</td>
                <td className="py-2 text-muted">{g.parent || "—"}</td>
                <td className="py-2">
                  <Select className="w-auto" value={cur[g.name.toLowerCase()] ?? ""} onChange={(e) => {
                    const next = { ...cur };
                    if (e.target.value) next[g.name.toLowerCase()] = e.target.value; else delete next[g.name.toLowerCase()];
                    setMap(next);
                  }}>
                    <option value="">Automatic ({labels[g.category] ?? g.category})</option>
                    {Object.entries(labels).filter(([k]) => k !== "indirect_inc").map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </Select>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Modal>
  );
}
