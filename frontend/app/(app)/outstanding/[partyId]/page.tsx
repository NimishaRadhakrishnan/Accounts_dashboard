"use client";

import { FileDown, FileSpreadsheet } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useState } from "react";
import { download, qs } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { d, fyRange, inr, today } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { Amount, Button, Card, ErrorBox, Input, PageHeader, Spinner, Table, useToast } from "@/components/ui";

type Party = { id: number; name: string; code: string; gstin: string | null; city: string | null; state_name: string; phone: string | null; contact_person: string | null; credit_days: number; credit_limit: string; is_customer: boolean; is_supplier: boolean };
type Item = { id: number; number: string; supplier_bill_no: string | null; date: string; due_date: string; total: string; settled: string; balance: string; overdue_days: number };
type Report = { title: string; rows: { date: string; type: string; number: string; narration: string; debit: string | null; credit: string | null; balance: string }[] };

export default function PartyStatementPage() {
  const { partyId } = useParams<{ partyId: string }>();
  const { can } = useAuth();
  const toast = useToast();
  const fy = fyRange();
  const [from, setFrom] = useState(fy.from);
  const [to, setTo] = useState(today());
  const { data: party, error } = useApi<Party>(`/api/parties/${partyId}`);
  const recv = useApi<Item[]>(party?.is_customer ? `/api/parties/${partyId}/open-invoices` : null);
  const pay = useApi<Item[]>(party?.is_supplier ? `/api/parties/${partyId}/open-bills` : null);
  const params = qs({ party_id: partyId, date_from: from, date_to: to });
  const stmt = useApi<Report>(`/api/reports/party-ledger${params}`);

  if (error) return <ErrorBox message={error} />;
  if (!party) return <Spinner />;
  const items = [...(recv.data ?? []).map((x) => ({ ...x, k: "r" })), ...(pay.data ?? []).map((x) => ({ ...x, k: "p" }))];

  return (
    <>
      <PageHeader title={party.name} subtitle={`${party.code} · ${party.gstin ?? "Unregistered"} · ${party.city ?? ""} ${party.state_name} · ${party.credit_days} days credit${Number(party.credit_limit) > 0 ? ` · limit ${inr(party.credit_limit)}` : ""}`}
        actions={can("reports.export") && <>
          <Button icon={<FileSpreadsheet className="h-5 w-5" />} onClick={() => download(`/api/reports/party-ledger/export${params}&fmt=xlsx`, "statement.xlsx").catch((e) => toast(e.message, "bad"))}>Download Excel</Button>
          <Button variant="primary" icon={<FileDown className="h-5 w-5" />} onClick={() => download(`/api/reports/party-ledger/export${params}&fmt=pdf`, "statement.pdf").catch((e) => toast(e.message, "bad"))}>Download statement (PDF)</Button>
        </>} />

      <Card title="Bills not fully paid" pad={false} className="mb-6">
        <Table<Item & { k: string }> rows={items} rowKey={(r) => `${r.k}${r.id}`} empty="Nothing pending — everything is paid." cols={[
          { key: "no", label: "Bill / invoice", render: (r) => <Link className="font-medium text-accent-strong hover:underline" href={r.k === "r" ? `/sales/${r.id}` : `/purchases/${r.id}`}>{r.supplier_bill_no ?? r.number}</Link> },
          { key: "date", label: "Date", render: (r) => d(r.date) },
          { key: "due", label: "Pay by", render: (r) => <span className={r.overdue_days ? "text-bad" : ""}>{d(r.due_date)}{r.overdue_days > 0 && <span className="block text-sm">{r.overdue_days} days late</span>}</span> },
          { key: "t", label: "Total", align: "right", render: (r) => <Amount value={r.total} /> },
          { key: "s", label: "Paid", align: "right", render: (r) => <Amount value={r.settled} muted /> },
          { key: "b", label: "Still to pay", align: "right", render: (r) => <Amount value={r.balance} strong /> },
        ]} />
      </Card>

      <Card title="Full statement (all entries)" pad={false} actions={
        <div className="flex flex-wrap items-center gap-2 text-base text-muted">
          <Input type="date" className="w-auto" value={from} onChange={(e) => setFrom(e.target.value)} aria-label="From" /> to
          <Input type="date" className="w-auto" value={to} onChange={(e) => setTo(e.target.value)} aria-label="To" />
        </div>}>
        {stmt.error ? <div className="p-4"><ErrorBox message={stmt.error} /></div> : !stmt.data ? <Spinner /> : (
          <Table rows={stmt.data.rows.map((r, i) => ({ ...r, _i: i }))} rowKey={(r) => r._i} cols={[
            { key: "date", label: "Date", render: (r) => d(r.date) },
            { key: "type", label: "Type", render: (r) => <span className={r.type === "Opening" || r.type === "Closing" ? "font-semibold" : ""}>{r.type}</span> },
            { key: "no", label: "No", render: (r) => r.number },
            { key: "n", label: "Details", render: (r) => <span className="text-muted">{r.narration}</span> },
            { key: "dr", label: "Debit", align: "right", render: (r) => r.debit !== null && Number(r.debit) ? <Amount value={r.debit} /> : "" },
            { key: "cr", label: "Credit", align: "right", render: (r) => r.credit !== null && Number(r.credit) ? <Amount value={r.credit} /> : "" },
            { key: "bal", label: "Balance", align: "right", render: (r) => <Amount value={r.balance} strong={r.type === "Closing"} /> },
          ]} />
        )}
      </Card>
    </>
  );
}
