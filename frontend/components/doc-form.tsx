"use client";

import { Plus, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";
import { inr, GST_RATES, today } from "@/lib/format";
import { PartyPicker, useList, type PartyLite, type ProductLite } from "./pickers";
import { Button, Card, Field, Input, MissingList, Notice, Select, Textarea } from "./ui";

function Step({ n, title }: { n: number; title: string }) {
  return (
    <div className="flex items-center gap-3">
      <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-sidebar text-lg font-semibold text-white">{n}</span>
      <span className="text-xl font-semibold">{title}</span>
    </div>
  );
}

export type LineDraft = {
  key: number; product_id: number | null; description: string; hsn_code: string; qty: string; unit: string;
  rate: string; discount_pct: string; gst_rate: string;
};

export type DocDraft = {
  party_id: number | null; date: string; due_date: string; reference: string; notes: string; lines: LineDraft[];
};

let K = 1;
export const blankLine = (): LineDraft => ({ key: K++, product_id: null, description: "", hsn_code: "", qty: "", unit: "Nos", rate: "", discount_pct: "0", gst_rate: "5" });
export const blankDoc = (): DocDraft => ({ party_id: null, date: today(), due_date: "", reference: "", notes: "", lines: [blankLine()] });

// Display-only preview. The server recalculates everything with exact decimals when saving.
const r2 = (x: number) => Math.sign(x) * Math.round((Math.abs(x) + Number.EPSILON) * 100) / 100;

export function preview(lines: LineDraft[], inter: boolean) {
  let taxable = 0, cgst = 0, sgst = 0, igst = 0, discount = 0;
  const rows = lines.map((l) => {
    const gross = r2((Number(l.qty) || 0) * (Number(l.rate) || 0));
    const disc = r2((gross * (Number(l.discount_pct) || 0)) / 100);
    const tx = gross - disc;
    const rate = Number(l.gst_rate) || 0;
    const c = inter ? 0 : r2((tx * rate) / 200);
    const i = inter ? r2((tx * rate) / 100) : 0;
    taxable += tx; cgst += c; sgst += c; igst += i; discount += disc;
    return tx + c + c + i;
  });
  const before = taxable + cgst + sgst + igst;
  const grand = Math.round(before);
  return { rows, taxable, cgst, sgst, igst, discount, roundOff: grand - before, grand };
}

export function DocForm({ kind, initial, onSubmit, submitLabels, busy, error, warn, note, submitHelp }: {
  kind: "sales" | "purchase";
  /** Credit/debit note mode: party is fixed, no due date or reference. */
  note?: boolean;
  initial: DocDraft;
  onSubmit: (d: DocDraft, action: "draft" | "post") => void;
  submitLabels: { draft?: string; post?: string };
  /** One line under the save buttons explaining what saving does. */
  submitHelp?: string;
  busy: boolean;
  error: string | null;
  warn?: string | null;
}) {
  const [doc, setDoc] = useState<DocDraft>(initial);
  const parties = useList<PartyLite>(`/api/parties?kind=${kind === "sales" ? "customer" : "supplier"}&active=true`);
  const party = parties.find((x) => x.id === doc.party_id) ?? null;
  const products = useList<ProductLite>("/api/products?active=true");
  const inter = party ? party.state_code !== "33" : false;
  const p = useMemo(() => preview(doc.lines, inter), [doc.lines, inter]);

  const setLine = (key: number, patch: Partial<LineDraft>) =>
    setDoc((d) => ({ ...d, lines: d.lines.map((l) => (l.key === key ? { ...l, ...patch } : l)) }));

  const pickProduct = (key: number, id: string) => {
    const prod = products.find((x) => x.id === Number(id));
    if (!prod) return setLine(key, { product_id: null });
    setLine(key, {
      product_id: prod.id, description: prod.name, hsn_code: prod.hsn_code ?? "", unit: prod.unit,
      gst_rate: String(Number(prod.gst_rate)),
      rate: String(Number(kind === "sales" ? prod.sale_price : prod.purchase_price) || ""),
    });
  };

  const [tried, setTried] = useState(false);
  const who = kind === "sales" ? "dealer" : "supplier";
  const missing: string[] = [];
  if (!doc.party_id) missing.push(`Choose the ${who} (step 1)`);
  if (!doc.date) missing.push("Fill in the date");
  if (kind === "purchase" && !note && !doc.reference.trim()) missing.push("Type the supplier's bill number (step 1)");
  doc.lines.forEach((l, i) => {
    const n = doc.lines.length > 1 ? ` on line ${i + 1}` : "";
    if (!l.description.trim()) missing.push(kind === "sales" ? `Choose a product${n}` : `Type what was bought${n}`);
    if (!(Number(l.qty) > 0)) missing.push(`Type the quantity${n}`);
    if (l.rate === "" || Number(l.rate) < 0) missing.push(`Type the rate${n}`);
  });
  const bad = (cond: boolean) => (tried && cond ? "border-bad bg-bad-bg/40" : "");

  const submit = (action: "draft" | "post") => {
    setTried(true);
    if (missing.length) return;
    onSubmit(doc, action);
  };

  return (
    <form onSubmit={(e) => { e.preventDefault(); submit("post"); }} className="space-y-6" noValidate>
      <Card>
        <div className="mb-5"><Step n={1} title={note ? "Date of this note" : kind === "sales" ? "Who is this invoice for?" : "Which supplier sent this bill?"} /></div>
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
          <Field label={kind === "sales" ? "Dealer" : "Supplier"} required className="md:col-span-2"
            hint={note ? undefined : "Click the box, then type a few letters of the name"}
            error={tried && !doc.party_id ? `Please choose the ${who}` : null}>
            <PartyPicker disabled={note} kind={kind === "sales" ? "customer" : "supplier"} value={doc.party_id}
              onChange={(pt) => setDoc((d) => ({ ...d, party_id: pt?.id ?? null }))} />
          </Field>
          <Field label={note ? "Date" : kind === "sales" ? "Invoice date" : "Date on the bill"} required>
            <Input type="date" value={doc.date} onChange={(e) => setDoc({ ...doc, date: e.target.value })} />
          </Field>
          {!note && <Field label="Payment due by" hint={party ? `Leave empty to use ${party.credit_days} days credit` : "Leave empty to use the usual credit days"}>
            <Input type="date" value={doc.due_date} min={doc.date} onChange={(e) => setDoc({ ...doc, due_date: e.target.value })} />
          </Field>}
          {!note && <Field label={kind === "sales" ? "Dealer's order number (if any)" : "Supplier's bill number"} required={kind === "purchase"}
            error={tried && kind === "purchase" && !doc.reference.trim() ? "Please type the bill number" : null}>
            <Input value={doc.reference} maxLength={kind === "sales" ? 60 : 40} onChange={(e) => setDoc({ ...doc, reference: e.target.value })} className={bad(kind === "purchase" && !doc.reference.trim())} />
          </Field>}
          {party && (
            <div className="rounded-lg bg-soft-2 px-4 py-3 text-base md:col-span-2 xl:col-span-4">
              <span className="font-medium">{party.name}</span> · {party.state_name} · {party.gstin ? `GSTIN ${party.gstin}` : "No GSTIN (unregistered)"}
              <br />
              <span className="text-muted">Tax will be </span>
              <span className="font-medium">{inter ? "IGST, because they are in another state" : "CGST + SGST, because they are in Tamil Nadu"}</span>
              {kind === "sales" && Number(party.credit_limit) > 0 && (
                <><br /><span className="text-muted">They already owe us {inr(party.balance)} · their limit is {inr(party.credit_limit)}</span></>
              )}
            </div>
          )}
        </div>
      </Card>

      <Card pad={false}>
        <div className="px-5 pt-5"><Step n={2} title={kind === "sales" ? "What was sold?" : "What was bought?"} /></div>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[1040px] text-base">
            <thead>
              <tr className="border-y-2 border-line bg-soft-2 text-left text-sm font-semibold text-ink">
                <th className="w-10 px-4 py-3">No.</th>
                <th className="min-w-72 px-2 py-3">{kind === "sales" ? "Product" : "Item"}</th>
                <th className="w-28 px-2 py-3 text-right">Quantity</th>
                <th className="w-36 px-2 py-3 text-right">Rate for one<br /><span className="font-normal text-muted">₹, before GST</span></th>
                <th className="w-24 px-2 py-3 text-right">Discount<br /><span className="font-normal text-muted">%</span></th>
                <th className="w-32 px-2 py-3 text-right">GST<br /><span className="font-normal text-muted">%</span></th>
                <th className="w-36 px-4 py-3 text-right">Amount<br /><span className="font-normal text-muted">with GST</span></th>
                <th className="w-28" />
              </tr>
            </thead>
            <tbody>
              {doc.lines.map((l, i) => (
                <tr key={l.key} className="border-b border-line align-top">
                  <td className="px-4 pt-5 text-lg font-medium text-muted">{i + 1}</td>
                  <td className="px-2 py-3">
                    <div className="space-y-2">
                      <Select value={l.product_id ?? ""} onChange={(e) => pickProduct(l.key, e.target.value)} aria-label={`Product on line ${i + 1}`}
                        className={bad(kind === "sales" && !l.description.trim())}>
                        <option value="">{kind === "sales" ? "— Choose product —" : "— Not in the list (type below) —"}</option>
                        {products.map((pr) => <option key={pr.id} value={pr.id}>{pr.name}</option>)}
                      </Select>
                      {(kind === "purchase" || l.product_id) && (
                        <Input value={l.description} placeholder="What was bought" maxLength={300} onChange={(e) => setLine(l.key, { description: e.target.value })}
                          aria-label={`Description on line ${i + 1}`} className={bad(!l.description.trim())} />
                      )}
                      <div className="flex flex-wrap items-center gap-3 text-sm text-muted">
                        <label className="flex items-center gap-1.5">HSN
                          <input value={l.hsn_code} maxLength={8} onChange={(e) => setLine(l.key, { hsn_code: e.target.value.replace(/\D/g, "") })}
                            className="h-9 w-24 rounded-md border-2 border-soft px-2 text-sm text-ink" aria-label={`HSN code on line ${i + 1}`} />
                        </label>
                        <label className="flex items-center gap-1.5">Unit
                          <input value={l.unit} maxLength={20} onChange={(e) => setLine(l.key, { unit: e.target.value })}
                            className="h-9 w-20 rounded-md border-2 border-soft px-2 text-sm text-ink" aria-label={`Unit on line ${i + 1}`} />
                        </label>
                      </div>
                    </div>
                  </td>
                  <td className="px-2 py-3"><Input type="number" inputMode="decimal" step="0.001" min="0" value={l.qty} onChange={(e) => setLine(l.key, { qty: e.target.value })} aria-label={`Quantity on line ${i + 1}`} className={bad(!(Number(l.qty) > 0))} /></td>
                  <td className="px-2 py-3"><Input type="number" inputMode="decimal" step="0.01" min="0" value={l.rate} onChange={(e) => setLine(l.key, { rate: e.target.value })} aria-label={`Rate on line ${i + 1}`} className={bad(l.rate === "")} /></td>
                  <td className="px-2 py-3"><Input type="number" inputMode="decimal" step="0.01" min="0" max="100" value={l.discount_pct} onChange={(e) => setLine(l.key, { discount_pct: e.target.value })} aria-label={`Discount percent on line ${i + 1}`} /></td>
                  <td className="px-2 py-3">
                    <Select value={l.gst_rate} onChange={(e) => setLine(l.key, { gst_rate: e.target.value })} aria-label={`GST percent on line ${i + 1}`}>
                      {GST_RATES.map((g) => <option key={g} value={g}>{g}%</option>)}
                    </Select>
                  </td>
                  <td className="num px-4 pt-5 text-right text-lg font-semibold">{inr(p.rows[i])}</td>
                  <td className="pr-4 pt-3 text-right">
                    {doc.lines.length > 1 && (
                      <button type="button" onClick={() => setDoc((d) => ({ ...d, lines: d.lines.filter((x) => x.key !== l.key) }))}
                        className="inline-flex min-h-10 items-center gap-1.5 rounded-lg border-2 border-bad/30 px-2.5 text-sm font-medium text-bad hover:bg-bad-bg" aria-label={`Remove line ${i + 1}`}>
                        <Trash2 className="h-4 w-4" />Remove
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="px-5 py-4">
          <Button icon={<Plus className="h-5 w-5" />} onClick={() => setDoc((d) => ({ ...d, lines: [...d.lines, blankLine()] }))}>Add another item</Button>
        </div>
      </Card>

      <Card>
        <div className="mb-5"><Step n={3} title="Check the total and save" /></div>
        <div className="flex flex-col gap-6 lg:flex-row lg:justify-between">
          <Field label="Note for our office (not printed)" className="max-w-lg flex-1">
            <Textarea value={doc.notes} onChange={(e) => setDoc({ ...doc, notes: e.target.value })} rows={3} />
          </Field>
          <dl className="w-full space-y-2 text-base lg:w-96">
            {p.discount > 0 && <Row k="Discount given" v={inr(p.discount)} />}
            <Row k="Amount before GST" v={inr(p.taxable)} />
            {inter ? <Row k="IGST" v={inr(p.igst)} /> : <><Row k="CGST" v={inr(p.cgst)} /><Row k="SGST" v={inr(p.sgst)} /></>}
            {Math.abs(p.roundOff) > 0.001 && <Row k="Rounded off" v={inr(p.roundOff)} />}
            <div className="flex justify-between rounded-lg bg-sidebar px-4 py-3 text-xl font-semibold text-white"><dt>Total</dt><dd className="num">{inr(p.grand)}</dd></div>
          </dl>
        </div>
      </Card>

      {tried && <MissingList items={missing} />}
      {warn && <Notice tone="warn">{warn}</Notice>}
      {error && <Notice tone="bad">{error}</Notice>}
      <div className="flex flex-col items-end gap-2">
        <div className="flex flex-wrap justify-end gap-3">
          {submitLabels.draft && <Button size="lg" busy={busy} onClick={() => submit("draft")}>{submitLabels.draft}</Button>}
          {submitLabels.post && <Button size="lg" type="submit" variant="primary" busy={busy}>{submitLabels.post}</Button>}
        </div>
        {submitHelp && <p className="max-w-xl text-right text-sm text-muted">{submitHelp}</p>}
      </div>
    </form>
  );
}

function Row({ k, v }: { k: string; v: string }) {
  return <div className="flex justify-between px-1 text-muted"><dt>{k}</dt><dd className="num text-ink">{v}</dd></div>;
}

export function toPayload(d: DocDraft) {
  return {
    party_id: d.party_id, date: d.date, due_date: d.due_date || null, notes: d.notes || null,
    lines: d.lines.map((l) => ({
      product_id: l.product_id, description: l.description.trim(), hsn_code: l.hsn_code || null, qty: l.qty,
      unit: l.unit || "Nos", rate: l.rate, discount_pct: l.discount_pct || "0", gst_rate: l.gst_rate,
    })),
  };
}

type ServerLine = { product_id: number | null; description: string; hsn_code: string | null; qty: string; unit: string; rate: string; discount_pct: string; gst_rate: string };
export function fromServer(doc: { party: { id: number }; date: string; due_date: string; notes: string | null; reference?: string | null; supplier_bill_no?: string; lines: ServerLine[] }): DocDraft {
  return {
    party_id: doc.party.id, date: doc.date, due_date: doc.due_date, notes: doc.notes ?? "",
    reference: doc.supplier_bill_no ?? doc.reference ?? "",
    lines: doc.lines.map((l) => ({
      key: K++, product_id: l.product_id, description: l.description, hsn_code: l.hsn_code ?? "",
      qty: String(Number(l.qty)), unit: l.unit, rate: String(Number(l.rate)),
      discount_pct: String(Number(l.discount_pct)), gst_rate: String(Number(l.gst_rate)),
    })),
  };
}
