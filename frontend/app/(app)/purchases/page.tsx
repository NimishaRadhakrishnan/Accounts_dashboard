"use client";

import { Plus } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { qs } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { d } from "@/lib/format";
import { useApi, useDebounced, useQueryParam } from "@/lib/hooks";
import { emptyFilter, ListBar } from "@/components/list-bar";
import { Amount, Badge, Card, DocStatus, ErrorBox, LinkButton, PageHeader, Pager, Spinner, Table, Tabs } from "@/components/ui";

type Bill = {
  id: number; number: string | null; supplier_bill_no: string; date: string; due_date: string; status: string; party: { name: string };
  grand_total: string; balance: string; payment_status: string; is_overdue: boolean; overdue_days: number; is_opening: boolean;
};
type DN = { id: number; number: string; date: string; party: { name: string }; bill_number: string; reason: string; grand_total: string; status: string; purchase_bill_id: number };
type Page<T> = { items: T[]; total: number; page: number; page_size: number };

export default function PurchasesPage() {
  const { can } = useAuth();
  const router = useRouter();
  const tabParam = useQueryParam("tab");
  const statusParam = useQueryParam("status");
  const [tab, setTab] = useState<"bills" | "debit">("bills");
  const [f, setF] = useState(emptyFilter());
  useEffect(() => { if (tabParam === "debit") setTab("debit"); }, [tabParam]);
  useEffect(() => { if (statusParam) setF((x) => ({ ...x, status: statusParam })); }, [statusParam]);
  const fq = useDebounced(f);
  const path = tab === "bills" ? "/api/purchase-bills" : "/api/debit-notes";
  const { data, error, loading, reload } = useApi<Page<Bill & DN>>(path + qs({ q: fq.q, status: fq.status, date_from: fq.date_from, date_to: fq.date_to, page: fq.page }));

  return (
    <>
      <PageHeader title="Purchase Bills" subtitle="Bills we received from suppliers. One person enters a bill, and another person checks it before it counts."
        actions={can("purchases.create") && <LinkButton href="/purchases/new" variant="primary" icon={<Plus className="h-5 w-5" />}>Enter a supplier bill</LinkButton>} />
      <Tabs value={tab} onChange={(t) => { setTab(t); setF(emptyFilter()); }} items={[{ value: "bills", label: "Supplier bills" }, { value: "debit", label: "Goods sent back (debit notes)" }]} />
      <Card pad={false}>
        <ListBar f={f} setF={setF} placeholder="Bill number or supplier name" statuses={tab === "bills"
          ? [{ value: "draft", label: "Waiting to be checked" }, { value: "posted", label: "Checked and saved" }, { value: "cancelled", label: "Cancelled" }]
          : [{ value: "posted", label: "Saved" }, { value: "cancelled", label: "Cancelled" }]} />
        {error ? <div className="p-4"><ErrorBox message={error} onRetry={reload} /></div> : loading && !data ? <Spinner /> : data && (
          <>
            {tab === "bills" ? (
              <Table<Bill> rows={data.items} rowKey={(r) => r.id} onRowClick={(r) => router.push(`/purchases/${r.id}`)} empty="No bills found." cols={[
                { key: "sb", label: "Supplier's bill no.", render: (r) => <span className="font-medium">{r.supplier_bill_no}{r.is_opening && <span className="ml-2"><Badge kind="opening" /></span>}</span> },
                { key: "no", label: "Our number", render: (r) => r.number ?? <span className="text-muted">—</span> },
                { key: "date", label: "Date", render: (r) => d(r.date) },
                { key: "party", label: "Supplier", render: (r) => r.party.name },
                { key: "due", label: "Pay by", render: (r) => <span className={r.is_overdue ? "text-bad" : ""}>{d(r.due_date)}</span> },
                { key: "total", label: "Total", align: "right", render: (r) => <Amount value={r.grand_total} /> },
                { key: "bal", label: "Still to pay", align: "right", render: (r) => r.status === "posted" ? <Amount value={r.balance} muted={Number(r.balance) === 0} /> : "" },
                { key: "st", label: "Status", render: (r) => <DocStatus {...r} draftLabel="verify" /> },
              ]} />
            ) : (
              <Table<DN> rows={data.items} rowKey={(r) => r.id} onRowClick={(r) => router.push(`/purchases/${r.purchase_bill_id}`)} empty="Nothing sent back." cols={[
                { key: "no", label: "Number", render: (r) => <span className="font-medium">{r.number}</span> },
                { key: "date", label: "Date", render: (r) => d(r.date) },
                { key: "party", label: "Supplier", render: (r) => r.party.name },
                { key: "bill", label: "For bill", render: (r) => r.bill_number },
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
