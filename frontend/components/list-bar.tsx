"use client";

import { Search, X } from "lucide-react";
import { Input, Select } from "./ui";

export type ListFilter = { q: string; status: string; date_from: string; date_to: string; page: number };
export const emptyFilter = (status = ""): ListFilter => ({ q: "", status, date_from: "", date_to: "", page: 1 });

/** Search and filter row. Every box has a visible label, and one button clears everything. */
export function ListBar({ f, setF, statuses, placeholder, children }: {
  f: ListFilter; setF: (f: ListFilter) => void; statuses?: { value: string; label: string }[]; placeholder?: string; children?: React.ReactNode;
}) {
  const filtered = !!(f.q || f.status || f.date_from || f.date_to);
  return (
    <div className="no-print flex flex-wrap items-end gap-3 border-b border-line px-4 py-4">
      <label className="w-full sm:w-80">
        <span className="mb-1.5 block text-sm font-medium">Search</span>
        <span className="relative block">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-5 w-5 -translate-y-1/2 text-muted" />
          <Input className="pl-10" placeholder={placeholder ?? "Number or name"} value={f.q} onChange={(e) => setF({ ...f, q: e.target.value, page: 1 })} />
        </span>
      </label>
      {statuses && (
        <label>
          <span className="mb-1.5 block text-sm font-medium">Show</span>
          <Select className="w-auto" value={f.status} onChange={(e) => setF({ ...f, status: e.target.value, page: 1 })}>
            <option value="">Everything</option>
            {statuses.map((s) => <option key={s.value} value={s.value}>{s.label}</option>)}
          </Select>
        </label>
      )}
      <label>
        <span className="mb-1.5 block text-sm font-medium">From date</span>
        <Input type="date" className="w-auto" value={f.date_from} onChange={(e) => setF({ ...f, date_from: e.target.value, page: 1 })} />
      </label>
      <label>
        <span className="mb-1.5 block text-sm font-medium">To date</span>
        <Input type="date" className="w-auto" value={f.date_to} onChange={(e) => setF({ ...f, date_to: e.target.value, page: 1 })} />
      </label>
      {children}
      {filtered && (
        <button onClick={() => setF({ ...f, q: "", status: "", date_from: "", date_to: "", page: 1 })}
          className="inline-flex min-h-11 items-center gap-1.5 rounded-lg px-3 text-base font-medium text-accent-strong underline underline-offset-4 hover:bg-soft-2">
          <X className="h-5 w-5" /> Clear search
        </button>
      )}
    </div>
  );
}
