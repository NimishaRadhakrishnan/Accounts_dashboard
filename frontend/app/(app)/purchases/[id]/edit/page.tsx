"use client";

import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { put } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { DocForm, fromServer, toPayload } from "@/components/doc-form";
import { ErrorBox, Notice, PageHeader, Spinner, useToast } from "@/components/ui";

export default function EditBillPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const toast = useToast();
  const { data, error: loadErr } = useApi<Parameters<typeof fromServer>[0] & { number: string | null; status: string; supplier_bill_no: string }>(`/api/purchase-bills/${id}`);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (loadErr) return <ErrorBox message={loadErr} />;
  if (!data) return <Spinner />;
  return (
    <>
      <PageHeader title={`Edit bill ${data.supplier_bill_no}`} />
      {data.status === "posted" && <div className="mb-4"><Notice tone="warn">This bill is already final. When you save, the old figures are replaced by the new ones. The change is recorded.</Notice></div>}
      <DocForm kind="purchase" initial={fromServer(data)} busy={busy} error={error} submitLabels={{ post: "Save changes" }}
        onSubmit={async (doc) => {
          setBusy(true);
          setError(null);
          try {
            await put(`/api/purchase-bills/${id}`, { ...toPayload(doc), supplier_bill_no: doc.reference.trim() });
            toast("Changes saved.");
            router.push(`/purchases/${id}`);
          } catch (e) {
            setError((e as Error).message);
            setBusy(false);
          }
        }} />
    </>
  );
}
