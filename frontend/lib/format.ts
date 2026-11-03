// Money comes from the API as exact strings ("12345.50"). These helpers only format for display.

export type Money = string | number | null | undefined;

export function num(v: Money): number {
  if (v === null || v === undefined || v === "") return 0;
  return typeof v === "number" ? v : Number(v);
}

const inrFmt = new Intl.NumberFormat("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const inr0 = new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 });

/** ₹12,34,567.00 */
export function inr(v: Money, opts: { symbol?: boolean; blankZero?: boolean } = {}): string {
  const n = num(v);
  if (opts.blankZero && n === 0) return "";
  const s = inrFmt.format(Math.abs(n));
  return `${n < 0 ? "−" : ""}${opts.symbol === false ? "" : "₹"}${s}`;
}

/** Compact for KPI cards: ₹12.4 L, ₹1.03 Cr */
export function inrShort(v: Money): string {
  const n = num(v);
  const a = Math.abs(n);
  const sign = n < 0 ? "−" : "";
  if (a >= 1e7) return `${sign}₹${(a / 1e7).toFixed(2)} Cr`;
  if (a >= 1e5) return `${sign}₹${(a / 1e5).toFixed(2)} L`;
  return `${sign}₹${inr0.format(a)}`;
}

export function d(v: string | null | undefined): string {
  if (!v) return "";
  const [y, m, day] = v.slice(0, 10).split("-");
  return `${day}-${m}-${y}`;
}

export function dt(v: string | null | undefined): string {
  if (!v) return "";
  return new Date(v).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" });
}

export function today(): string {
  const t = new Date();
  const off = t.getTimezoneOffset();
  return new Date(t.getTime() - off * 60000).toISOString().slice(0, 10);
}

export function monthStart(): string {
  return today().slice(0, 8) + "01";
}

/** Indian financial year containing a date: 1 Apr – 31 Mar */
export function fyRange(on: string = today()): { from: string; to: string } {
  const [y, m] = on.split("-").map(Number);
  const start = m >= 4 ? y : y - 1;
  return { from: `${start}-04-01`, to: `${start + 1}-03-31` };
}

export function pct(a: Money, b: Money): number | null {
  const x = num(a);
  const y = num(b);
  if (!y) return null;
  return ((x - y) / Math.abs(y)) * 100;
}

export const MODES = [
  { value: "neft", label: "NEFT" },
  { value: "rtgs", label: "RTGS" },
  { value: "imps", label: "IMPS" },
  { value: "upi", label: "UPI" },
  { value: "cheque", label: "Cheque" },
  { value: "cash", label: "Cash" },
];

export const GST_RATES = ["0", "5", "12", "18", "28"];

export const STATES: { code: string; name: string }[] = [
  { code: "33", name: "Tamil Nadu" }, { code: "32", name: "Kerala" }, { code: "29", name: "Karnataka" },
  { code: "36", name: "Telangana" }, { code: "37", name: "Andhra Pradesh" }, { code: "34", name: "Puducherry" },
  { code: "27", name: "Maharashtra" }, { code: "24", name: "Gujarat" }, { code: "07", name: "Delhi" },
  { code: "09", name: "Uttar Pradesh" }, { code: "19", name: "West Bengal" }, { code: "21", name: "Odisha" },
  { code: "30", name: "Goa" }, { code: "23", name: "Madhya Pradesh" }, { code: "08", name: "Rajasthan" },
  { code: "06", name: "Haryana" }, { code: "03", name: "Punjab" }, { code: "10", name: "Bihar" },
];

/** Whole rupees for headline numbers: ₹8,90,170 (easier to read than ₹8.90 L for most people). */
export function rupees(v: Money): string {
  const n = Math.round(num(v));
  return `${n < 0 ? "−" : ""}₹${inr0.format(Math.abs(n))}`;
}

/** For headline numbers: ₹26.80 lakh, ₹1.60 crore, ₹49,287 — how people in India say amounts. */
export function money(v: Money): string {
  const n = num(v);
  const a = Math.abs(n);
  const sign = n < 0 ? "−" : "";
  if (a >= 1e7) return `${sign}₹${(a / 1e7).toFixed(2)} crore`;
  if (a >= 1e5) return `${sign}₹${(a / 1e5).toFixed(2)} lakh`;
  return `${sign}₹${inr0.format(Math.round(a))}`;
}

export function ago(minutes: number | null | undefined): string {
  if (minutes === null || minutes === undefined) return "not yet";
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} minute${minutes === 1 ? "" : "s"} ago`;
  const h = Math.floor(minutes / 60);
  if (h < 24) return `${h} hour${h === 1 ? "" : "s"} ago`;
  const days = Math.floor(h / 24);
  return `${days} day${days === 1 ? "" : "s"} ago`;
}
