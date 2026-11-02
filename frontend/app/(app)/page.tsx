"use client";

import {
  AlertCircle, ArrowDownLeft, ArrowDownRight, ArrowRight, ArrowUpRight, BarChart3, CheckCircle2, Clock3, FilePlus2,
  Landmark, ReceiptText, ShoppingCart, Wallet,
} from "lucide-react";
import Link from "next/link";
import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/lib/auth";
import { d, inr, inrShort, num, pct, rupees } from "@/lib/format";
import { Card, cx, ErrorBox, Spinner } from "@/components/ui";

// Validated (dataviz validator, light surface): Sales #1d7f5f bars + Costs #eb6834 line.
// Protan ΔE 7.0 sits in the floor band, so the series also differ by mark type (bar vs line) and have a legend.
const SALES = "#1d7f5f";
const COSTS = "#eb6834";

type Dash = {
  as_of: string; fy: string;
  kpis: Record<string, string>;
  banks: { id: number; name: string; kind: string; balance: string }[];
  trend: { month: string; sales: string; purchases: string; expenses: string; future: boolean }[];
  receivable_ageing: { key: string; label: string; amount: string }[];
  payable_ageing: { key: string; label: string; amount: string }[];
  overdue_dealers: { party_id: number; party_name: string; net: string; oldest_overdue_days: number; open_count: number }[];
  upcoming_payments: { id: number; number: string; party_name: string; due_date: string; balance: string; supplier_bill_no: string }[];
  recent: { date: string; type: string; source_id: number; narration: string; amount: string; is_reversal: boolean }[];
  pending: { payments: number; expenses: number; bills_to_verify: number };
};

// ---------- "What would you like to do?" ----------
const ACTIONS = [
  { href: "/sales/new", perm: "sales.create", icon: FilePlus2, title: "Make a new invoice", text: "Bill a dealer for goods sold" },
  { href: "/payments?new=receipt", perm: "receipts.create", icon: ArrowDownLeft, title: "Money received", text: "A dealer paid us" },
  { href: "/payments?new=payment", perm: "payments.create", icon: ArrowUpRight, title: "Pay a supplier", text: "We paid a supplier" },
  { href: "/purchases/new", perm: "purchases.create", icon: ShoppingCart, title: "Enter a supplier bill", text: "A bill we received" },
  { href: "/expenses?new=1", perm: "expenses.create", icon: Wallet, title: "Add an expense", text: "Fuel, rent, travel, office" },
  { href: "/outstanding", perm: "outstanding.view", icon: Clock3, title: "Who owes us?", text: "Pending payments from dealers" },
  { href: "/reports", perm: "reports.view", icon: BarChart3, title: "Get a report", text: "Download Excel or PDF" },
];

function ActionTile({ href, icon: Icon, title, text }: { href: string; icon: typeof Wallet; title: string; text: string }) {
  return (
    <Link href={href} className="group flex items-center gap-4 rounded-xl border-2 border-line bg-white p-4 shadow-card transition-colors hover:border-accent hover:bg-soft-2/40">
      <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-xl bg-soft text-sidebar group-hover:bg-sidebar group-hover:text-white">
        <Icon className="h-7 w-7" strokeWidth={1.8} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-lg font-semibold text-ink">{title}</span>
        <span className="block text-base text-muted">{text}</span>
      </span>
      <ArrowRight className="h-6 w-6 shrink-0 text-accent-strong" />
    </Link>
  );
}

// ---------- Money at a glance ----------
function Compare({ now, prev, goodWhenUp = true }: { now: string; prev: string; goodWhenUp?: boolean }) {
  const p = pct(now, prev);
  if (p === null) return null;
  const up = p >= 0;
  const good = up === goodWhenUp;
  return (
    <span className={cx("inline-flex items-center gap-1 text-base font-medium", good ? "text-ok" : "text-bad")}>
      {up ? <ArrowUpRight className="h-5 w-5" /> : <ArrowDownRight className="h-5 w-5" />}
      {Math.abs(p).toFixed(0)}% {up ? "more" : "less"} than last month
    </span>
  );
}

