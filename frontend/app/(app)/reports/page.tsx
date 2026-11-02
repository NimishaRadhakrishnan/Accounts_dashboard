"use client";

import { FileCode2, FileDown, FileSpreadsheet } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { download, qs } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { d, fyRange, inr, monthStart, today } from "@/lib/format";
import { useApi, useQueryParam } from "@/lib/hooks";
import { BankSelect, PartyPicker } from "@/components/pickers";
import { Button, Card, cx, ErrorBox, Field, Input, Notice, PageHeader, Select, Spinner, useToast } from "@/components/ui";

type Cat = { key: string; title: string; group: string; needs: "period" | "as_of" | "party" | "bank" };
type Col = { key: string; label: string; kind: string };
type Rep = { title: string; subtitle: string; notes: string[]; columns: Col[]; rows: Record<string, unknown>[]; totals: Record<string, string> | null };

function lastMonth() {
  const t = new Date(today());
  const first = new Date(t.getFullYear(), t.getMonth() - 1, 1);
  const last = new Date(t.getFullYear(), t.getMonth(), 0);
  const iso = (x: Date) => `${x.getFullYear()}-${String(x.getMonth() + 1).padStart(2, "0")}-${String(x.getDate()).padStart(2, "0")}`;
  return { from: iso(first), to: iso(last) };
}

function cell(v: unknown, kind: string) {
  if (v === null || v === undefined || v === "") return "";
  if (kind === "money") return <span className={cx("num", Number(v) < 0 && "text-bad")}>{inr(v as string, { symbol: false })}</span>;
  if (kind === "date") return d(String(v));
  if (kind === "pct" || kind === "number") return <span className="num">{Number(v)}</span>;
  return String(v);
}

function partyKind(p: string | null): "customer" | "supplier" { return p === "supplier" ? "supplier" : "customer"; }

