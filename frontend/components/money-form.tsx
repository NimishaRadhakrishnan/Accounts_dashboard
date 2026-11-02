"use client";

import { useEffect, useMemo, useState } from "react";
import { get, post } from "@/lib/api";
import { d, inr, num, today } from "@/lib/format";
import { BankSelect, PartyPicker, useList, type BankLite } from "./pickers";
import { Button, Field, Input, MissingList, Modal, Notice, Textarea, cx } from "./ui";

export type OpenItem = { id: number; number: string; supplier_bill_no: string | null; date: string; due_date: string; total: string; balance: string; overdue_days: number };

/** Spread an amount over open items, oldest due first. */
export function fifoAlloc(items: OpenItem[], amount: number): Record<number, string> {
  let left = amount;
  const a: Record<number, string> = {};
  for (const it of items) {
    if (left <= 0) break;
    const take = Math.min(num(it.balance), left);
    a[it.id] = take.toFixed(2);
    left = Math.round((left - take) * 100) / 100;
  }
  return a;
}

/** Which invoices/bills this money is for. Filled in automatically (oldest first); can be changed. */
export function AllocGrid({ items, alloc, setAlloc, amount, isR = true }: {
  items: OpenItem[]; alloc: Record<number, string>; setAlloc: (a: Record<number, string>) => void; amount: number; isR?: boolean;
}) {
  const used = Object.values(alloc).reduce((s, v) => s + (Number(v) || 0), 0);
  const fifo = () => setAlloc(fifoAlloc(items, amount));
  const doc = isR ? "invoice" : "bill";
  if (!items.length) return <Notice>There is no unpaid {doc} for them. The whole amount will be kept as an advance.</Notice>;
  return (
    <div className="rounded-lg border-2 border-line">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-soft-2 px-4 py-3">
        <span className="text-base font-semibold">Which {doc}s is this money for?</span>
        <span className="flex gap-2">
          <Button size="sm" onClick={fifo}>Fill oldest first</Button>
          <Button size="sm" variant="ghost" onClick={() => setAlloc({})}>Clear all</Button>
        </span>
      </div>
      <p className="px-4 pt-3 text-sm text-muted">We have filled this in for you, starting with the oldest {doc}. Change the amounts only if the {isR ? "dealer" : "supplier"} said otherwise.</p>
      <div className="max-h-72 overflow-y-auto">
        <table className="w-full text-base">
          <thead><tr className="text-left text-sm text-muted"><th className="px-4 py-2 font-medium">{isR ? "Invoice" : "Bill"}</th><th className="px-4 py-2 text-right font-medium">Unpaid</th><th className="px-4 py-2 text-right font-medium">Pay now ₹</th></tr></thead>
          <tbody>
            {items.map((it) => (
              <tr key={it.id} className="border-t border-line">
                <td className="px-4 py-2.5">
                  <span className="font-medium">{it.supplier_bill_no ?? it.number}</span>
                  <span className="block text-sm text-muted">dated {d(it.date)}{it.overdue_days > 0 && <span className="font-medium text-bad"> · {it.overdue_days} days late</span>}</span>
                </td>
                <td className="num px-4 py-2.5 text-right">{inr(it.balance)}</td>
                <td className="w-40 px-4 py-2.5">
                  <Input type="number" inputMode="decimal" step="0.01" min="0" max={num(it.balance)} value={alloc[it.id] ?? ""} placeholder="0"
                    onChange={(e) => setAlloc({ ...alloc, [it.id]: e.target.value })} aria-label={`Amount for ${it.supplier_bill_no ?? it.number}`} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className={cx("flex flex-wrap justify-between gap-2 border-t-2 border-line px-4 py-3 text-base", used > amount + 0.001 ? "font-semibold text-bad" : "text-ink")}>
        <span>Linked to {doc}s: <span className="num font-semibold">{inr(used)}</span> of <span className="num">{inr(amount)}</span></span>
        <span>{used > amount + 0.001 ? `This is more than the amount received — please reduce it` : `Kept as advance: ${inr(Math.max(0, amount - used))}`}</span>
      </div>
    </div>
  );
}

const MODE_CHOICES = [
  { value: "neft", label: "Bank transfer", sub: "NEFT / RTGS / IMPS" },
  { value: "upi", label: "UPI", sub: "GPay, PhonePe…" },
  { value: "cheque", label: "Cheque", sub: "" },
  { value: "cash", label: "Cash", sub: "" },
];

function ModePicker({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4" role="radiogroup" aria-label="How was it paid">
      {MODE_CHOICES.map((m) => (
        <button key={m.value} type="button" role="radio" aria-checked={value === m.value || (m.value === "neft" && ["rtgs", "imps"].includes(value))}
          onClick={() => onChange(m.value)}
          className={cx("min-h-14 rounded-lg border-2 px-3 py-2 text-left transition-colors",
            value === m.value ? "border-sidebar bg-sidebar text-white" : "border-soft bg-white text-ink hover:border-accent")}>
          <span className="block text-base font-semibold">{value === m.value ? "● " : "○ "}{m.label}</span>
          {m.sub && <span className={cx("block text-sm", value === m.value ? "text-white/80" : "text-muted")}>{m.sub}</span>}
        </button>
      ))}
    </div>
  );
}

/** Pick the only matching account automatically, so people are not asked an obvious question. */
function useAutoAccount(kind: "bank" | "cash", bank: number | "", setBank: (v: number | "") => void) {
  const banks = useList<BankLite>("/api/bank-accounts").filter((b) => b.is_active && b.kind === kind);
  useEffect(() => {
    if (bank === "" && banks.length === 1) setBank(banks[0].id);
  }, [banks, bank, setBank]);
}

export function MoneyModal({ kind, open, onClose, onDone }: { kind: "receipt" | "payment"; open: boolean; onClose: () => void; onDone: () => void }) {
  const isR = kind === "receipt";
  const [party, setParty] = useState<number | null>(null);
  const [date, setDate] = useState(today());
  const [bank, setBank] = useState<number | "">("");
  const [mode, setMode] = useState("neft");
  const [amount, setAmount] = useState("");
  const [ref, setRef] = useState("");
  const [notes, setNotes] = useState("");
  const [items, setItems] = useState<OpenItem[]>([]);
  const [alloc, setAlloc] = useState<Record<number, string>>({});
  const [touched, setTouched] = useState(false); // until the user edits, link oldest-first automatically
  const [tried, setTried] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setTouched(false); setTried(false);
    setParty(null); setDate(today()); setBank(""); setMode("neft"); setAmount(""); setRef(""); setNotes(""); setItems([]); setAlloc({}); setErr(null);
  }, [open]);
  useEffect(() => {
    if (!party) return setItems([]);
    get<OpenItem[]>(`/api/parties/${party}/${isR ? "open-invoices" : "open-bills"}`).then(setItems).catch(() => setItems([]));
    setTouched(false);
  }, [party, isR]);
  useAutoAccount(mode === "cash" ? "cash" : "bank", bank, setBank);

  const amt = Number(amount) || 0;
  useEffect(() => { if (!touched) setAlloc(fifoAlloc(items, amt)); }, [items, amt, touched]);
  const used = useMemo(() => Object.values(alloc).reduce((s, v) => s + (Number(v) || 0), 0), [alloc]);
  const who = isR ? "dealer" : "supplier";
  const missing = [
    !party && `Choose the ${who}`,
    !(amt > 0) && "Type the amount",
    !bank && (isR ? "Choose which account the money came into" : "Choose which account the money was paid from"),
    used > amt + 0.001 && "The amounts linked to bills are more than the total — please reduce them",
  ].filter(Boolean) as string[];

  async function save() {
    setTried(true);
    if (missing.length) return;
    setBusy(true); setErr(null);
    try {
      const allocations = Object.entries(alloc).filter(([, v]) => Number(v) > 0).map(([k, v]) => ({ doc_id: Number(k), amount: v }));
      await post(isR ? "/api/receipts" : "/api/payments", {
        party_id: party, date, bank_account_id: bank, amount, mode, reference: ref || null, notes: notes || null, allocations,
      });
      onDone();
      onClose();
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  }

  return (
    <Modal open={open} onClose={onClose} wide title={isR ? "A dealer paid us" : "We paid a supplier"}
      footer={<><Button onClick={onClose}>Close without saving</Button><Button variant="primary" size="lg" busy={busy} onClick={save}>Save</Button></>}>
      <div className="space-y-5">
        <Field label={isR ? "Which dealer paid?" : "Which supplier did we pay?"} required hint="Click the box, then type a few letters of the name"
          error={tried && !party ? `Please choose the ${who}` : null}>
          <PartyPicker kind={isR ? "customer" : "supplier"} value={party} onChange={(p) => setParty(p?.id ?? null)} />
        </Field>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="How much? (₹)" required error={tried && !(amt > 0) ? "Please type the amount" : null}>
            <Input type="number" inputMode="decimal" step="0.01" min="0" value={amount} onChange={(e) => setAmount(e.target.value)} className="min-h-13 text-xl" placeholder="0" />
          </Field>
          <Field label="On which date?" required><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="min-h-13" /></Field>
        </div>
        <div>
          <div className="mb-1.5 text-base font-medium">How was it paid?</div>
          <ModePicker value={mode} onChange={(v) => { setMode(v); setBank(""); }} />
        </div>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label={isR ? "Money came into" : "Money was paid from"} required error={tried && !bank ? "Please choose the account" : null}>
            <BankSelect value={bank} onChange={setBank} kind={mode === "cash" ? "cash" : "bank"} />
          </Field>
          {mode !== "cash" && <Field label={mode === "cheque" ? "Cheque number" : "UTR / reference number"} hint="Printed in the bank SMS or statement (optional)">
            <Input value={ref} maxLength={60} onChange={(e) => setRef(e.target.value)} />
          </Field>}
        </div>
        {party && amt > 0 && <AllocGrid isR={isR} items={items} alloc={alloc} setAlloc={(a) => { setTouched(true); setAlloc(a); }} amount={amt} />}
        <Field label="Note (optional)"><Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} /></Field>
        {!isR && <p className="text-sm text-muted">Large payments wait for a manager&apos;s approval before they count.</p>}
        {tried && <MissingList items={missing} />}
        {err && <Notice tone="bad">{err}</Notice>}
      </div>
    </Modal>
  );
}

export function TransferModal({ open, onClose, onDone }: { open: boolean; onClose: () => void; onDone: () => void }) {
  const [date, setDate] = useState(today());
  const [from, setFrom] = useState<number | "">("");
  const [to, setTo] = useState<number | "">("");
  const [amount, setAmount] = useState("");
  const [ref, setRef] = useState("");
  const [tried, setTried] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => { if (open) { setDate(today()); setFrom(""); setTo(""); setAmount(""); setRef(""); setErr(null); setTried(false); } }, [open]);
  const missing = [
    !from && "Choose where the money was taken from",
    !to && "Choose where the money was put",
    from && to && from === to && "“From” and “To” must be different accounts",
    !(Number(amount) > 0) && "Type the amount",
  ].filter(Boolean) as string[];
  return (
    <Modal open={open} onClose={onClose} title="Move money between cash and bank"
      footer={<><Button onClick={onClose}>Close without saving</Button><Button variant="primary" size="lg" busy={busy}
        onClick={async () => {
          setTried(true);
          if (missing.length) return;
          setBusy(true); setErr(null);
          try { await post("/api/contra", { date, from_account_id: from, to_account_id: to, amount, reference: ref || null }); onDone(); onClose(); }
          catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
        }}>Save</Button></>}>
      <div className="space-y-5">
        <Notice>Use this when cash is deposited in the bank, cash is withdrawn, or money moves between our own bank accounts.</Notice>
        <div className="grid gap-5 sm:grid-cols-2">
          <Field label="Taken from" required><BankSelect value={from} onChange={setFrom} /></Field>
          <Field label="Put into" required><BankSelect value={to} onChange={setTo} /></Field>
          <Field label="How much? (₹)" required><Input type="number" inputMode="decimal" step="0.01" min="0" value={amount} onChange={(e) => setAmount(e.target.value)} className="min-h-13 text-xl" /></Field>
          <Field label="Date" required><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} className="min-h-13" /></Field>
          <Field label="Note (optional)" className="sm:col-span-2" hint="For example: cash deposited at branch"><Input value={ref} onChange={(e) => setRef(e.target.value)} /></Field>
        </div>
        {tried && <MissingList items={missing} />}
        {err && <Notice tone="bad">{err}</Notice>}
      </div>
    </Modal>
  );
}