function Kpi({ label, value, sub, href, foot, tone }: { label: string; value: string; sub?: React.ReactNode; href: string; foot?: React.ReactNode; tone?: "bad" }) {
  return (
    <Link href={href} className="flex flex-col rounded-xl border-2 border-line bg-white p-5 shadow-card transition-colors hover:border-accent">
      <div className="text-base font-medium text-muted">{label}</div>
      <div className={cx("num mt-1.5 text-3xl font-semibold", tone === "bad" ? "text-bad" : "text-ink")}>{rupees(value)}</div>
      <div className="mt-1 min-h-6 text-base text-muted">{sub}</div>
      {foot && <div className="mt-3 border-t border-line pt-3 text-base text-muted">{foot}</div>}
      <div className="mt-auto pt-3 text-base font-medium text-accent-strong">See details →</div>
    </Link>
  );
}

const TYPE_LABEL: Record<string, string> = {
  sales_invoice: "Invoice", credit_note: "Sales return", purchase_bill: "Supplier bill", debit_note: "Purchase return",
  receipt: "Money received", payment: "Money paid", expense: "Expense", contra: "Cash ↔ Bank",
};
const TYPE_HREF: Record<string, (id: number) => string> = {
  sales_invoice: (id) => `/sales/${id}`, purchase_bill: (id) => `/purchases/${id}`,
  receipt: () => "/payments", payment: () => "/payments?tab=payments", expense: () => "/expenses",
  contra: () => "/payments?tab=transfers", credit_note: () => "/sales?tab=credit", debit_note: () => "/purchases?tab=debit",
};

