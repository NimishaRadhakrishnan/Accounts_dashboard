"use client";

import { FileDown, FileSpreadsheet } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { download, qs } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { inr, today } from "@/lib/format";
import { useApi, useQueryParam } from "@/lib/hooks";
import { Button, Card, cx, ErrorBox, Input, PageHeader, Spinner, Table, Tabs, useToast } from "@/components/ui";

type Bucket = { key: string; label: string; amount: string };
type PartyRow = { party_id: number; party_name: string; party_code: string; not_due: string; d0_30: string; d31_60: string; d61_90: string; d90_plus: string; gross: string; advance: string; net: string; oldest_overdue_days: number; open_count: number; credit_limit: string; over_limit: boolean };
const BUCKET_WORDS: Record<string, string> = { not_due: "Not due yet", d0_30: "Late up to 1 month", d31_60: "Late 1–2 months", d61_90: "Late 2–3 months", d90_plus: "Late over 3 months" };
type Ageing = { buckets: Bucket[]; gross: string; advances: string; net: string; parties: PartyRow[] };

export default function OutstandingPage() {
  const router = useRouter();
  const { can } = useAuth();
  const toast = useToast();
  const tabParam = useQueryParam("tab");
  const [kind, setKind] = useState<"receivable" | "payable">("receivable");
  useEffect(() => { if (tabParam === "payable") setKind("payable"); }, [tabParam]);
  const [asOf, setAsOf] = useState(today());
  const [q, setQ] = useState("");
  const { data, error, loading, reload } = useApi<Ageing>(`/api/outstanding/${kind}${qs({ as_of: asOf })}`);
  const rows = useMemo(() => (data?.parties ?? []).filter((p) => !q || p.party_name.toLowerCase().includes(q.toLowerCase())), [data, q]);
  const who = kind === "receivable" ? "Dealer" : "Supplier";

  const exp = (fmt: "xlsx" | "pdf") => download(`/api/reports/${kind}-ageing/export${qs({ fmt, as_of: asOf })}`, `${kind}-ageing.${fmt}`).catch((e) => toast(e.message, "bad"));
  // eslint-disable-next-line react/display-name
  const money = (k: keyof PartyRow, cls?: string) => (r: PartyRow) => <span className={cx("num", Number(r[k]) === 0 ? "text-muted/50" : cls)}>{Number(r[k]) === 0 ? "–" : inr(r[k] as string, { symbol: false })}</span>;

  return (
    <>
      <PageHeader title="Outstanding Payments" subtitle="Money still to come in from dealers, and money we still have to pay suppliers — and how late it is."
        actions={can("reports.export") && <>
          <Button icon={<FileSpreadsheet className="h-5 w-5" />} onClick={() => exp("xlsx")}>Download Excel</Button>
          <Button icon={<FileDown className="h-5 w-5" />} onClick={() => exp("pdf")}>Download PDF</Button>
        </>} />
      <Tabs value={kind} onChange={setKind} items={[{ value: "receivable", label: "Dealers owe us" }, { value: "payable", label: "We owe suppliers" }]} />
      {error ? <ErrorBox message={error} onRetry={reload} /> : !data || loading ? <Spinner /> : (
        <>
          <div className="mb-6 grid gap-3 sm:grid-cols-3 lg:grid-cols-6">
            {data.buckets.map((b) => (
              <div key={b.key} className="rounded-xl border border-line bg-white px-4 py-3 shadow-card">
                <div className={cx("text-sm", b.key === "d90_plus" ? "font-semibold text-bad" : "text-muted")}>{BUCKET_WORDS[b.key] ?? b.label}</div>
                <div className="num mt-1 text-lg font-semibold">{inr(b.amount)}</div>
              </div>
            ))}
            <div className="rounded-xl border border-sidebar bg-sidebar px-4 py-3 text-white shadow-card">
              <div className="text-sm text-white/80">Total{Number(data.advances) > 0 && " (after advances)"}</div>
              <div className="num mt-1 text-lg font-semibold">{inr(data.net)}</div>
            </div>
          </div>
          <Card pad={false}>
            <div className="flex flex-wrap items-end gap-4 border-b border-line px-4 py-4">
              <label><span className="mb-1.5 block text-sm font-medium">Search</span><Input className="w-72" placeholder={`${who} name`} value={q} onChange={(e) => setQ(e.target.value)} /></label>
              <label><span className="mb-1.5 block text-sm font-medium">As on date</span><Input type="date" className="w-auto" value={asOf} onChange={(e) => setAsOf(e.target.value || today())} /></label>
              <span className="ml-auto self-end text-sm text-muted">Columns show how late the money is</span>
            </div>
            <Table<PartyRow> rows={rows} rowKey={(r) => r.party_id} onRowClick={(r) => router.push(`/outstanding/${r.party_id}`)} empty="Nothing pending. Everything is paid." openLabel="See bills" cols={[
              { key: "p", label: who, render: (r) => <span><span className="font-medium">{r.party_name}</span>
                <span className="block text-sm text-muted">{r.open_count} unpaid bill{r.open_count === 1 ? "" : "s"}{r.over_limit && <span className="font-medium text-bad"> · above credit limit</span>}</span></span> },
              { key: "nd", label: "Not due yet", align: "right", render: money("not_due") },
              { key: "a", label: "Late 1–30 days", align: "right", render: money("d0_30") },
              { key: "b", label: "31–60 days", align: "right", render: money("d31_60") },
              { key: "c", label: "61–90 days", align: "right", render: money("d61_90") },
              { key: "d", label: "Over 90 days", align: "right", render: money("d90_plus", "font-medium text-bad") },
              { key: "adv", label: "Advance", align: "right", render: money("advance", "text-warn") },
              { key: "net", label: "Total", align: "right", render: (r) => <span className="num font-semibold">{inr(r.net)}</span> },
            ]} />
          </Card>
        </>
      )}
    </>
  );
}
