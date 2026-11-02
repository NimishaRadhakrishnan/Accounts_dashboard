"use client";

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { put } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { DocForm, fromServer, toPayload } from "@/components/doc-form";
import { ErrorBox, Notice, PageHeader, Spinner, useToast } from "@/components/ui";

export default function EditInvoicePage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const toast = useToast();
  const { data, error: loadErr } = useApi<Parameters<typeof fromServer>[0] & { number: string | null; status: string }>(`/api/sales-invoices/${id}`);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (loadErr) return <ErrorBox message={loadErr} />;
  if (!data) return <Spinner />;
  return (
    <>
      <PageHeader title={`Edit ${data.number ?? "draft invoice"}`} />
      {data.status === "posted" && <div className="mb-4"><Notice tone="warn">This invoice is already final. When you save, the old figures are replaced by the new ones and the invoice keeps the same number. The change is recorded.</Notice></div>}
      <DocForm kind="sales" initial={fromServer(data)} busy={busy} error={error} submitLabels={{ post: "Save changes" }}
        onSubmit={async (doc) => {
          setBusy(true);
          setError(null);
          try {
            await put(`/api/sales-invoices/${id}`, { ...toPayload(doc), reference: doc.reference || null });
            toast("Changes saved.");
            router.push(`/sales/${id}`);
          } catch (e) {
            setError((e as Error).message);
            setBusy(false);
          }
        }} />
    </>
  );
}
