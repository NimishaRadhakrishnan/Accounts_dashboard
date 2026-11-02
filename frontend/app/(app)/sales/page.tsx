"use client";

import { Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { qs } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { d } from "@/lib/format";
import { useApi, useDebounced, useQueryParam } from "@/lib/hooks";
import { emptyFilter, ListBar } from "@/components/list-bar";
import { Amount, Badge, Button, Card, DocStatus, ErrorBox, LinkButton, PageHeader, Pager, Spinner, Table, Tabs } from "@/components/ui";

type Inv = {
  id: number; number: string | null; date: string; due_date: string; status: string; party: { name: string; state_name: string };
  grand_total: string; balance: string; payment_status: string; is_overdue: boolean; overdue_days: number; is_opening: boolean;
};
type CN = { id: number; number: string; date: string; party: { name: string }; invoice_number: string; reason: string; grand_total: string; status: string; sales_invoice_id: number };
type Page<T> = { items: T[]; total: number; page: number; page_size: number };

export default function SalesPage() {
  const { can } = useAuth();
  const router = useRouter();
  const tabParam = useQueryParam("tab");
  const [tab, setTab] = useState<"invoices" | "credit">("invoices");
  useEffect(() => { if (tabParam === "credit") setTab("credit"); }, [tabParam]);
  const [f, setF] = useState(emptyFilter());
  const fq = useDebounced(f);
  const path = tab === "invoices" ? "/api/sales-invoices" : "/api/credit-notes";
  const { data, error, loading, reload } = useApi<Page<Inv & CN>>(path + qs({ q: fq.q, status: fq.status, date_from: fq.date_from, date_to: fq.date_to, page: fq.page }));

  return (
    <>
      <PageHeader title="Sales & Invoices" subtitle="All bills we have given to dealers. Press “Open” on any row to see it, print it, or record goods returned."
        actions={can("sales.create") && <LinkButton href="/sales/new" variant="primary" icon={<Plus className="h-5 w-5" />}>Make a new invoice</LinkButton>} />
      <Tabs value={tab} onChange={(t) => { setTab(t); setF(emptyFilter()); }} items={[{ value: "invoices", label: "Invoices" }, { value: "credit", label: "Goods returned (credit notes)" }]} />
      <Card pad={false}>
        <ListBar f={f} setF={setF} statuses={tab === "invoices"
          ? [{ value: "draft", label: "Not finished (drafts)" }, { value: "posted", label: "Saved invoices" }, { value: "cancelled", label: "Cancelled" }]
          : [{ value: "posted", label: "Saved" }, { value: "cancelled", label: "Cancelled" }]} placeholder="Invoice number or dealer name" />
        {error ? <div className="p-4"><ErrorBox message={error} onRetry={reload} /></div> : loading && !data ? <Spinner /> : data && (
          <>
            {tab === "invoices" ? (
              <Table<Inv> rows={data.items} rowKey={(r) => r.id} onRowClick={(r) => router.push(`/sales/${r.id}`)} empty="No invoices found." emptyAction={f.q || f.status || f.date_from || f.date_to ? <Button onClick={() => setF(emptyFilter())}>Clear search</Button> : can("sales.create") ? <LinkButton href="/sales/new" variant="primary">Make the first invoice</LinkButton> : undefined} cols={[
                { key: "no", label: "Invoice no.", render: (r) => <span className="font-medium">{r.number ?? <span className="text-muted">No number yet</span>}{r.is_opening && <span className="ml-2"><Badge kind="opening" /></span>}</span> },
                { key: "date", label: "Date", render: (r) => d(r.date) },
                { key: "party", label: "Dealer", render: (r) => <span>{r.party.name}<span className="block text-sm text-muted">{r.party.state_name}</span></span> },
                { key: "due", label: "Pay by", render: (r) => <span className={r.is_overdue ? "text-bad" : ""}>{d(r.due_date)}</span> },
                { key: "total", label: "Total", align: "right", render: (r) => <Amount value={r.grand_total} /> },
                { key: "bal", label: "Still to receive", align: "right", render: (r) => r.status === "posted" ? <Amount value={r.balance} muted={Number(r.balance) === 0} /> : "" },
                { key: "st", label: "Status", render: (r) => <DocStatus {...r} /> },
              ]} />
            ) : (
              <Table<CN> rows={data.items} rowKey={(r) => r.id} onRowClick={(r) => router.push(`/sales/${r.sales_invoice_id}`)} empty="No goods returned." cols={[
                { key: "no", label: "Return no.", render: (r) => <span className="font-medium">{r.number}</span> },
                { key: "date", label: "Date", render: (r) => d(r.date) },
                { key: "party", label: "Dealer", render: (r) => r.party.name },
                { key: "inv", label: "For invoice", render: (r) => r.invoice_number },
                { key: "reason", label: "Why", render: (r) => <span className="text-muted">{r.reason}</span> },
                { key: "total", label: "Amount", align: "right", render: (r) => <Amount value={r.grand_total} /> },
                { key: "st", label: "Status", render: (r) => <Badge kind={r.status} /> },
              ]} />
            )}
            <Pager page={data.page} pageSize={data.page_size} total={data.total} onPage={(p) => setF({ ...f, page: p })} />
          </>
        )}
      </Card>
    </>
  );
}