export default function ReportsPage() {
  const { can } = useAuth();
  const toast = useToast();
  const rParam = useQueryParam("r");
  const { data: cats } = useApi<Cat[]>("/api/reports");
  const [key, setKey] = useState("sales-register");
  useEffect(() => { if (rParam) setKey(rParam); }, [rParam]);
  const cat = cats?.find((c) => c.key === key);
  const [preset, setPreset] = useState("month");
  const [from, setFrom] = useState(monthStart());
  const [to, setTo] = useState(today());
  const [asOf, setAsOf] = useState(today());
  const [pk, setPk] = useState<string | null>("customer");
  const [party, setParty] = useState<number | null>(null);
  const [bank, setBank] = useState<number | "">("");
  const [run, setRun] = useState<string | null>(null);
  const [tFrom, setTFrom] = useState(monthStart());
  const [tTo, setTTo] = useState(today());

  const applyPreset = (p: string) => {
    setPreset(p);
    if (p === "month") { setFrom(monthStart()); setTo(today()); }
    if (p === "last") { const r = lastMonth(); setFrom(r.from); setTo(r.to); }
    if (p === "fy") { const r = fyRange(); setFrom(r.from); setTo(today() < r.to ? today() : r.to); }
  };

  const params = useMemo(() => {
    if (!cat) return null;
    if (cat.needs === "as_of") return qs({ as_of: asOf });
    if (cat.needs === "party") return party ? qs({ party_id: party, date_from: from, date_to: to }) : null;
    if (cat.needs === "bank") return bank ? qs({ bank_id: bank, date_from: from, date_to: to }) : null;
    return qs({ date_from: from, date_to: to });
  }, [cat, asOf, party, bank, from, to]);

  // Run automatically whenever the choice is complete.
  useEffect(() => { setRun(params ? `/api/reports/${key}${params}` : null); }, [key, params]);
  const rep = useApi<Rep>(run);

  const groups = useMemo(() => {
    const g: Record<string, Cat[]> = {};
    (cats ?? []).forEach((c) => (g[c.group] ??= []).push(c));
    return g;
  }, [cats]);

  const exp = (fmt: "xlsx" | "pdf") => params && download(`/api/reports/${key}/export${params}&fmt=${fmt}`, `${key}.${fmt}`).catch((e) => toast(e.message, "bad"));

  return (
    <>
      <PageHeader title="Financial Reports" subtitle="1. Choose a report on the left.  2. Choose the dates.  3. Check it on screen, then download it." />
      <div className="grid gap-6 lg:grid-cols-[240px_1fr]">
        <nav className="space-y-5">
          {Object.entries(groups).map(([g, list]) => (
            <div key={g}>
              <div className="mb-1.5 px-3 text-sm font-semibold text-muted">{g}</div>
              {list.map((c) => (
                <button key={c.key} onClick={() => setKey(c.key)}
                  className={cx("block w-full rounded-lg border-2 px-3 py-2.5 text-left text-base", key === c.key ? "border-sidebar bg-white font-semibold text-ink" : "border-transparent text-ink hover:border-soft hover:bg-white")}>
                  {c.title}
                </button>
              ))}
            </div>
          ))}
        </nav>

        <div className="min-w-0 space-y-6">
          <Card>
            <div className="flex flex-wrap items-end gap-4">
              {cat?.needs === "as_of" ? (
                <Field label="As on"><Input type="date" value={asOf} onChange={(e) => setAsOf(e.target.value)} /></Field>
              ) : <>
                {cat?.needs === "party" && <>
                  <Field label="Type"><Select value={pk ?? "customer"} onChange={(e) => { setPk(e.target.value); setParty(null); }}><option value="customer">Dealer</option><option value="supplier">Supplier</option></Select></Field>
                  <Field label={pk === "supplier" ? "Supplier" : "Dealer"} className="w-72"><PartyPicker kind={partyKind(pk)} value={party} onChange={(p) => setParty(p?.id ?? null)} /></Field>
                </>}
                {cat?.needs === "bank" && <Field label="Account" className="w-64"><BankSelect value={bank} onChange={setBank} /></Field>}
                <Field label="Period">
                  <Select value={preset} onChange={(e) => applyPreset(e.target.value)}>
                    <option value="month">This month</option><option value="last">Last month</option><option value="fy">This whole year (April onwards)</option><option value="custom">Choose my own dates</option>
                  </Select>
                </Field>
                <Field label="From"><Input type="date" value={from} onChange={(e) => { setFrom(e.target.value); setPreset("custom"); }} /></Field>
                <Field label="To"><Input type="date" value={to} onChange={(e) => { setTo(e.target.value); setPreset("custom"); }} /></Field>
              </>}
              {can("reports.export") && (
                <div className="ml-auto flex gap-2">
                  <Button disabled={!params} icon={<FileSpreadsheet className="h-5 w-5" />} onClick={() => exp("xlsx")}>Download Excel</Button>
                  <Button variant="primary" disabled={!params} icon={<FileDown className="h-5 w-5" />} onClick={() => exp("pdf")}>Download PDF</Button>
                </div>
              )}
            </div>
          </Card>

          <Card pad={false} title={rep.data ? <span>{rep.data.title} <span className="font-normal text-muted">· {rep.data.subtitle}</span></span> : cat?.title}>
            {!params ? <p className="p-5 text-base text-muted">Choose {cat?.needs === "bank" ? "a bank or cash account" : "a dealer or supplier"} above to see this report.</p>
              : rep.error ? <div className="p-4"><ErrorBox message={rep.error} /></div>
              : rep.loading || !rep.data ? <Spinner />
              : (
                <>
                  <div className="max-h-[65vh] overflow-auto">
                    <table className="w-full text-base">
                      <thead className="sticky top-0 z-10">
                        <tr className="border-b border-line bg-soft-2">
                          {rep.data.columns.map((c) => <th key={c.key} className={cx("whitespace-nowrap px-4 py-3 text-sm font-semibold text-ink", ["money", "number", "pct"].includes(c.kind) ? "text-right" : "text-left")}>{c.label}</th>)}
                        </tr>
                      </thead>
                      <tbody>
                        {rep.data.rows.map((r, i) => {
                          const strong = r.bold || r.type === "Opening" || r.type === "Closing" || String(r.section ?? "").match(/^(Total|Net)/);
                          return (
                            <tr key={i} className={cx("border-b border-line/70", strong && "bg-soft-2/60 font-semibold")}>
                              {rep.data!.columns.map((c) => <td key={c.key} className={cx("whitespace-nowrap px-4 py-2", ["money", "number", "pct"].includes(c.kind) ? "text-right" : "", c.key === "narration" && "max-w-md truncate text-muted")}>{cell(r[c.key], c.kind)}</td>)}
                            </tr>
                          );
                        })}
                        {!rep.data.rows.length && <tr><td colSpan={rep.data.columns.length} className="px-4 py-10 text-center text-muted">No entries for this period.</td></tr>}
                      </tbody>
                      {rep.data.totals && (
                        <tfoot className="sticky bottom-0 bg-soft font-semibold">
                          <tr>{rep.data.columns.map((c, i) => <td key={c.key} className={cx("px-4 py-2.5", c.kind === "money" && "text-right")}>{i === 0 ? "Total" : c.key in rep.data!.totals! ? cell(rep.data!.totals![c.key], c.kind) : ""}</td>)}</tr>
                        </tfoot>
                      )}
                    </table>
                  </div>
                  {rep.data.notes.length > 0 && <div className="space-y-1 border-t border-line px-5 py-3 text-xs text-muted">{rep.data.notes.map((n) => <p key={n}>{n}</p>)}</div>}
                </>
              )}
          </Card>

          {can("reports.export") && (
            <Card title="Send entries to Tally">
              <div className="flex flex-wrap items-end gap-4">
                <Field label="From"><Input type="date" value={tFrom} onChange={(e) => setTFrom(e.target.value)} /></Field>
                <Field label="To"><Input type="date" value={tTo} onChange={(e) => setTTo(e.target.value)} /></Field>
                <Button icon={<FileCode2 className="h-4 w-4" />} onClick={() => download(`/api/exports/tally${qs({ date_from: tFrom, date_to: tTo })}`, "tally.xml").then(() => toast("File for Tally downloaded.")).catch((e) => toast(e.message, "bad"))}>Download file for Tally</Button>
              </div>
              <div className="mt-4"><Notice>For the person who looks after Tally: in Tally go to Gateway of Tally → Import → Vouchers and choose this file. Ledger names must match Tally exactly (Settings → Tally ledgers). Try it first on a copy of the Tally company. Cancelled entries and old balances are not included.</Notice></div>
            </Card>
          )}
        </div>
      </div>
    </>
  );
}
