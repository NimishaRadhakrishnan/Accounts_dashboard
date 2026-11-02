"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { post } from "@/lib/api";
import { blankDoc, DocForm, toPayload } from "@/components/doc-form";
import { PageHeader, useToast } from "@/components/ui";

export default function NewBillPage() {
  const router = useRouter();
  const toast = useToast();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const initial = blankDoc();
  initial.lines[0].gst_rate = "18";

  return (
    <>
      <PageHeader title="Enter a supplier bill" subtitle="Copy the details exactly as printed on the supplier's bill. You can attach a photo of the bill after saving." />
      <DocForm kind="purchase" initial={initial} busy={busy} error={error} submitLabels={{ post: "Save bill" }}
        submitHelp="After saving, another person (the Accounts Manager) checks it against the paper bill. It counts in the accounts only after that check."
        onSubmit={async (doc) => {
          setBusy(true);
          setError(null);
          try {
            const b = await post<{ id: number; status: string }>("/api/purchase-bills", { ...toPayload(doc), supplier_bill_no: doc.reference.trim() });
            toast(b.status === "posted" ? "Bill saved." : "Bill saved. It now waits for the Accounts Manager to check it.");
            router.push(`/purchases/${b.id}`);
          } catch (e) {
            setError((e as Error).message);
            setBusy(false);
          }
        }} />
    </>
  );
}
