"use client";

import { ChevronDown, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { get } from "@/lib/api";
import { cx, Select } from "./ui";

export type PartyLite = {
  id: number; code: string; name: string; gstin: string | null; state_name: string; state_code: string;
  city: string | null; credit_days: number; credit_limit: string; balance: string; is_active: boolean;
  is_customer: boolean; is_supplier: boolean;
};
export type ProductLite = { id: number; code: string; name: string; hsn_code: string | null; unit: string; gst_rate: string; sale_price: string; purchase_price: string; is_active: boolean };
export type BankLite = { id: number; name: string; kind: "bank" | "cash"; balance?: string; is_active: boolean };
export type CategoryLite = { id: number; name: string; is_active: boolean };

const cache = new Map<string, Promise<unknown>>();
function cached<T>(path: string, fresh = false): Promise<T> {
  if (fresh || !cache.has(path)) cache.set(path, get<T>(path).catch((e) => { cache.delete(path); throw e; }));
  return cache.get(path) as Promise<T>;
}
export function invalidateLists() { cache.clear(); }

export function useList<T>(path: string) {
  const [items, setItems] = useState<T[]>([]);
  useEffect(() => { cached<T[]>(path).then(setItems).catch(() => setItems([])); }, [path]);
  return items;
}

/** Searchable dropdown for dealers / suppliers. */
export function PartyPicker({ kind, value, onChange, disabled, placeholder }: {
  kind: "customer" | "supplier"; value: number | null; onChange: (p: PartyLite | null) => void; disabled?: boolean; placeholder?: string;
}) {
  const parties = useList<PartyLite>(`/api/parties?kind=${kind}&active=true`);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [hi, setHi] = useState(0);
  const box = useRef<HTMLDivElement>(null);
  const selected = parties.find((p) => p.id === value) ?? null;

  const list = useMemo(() => {
    const s = q.trim().toLowerCase();
    return parties.filter((p) => !s || p.name.toLowerCase().includes(s) || p.code.toLowerCase().includes(s) ||
      (p.city ?? "").toLowerCase().includes(s) || (p.gstin ?? "").toLowerCase().includes(s)).slice(0, 50);
  }, [parties, q]);

  useEffect(() => {
    const h = (e: MouseEvent) => { if (box.current && !box.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);

  const pick = (p: PartyLite) => { onChange(p); setOpen(false); setQ(""); };

  return (
    <div ref={box} className="relative">
      <button type="button" disabled={disabled} onClick={() => setOpen((o) => !o)}
        className="flex min-h-11 w-full items-center justify-between rounded-lg border-2 border-soft bg-white px-3.5 text-left text-base hover:border-accent focus:border-accent-strong focus:outline-none focus:ring-4 focus:ring-accent/20 disabled:bg-soft-2">
        <span className={cx("truncate", !selected && "text-muted")}>
          {selected ? `${selected.name} · ${selected.city ?? selected.state_name}` : placeholder ?? `Click here to choose the ${kind === "customer" ? "dealer" : "supplier"}`}
        </span>
        <ChevronDown className="h-5 w-5 shrink-0 text-ink" />
      </button>
      {open && (
        <div className="absolute z-40 mt-1 w-full min-w-72 overflow-hidden rounded-lg border border-soft bg-white shadow-lg">
          <div className="flex items-center gap-2 border-b border-line px-3">
            <Search className="h-4 w-4 text-muted" />
            <input autoFocus value={q} placeholder="Type a few letters of the name or town"
              onChange={(e) => { setQ(e.target.value); setHi(0); }}
              onKeyDown={(e) => {
                if (e.key === "ArrowDown") { e.preventDefault(); setHi((h) => Math.min(h + 1, list.length - 1)); }
                if (e.key === "ArrowUp") { e.preventDefault(); setHi((h) => Math.max(h - 1, 0)); }
                if (e.key === "Enter" && list[hi]) { e.preventDefault(); pick(list[hi]); }
                if (e.key === "Escape") setOpen(false);
              }}
              className="h-12 w-full text-base outline-none" />
          </div>
          <ul className="max-h-80 overflow-y-auto py-1">
            {list.map((p, i) => (
              <li key={p.id}>
                <button type="button" onMouseEnter={() => setHi(i)} onClick={() => pick(p)}
                  className={cx("flex w-full items-center justify-between gap-3 px-3 py-2.5 text-left text-base", i === hi && "bg-soft-2")}>
                  <span className="min-w-0">
                    <span className="block truncate font-medium">{p.name}</span>
                    <span className="block truncate text-sm text-muted">{p.city ?? ""}, {p.state_name}</span>
                  </span>
                  {p.state_code !== "33" && <span className="shrink-0 rounded bg-info-bg px-2 py-0.5 text-sm text-info">Other state</span>}
                </button>
              </li>
            ))}
            {!list.length && <li className="px-3 py-5 text-center text-base text-muted">No name matches “{q}”. Check the spelling, or add them in Settings.</li>}
          </ul>
        </div>
      )}
    </div>
  );
}

export function BankSelect({ value, onChange, kind, ...rest }: { value: number | ""; onChange: (id: number | "") => void; kind?: "bank" | "cash" } & Omit<React.SelectHTMLAttributes<HTMLSelectElement>, "value" | "onChange">) {
  const banks = useList<BankLite>("/api/bank-accounts").filter((b) => b.is_active && (!kind || b.kind === kind));
  return (
    <Select value={value} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : "")} {...rest}>
      <option value="">— Choose account —</option>
      {banks.map((b) => <option key={b.id} value={b.id}>{b.name}{b.kind === "cash" ? " (cash)" : ""}</option>)}
    </Select>
  );
}

export function CategorySelect({ value, onChange, allowAll, ...rest }: { value: number | ""; onChange: (id: number | "") => void; allowAll?: boolean } & Omit<React.SelectHTMLAttributes<HTMLSelectElement>, "value" | "onChange">) {
  const cats = useList<CategoryLite>("/api/expense-categories").filter((c) => c.is_active);
  return (
    <Select value={value} onChange={(e) => onChange(e.target.value ? Number(e.target.value) : "")} {...rest}>
      <option value="">{allowAll ? "All types" : "— Choose type of expense —"}</option>
      {cats.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
    </Select>
  );
}
