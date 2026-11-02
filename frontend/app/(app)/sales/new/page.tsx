"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { blankDoc, DocForm, toPayload } from "@/components/doc-form";
import { PageHeader, useToast } from "@/components/ui";

export default function NewInvoicePage() {
  const router = useRouter();
  const { can } = useAuth();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  return (
    <>
      <PageHeader title="Make a new invoice" subtitle="Fill the three steps below. The invoice number is given automatically when you save." />
      <DocForm kind="sales" initial={blankDoc()} busy={busy} error={error}
        submitLabels={{ draft: "Save for later (not final)", post: can("sales.post") ? "Save invoice" : undefined }}
        submitHelp="“Save invoice” gives it a number and adds it to the accounts. After that only the Accounts Manager can change it. “Save for later” keeps it as an unfinished draft you can change any time."
        onSubmit={async (doc, action) => {
          setBusy(true);
          setError(null);
          try {
            const inv = await api<{ id: number; number: string | null; warning: string | null }>(
              `/api/sales-invoices${action === "post" ? "?post=true" : ""}`,
              { method: "POST", body: { ...toPayload(doc), reference: doc.reference || null } });
            if (inv.warning) toast(inv.warning, "warn");
            toast(inv.number ? `Invoice ${inv.number} is saved. You can print it now.` : "Saved for later. You can find it in Sales & Invoices under “Not finished”.");
            router.push(`/sales/${inv.id}`);
          } catch (e) {
            setError((e as Error).message);
            setBusy(false);
          }
        }} />
    </>
  );
}