function AgeingBars({ rows }: { rows: { key: string; label: string; amount: string }[] }) {
  const max = Math.max(1, ...rows.map((r) => num(r.amount)));
  const plain: Record<string, string> = { not_due: "Not due yet", d0_30: "Late up to 1 month", d31_60: "Late 1–2 months", d61_90: "Late 2–3 months", d90_plus: "Late over 3 months" };
  return (
    <div className="space-y-4">
      {rows.map((r) => (
        <div key={r.key}>
          <div className="flex justify-between text-base">
            <span className={cx(r.key === "d90_plus" ? "font-semibold text-bad" : "text-ink")}>{plain[r.key] ?? r.label}</span>
            <span className="num font-semibold">{rupees(r.amount)}</span>
          </div>
          <div className="mt-1.5 h-3 rounded-full bg-soft-2">
            <div className="h-3 rounded-full" style={{ width: `${Math.max(num(r.amount) ? 2 : 0, (num(r.amount) / max) * 100)}%`, background: r.key === "not_due" ? "#a9b7ae" : SALES, opacity: r.key === "not_due" ? 1 : 0.55 + ["d0_30", "d31_60", "d61_90", "d90_plus"].indexOf(r.key) * 0.15 }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function TrendTooltip({ active, payload, label }: { active?: boolean; payload?: { dataKey: string; value: number }[]; label?: string }) {
  if (!active || !payload?.length) return null;
  const s = payload.find((p) => p.dataKey === "sales")?.value ?? 0;
  const c = payload.find((p) => p.dataKey === "costs")?.value ?? 0;
  return (
    <div className="rounded-lg border border-line bg-white px-4 py-3 text-base shadow-lg">
      <div className="mb-1 font-semibold text-ink">{label}</div>
      <div className="flex items-center gap-2"><span className="h-3 w-3 rounded-sm" style={{ background: SALES }} />Sales <span className="num ml-auto pl-6 font-medium">{rupees(s)}</span></div>
      <div className="flex items-center gap-2"><span className="h-1 w-3" style={{ background: COSTS }} />Spending <span className="num ml-auto pl-6 font-medium">{rupees(c)}</span></div>
    </div>
  );
}

export default function HomePage() {
  const { me, can } = useAuth();
  const { data, error, loading, reload } = useApi<Dash>("/api/dashboard");
  const hour = new Date().getHours();
  const hello = hour < 12 ? "Good morning" : hour < 17 ? "Good afternoon" : "Good evening";
  const actions = ACTIONS.filter((a) => can(a.perm));

  const approvals = data ? [
    can("purchases.verify") && data.pending.bills_to_verify > 0 && { n: data.pending.bills_to_verify, label: `supplier bill${data.pending.bills_to_verify > 1 ? "s" : ""} waiting for you to check`, href: "/purchases?status=draft" },
    can("payments.approve") && data.pending.payments > 0 && { n: data.pending.payments, label: `payment${data.pending.payments > 1 ? "s" : ""} waiting for your approval`, href: "/payments?tab=payments" },
    can("expenses.approve") && data.pending.expenses > 0 && { n: data.pending.expenses, label: `expense${data.pending.expenses > 1 ? "s" : ""} waiting for your approval`, href: "/expenses?tab=approval" },
  ].filter(Boolean) as { n: number; label: string; href: string }[] : [];

  return (
    <>
      <div className="mb-6">
        <h1 className="text-2xl font-semibold">{hello}, {me?.full_name.split(" ")[0]}</h1>
        <p className="mt-1 text-base text-muted">Choose what you want to do, or look at today&apos;s summary further down.</p>
      </div>

      {approvals.length > 0 && (
        <div className="mb-6 space-y-2 rounded-xl border-2 border-warn/25 bg-warn-bg p-4">
          <div className="flex items-center gap-2 text-lg font-semibold text-warn"><AlertCircle className="h-6 w-6" /> Needs your attention</div>
          <div className="flex flex-wrap gap-2.5">
            {approvals.map((a) => (
              <Link key={a.href} href={a.href} className="inline-flex min-h-11 items-center gap-2 rounded-lg border-2 border-warn/30 bg-white px-4 text-base font-medium text-warn hover:bg-warn-bg">
                <span className="rounded-full bg-warn px-2 text-sm text-white">{a.n}</span>{a.label} →
              </Link>
            ))}
          </div>
        </div>
      )}

      {actions.length > 0 && (
        <section className="mb-8" aria-labelledby="todo">
          <h2 id="todo" className="mb-3 text-xl font-semibold">What would you like to do?</h2>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {actions.map((a) => <ActionTile key={a.href} {...a} />)}
          </div>
        </section>
      )}

      <h2 className="mb-3 text-xl font-semibold">Money at a glance</h2>
      {loading && !data ? <Spinner /> : error ? <ErrorBox message={error} onRetry={reload} /> : data && (() => {
        const k = data.kpis;
        const trend = data.trend.map((t) => ({ month: t.month, sales: t.future ? null : num(t.sales), costs: t.future ? null : num(t.purchases) + num(t.expenses) }));
        return (
          <>
            <div className="grid gap-4 sm:grid-cols-2 2xl:grid-cols-5 xl:grid-cols-3">
              <Kpi label="Sales this month" value={k.sales_month} href="/sales" sub={<Compare now={k.sales_month} prev={k.sales_prev_month} />}
                foot={<>This year so far: <span className="num font-semibold text-ink">{rupees(k.sales_fy)}</span><br /><span className="text-sm">(before GST)</span></>} />
              <Kpi label="Expenses this month" value={k.expenses_month} href="/expenses" sub={<>Supplier purchases: <span className="num">{rupees(k.purchases_month)}</span></>}
                foot={<>This year so far: <span className="num font-semibold text-ink">{rupees(k.expenses_fy)}</span></>} />
              <Kpi label="Dealers owe us" value={k.receivables} href="/outstanding" sub="Money still to come in"
                foot={<span className={num(k.receivables_overdue) > 0 ? "font-medium text-bad" : ""}>Already late: <span className="num">{rupees(k.receivables_overdue)}</span></span>} />
              <Kpi label="We owe suppliers" value={k.payables} href="/outstanding?tab=payable" sub="Money still to pay"
                foot={<span className={num(k.payables_overdue) > 0 ? "font-medium text-bad" : ""}>Already late: <span className="num">{rupees(k.payables_overdue)}</span></span>} />
              <Kpi label="Cash and bank now" value={k.cash_bank} href="/reports?r=bank-book" sub={`In ${data.banks.length} accounts`}
                foot={<>Cash in hand: <span className="num font-semibold text-ink">{rupees(k.cash_only)}</span></>} />
            </div>

            <div className="mt-6 grid gap-6 xl:grid-cols-3">
              <Card className="xl:col-span-2" title="Sales and spending, month by month (this year)">
                <div className="mb-3 flex flex-wrap gap-5 text-base text-ink">
                  <span className="flex items-center gap-2"><span className="h-3.5 w-3.5 rounded-sm" style={{ background: SALES }} />Green bars = Sales</span>
                  <span className="flex items-center gap-2"><span className="h-1 w-5 rounded" style={{ background: COSTS }} />Orange line = Purchases + expenses</span>
                </div>
                <div className="h-72">
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={trend} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
                      <CartesianGrid vertical={false} stroke="#e3e9e5" />
                      <XAxis dataKey="month" tickLine={false} axisLine={{ stroke: "#dce4df" }} tick={{ fontSize: 14, fill: "#4f5d56" }} />
                      <YAxis tickLine={false} axisLine={false} width={72} tick={{ fontSize: 14, fill: "#4f5d56" }} tickFormatter={(v) => inrShort(v)} />
                      <Tooltip content={<TrendTooltip />} cursor={{ fill: "rgba(220,228,223,0.45)" }} />
                      <Bar dataKey="sales" fill={SALES} maxBarSize={28} radius={[4, 4, 0, 0]} />
                      <Line dataKey="costs" stroke={COSTS} strokeWidth={2.5} dot={{ r: 4.5, strokeWidth: 2, stroke: "#fff", fill: COSTS }} activeDot={{ r: 6 }} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
                <p className="mt-2 text-sm text-muted">Point at a bar to see the exact amounts. &quot;L&quot; means lakh (1 L = ₹1,00,000).</p>
              </Card>

              <Card title="Cash and bank balances">
                <ul className="divide-y divide-line">
                  {data.banks.map((b) => (
                    <li key={b.id} className="flex items-center gap-3 py-3.5 first:pt-0">
                      <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-soft-2 text-accent-strong">
                        {b.kind === "cash" ? <Wallet className="h-5 w-5" /> : <Landmark className="h-5 w-5" />}
                      </span>
                      <span className="min-w-0 flex-1 text-base">{b.name}</span>
                      <span className={cx("num text-base font-semibold", num(b.balance) < 0 && "text-bad")}>{inr(b.balance)}</span>
                    </li>
                  ))}
                </ul>
                <div className="mt-3 flex items-center justify-between border-t-2 border-soft pt-3 text-lg font-semibold">
                  <span>Total</span><span className="num">{inr(k.cash_bank)}</span>
                </div>
              </Card>
            </div>

            <div className="mt-6 grid gap-6 xl:grid-cols-3">
              <Card title="Money dealers owe us — how late?">
                <AgeingBars rows={data.receivable_ageing} />
                <Link href="/outstanding" className="mt-5 inline-block text-base font-medium text-accent-strong hover:underline">See dealer-wise list →</Link>
              </Card>

              <Card title="Dealers who are late paying" pad={false}>
                {data.overdue_dealers.length ? (
                  <ul className="divide-y divide-line">
                    {data.overdue_dealers.map((p) => (
                      <li key={p.party_id}>
                        <Link href={`/outstanding/${p.party_id}`} className="flex items-center gap-3 px-5 py-3.5 hover:bg-soft-2">
                          <span className="min-w-0 flex-1">
                            <span className="block text-base font-medium">{p.party_name}</span>
                            <span className="text-sm text-bad">Oldest bill is {p.oldest_overdue_days} days late</span>
                          </span>
                          <span className="num text-base font-semibold">{rupees(p.net)}</span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : <div className="flex items-center gap-2 px-5 py-8 text-base text-ok"><CheckCircle2 className="h-5 w-5" />No dealer is late. </div>}
              </Card>

              <Card title="Supplier bills to pay this week" pad={false}>
                {data.upcoming_payments.length ? (
                  <ul className="divide-y divide-line">
                    {data.upcoming_payments.map((b) => (
                      <li key={b.id}>
                        <Link href={`/purchases/${b.id}`} className="flex items-center gap-3 px-5 py-3.5 hover:bg-soft-2">
                          <span className="min-w-0 flex-1">
                            <span className="block text-base font-medium">{b.party_name}</span>
                            <span className="text-sm text-muted">Bill {b.supplier_bill_no} · pay by {d(b.due_date)}</span>
                          </span>
                          <span className="num text-base font-semibold">{rupees(b.balance)}</span>
                        </Link>
                      </li>
                    ))}
                  </ul>
                ) : <div className="px-5 py-8 text-base text-muted">Nothing to pay in the next 7 days.</div>}
              </Card>
            </div>

            <Card className="mt-6" title="Last entries made" pad={false}>
              <ul className="divide-y divide-line">
                {data.recent.map((r, i) => (
                  <li key={i}>
                    <Link href={(TYPE_HREF[r.type] ?? (() => "/"))(r.source_id)} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-5 py-3 text-base hover:bg-soft-2">
                      <span className="w-28 text-muted">{d(r.date)}</span>
                      <span className="w-36 font-medium text-accent-strong"><ReceiptText className="mr-1 inline h-4 w-4" />{TYPE_LABEL[r.type] ?? r.type}{r.is_reversal ? " (undone)" : ""}</span>
                      <span className="min-w-0 flex-1 truncate">{r.narration}</span>
                      <span className="num font-semibold">{inr(r.amount)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>
          </>
        );
      })()}
    </>
  );
}
