"use client";

import { Paperclip, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { api, download } from "@/lib/api";
import { d, inr } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { Amount, Badge, Button, Card, Notice, Table } from "./ui";

export type Line = { line_no: number; product_id: number | null; description: string; hsn_code: string | null; qty: string; unit: string; rate: string; discount_pct: string; taxable: string; gst_rate: string; cgst: string; sgst: string; igst: string; total: string };
export type Doc = {
  id: number; number: string | null; date: string; due_date: string; status: string; supply_type: string; place_of_supply: string;
  party: { id: number; name: string; gstin: string | null; state_name: string; state_code: string };
  taxable_total: string; discount_total: string; cgst_total: string; sgst_total: string; igst_total: string; round_off: string; grand_total: string;
  settled: string; balance: string; payment_status: string; is_overdue: boolean; overdue_days: number; is_opening: boolean;
  notes: string | null; cancel_reason: string | null; lines: Line[]; created_at: string; posted_at: string | null;
};

export function DocLines({ doc }: { doc: Doc }) {
  const intra = doc.supply_type === "intra";
  if (doc.is_opening) return <p className="p-5 text-base text-muted">This amount was brought over from the old accounts (Tally/Excel), so there are no item details here.</p>;
  return (
    <Table<Line> rows={doc.lines} rowKey={(l) => l.line_no} cols={[
      { key: "n", label: "No.", render: (l) => <span className="text-muted">{l.line_no}</span> },
      { key: "desc", label: "Item", render: (l) => <span>{l.description}{l.hsn_code && <span className="block text-sm text-muted">HSN {l.hsn_code}</span>}</span> },
      { key: "qty", label: "Quantity", align: "right", render: (l) => <span className="num">{Number(l.qty)} {l.unit}</span> },
      { key: "rate", label: "Rate for one", align: "right", render: (l) => <Amount value={l.rate} /> },
      { key: "disc", label: "Discount", align: "right", render: (l) => Number(l.discount_pct) ? `${Number(l.discount_pct)}%` : "" },
      { key: "tx", label: "Before GST", align: "right", render: (l) => <Amount value={l.taxable} /> },
      { key: "gst", label: "GST", align: "right", render: (l) => <span className="num">{Number(l.gst_rate)}%<span className="block text-sm text-muted">{inr(intra ? Number(l.cgst) + Number(l.sgst) : l.igst)}</span></span> },
      { key: "total", label: "Amount", align: "right", render: (l) => <Amount value={l.total} strong /> },
    ]} />
  );
}

export function DocTotals({ doc }: { doc: Doc }) {
  const intra = doc.supply_type === "intra";
  const rows: [string, string][] = [];
  if (!doc.is_opening) {
    if (Number(doc.discount_total)) rows.push(["Discount given", doc.discount_total]);
    rows.push(["Amount before GST", doc.taxable_total]);
    if (intra) rows.push(["CGST", doc.cgst_total], ["SGST", doc.sgst_total]);
    else rows.push(["IGST", doc.igst_total]);
    if (Number(doc.round_off)) rows.push(["Rounded off", doc.round_off]);
  }
  return (
    <dl className="space-y-2 text-base">
      {rows.map(([k, v]) => <div key={k} className="flex justify-between text-muted"><dt>{k}</dt><dd className="num text-ink">{inr(v)}</dd></div>)}
      <div className="flex justify-between border-t-2 border-soft pt-2 text-xl font-semibold"><dt>Total</dt><dd className="num">{inr(doc.grand_total)}</dd></div>
      {doc.status === "posted" && <>
        <div className="flex justify-between pt-2 text-muted"><dt>Already paid</dt><dd className="num text-ink">{inr(doc.settled)}</dd></div>
        <div className="flex justify-between rounded-lg bg-soft-2 px-3 py-2 text-lg font-semibold"><dt>Still to be paid</dt><dd className={Number(doc.balance) > 0 && doc.is_overdue ? "num text-bad" : "num"}>{inr(doc.balance)}</dd></div>
      </>}
    </dl>
  );
}

export function DocMeta({ doc, partyLabel, extra }: { doc: Doc; partyLabel: string; extra?: [string, React.ReactNode][] }) {
  const items: [string, React.ReactNode][] = [
    [partyLabel, <span key="p">{doc.party.name}<span className="block text-sm font-normal text-muted">{doc.party.gstin ?? "No GSTIN"} · {doc.party.state_name}</span></span>],
    ["Date", d(doc.date)],
    ["Pay by", <span key="due" className={doc.is_overdue ? "text-bad" : ""}>{d(doc.due_date)}{doc.is_overdue && <span className="block text-sm">{doc.overdue_days} days late</span>}</span>],
    ["Tax", doc.supply_type === "intra" ? "CGST + SGST" : "IGST (other state)"],
    ...(extra ?? []),
  ];
  return (
    <dl className="grid gap-5 text-base sm:grid-cols-2 lg:grid-cols-5">
      {items.map(([k, v]) => <div key={k}><dt className="text-sm text-muted">{k}</dt><dd className="mt-0.5 font-medium">{v}</dd></div>)}
    </dl>
  );
}

type Att = { id: number; name: string; size: number; uploaded_at: string };

export function Attachments({ entity, id, canUpload }: { entity: string; id: number; canUpload: boolean }) {
  const { data, reload } = useApi<Att[]>(`/api/attachments?entity=${entity}&entity_id=${id}`);
  const ref = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  return (
    <Card title="Photo / scan of the bill" actions={canUpload && (
      <>
        <input ref={ref} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" className="hidden" onChange={async (e) => {
          const file = e.target.files?.[0];
          if (!file) return;
          setBusy(true); setErr(null);
          const fd = new FormData();
          fd.append("entity", entity); fd.append("entity_id", String(id)); fd.append("file", file);
          try { await api("/api/attachments", { method: "POST", form: fd }); reload(); } catch (x) { setErr((x as Error).message); }
          finally { setBusy(false); e.target.value = ""; }
        }} />
        <Button size="sm" busy={busy} icon={<Upload className="h-4 w-4" />} onClick={() => ref.current?.click()}>Add photo or PDF</Button>
      </>)}>
      {err && <div className="mb-3"><Notice tone="bad">{err}</Notice></div>}
      {data?.length ? (
        <ul className="space-y-1.5">
          {data.map((a) => (
            <li key={a.id}>
              <button className="inline-flex min-h-10 items-center gap-2 text-base text-accent-strong underline" onClick={() => download(`/api/attachments/${a.id}`, a.name)}>
                <Paperclip className="h-4 w-4" />{a.name}<span className="text-sm text-muted">({Math.ceil(a.size / 1024)} KB)</span>
              </button>
            </li>
          ))}
        </ul>
      ) : <p className="text-base text-muted">Nothing added yet. You can add a phone photo or a PDF (up to 5 MB).</p>}
    </Card>
  );
}

export function LinkedList({ title, rows, empty }: { title: string; rows: { id: number; number: string | null; date: string; amount: string; status: string; extra?: string }[]; empty: string }) {
  return (
    <Card title={title} pad={false}>
      {rows.length ? (
        <ul className="divide-y divide-line">
          {rows.map((r) => (
            <li key={`${r.id}-${r.number}`} className="flex flex-wrap items-center gap-3 px-5 py-3 text-base">
              <span className="whitespace-nowrap font-medium">{r.number ?? "Pending"}</span>
              <span className="whitespace-nowrap text-muted">{d(r.date)}</span>
              {r.extra && <span className="truncate text-muted">{r.extra}</span>}
              <span className="ml-auto"><Badge kind={r.status} /></span>
              <Amount value={r.amount} />
            </li>
          ))}
        </ul>
      ) : <p className="px-5 py-4 text-base text-muted">{empty}</p>}
    </Card>
  );
}
