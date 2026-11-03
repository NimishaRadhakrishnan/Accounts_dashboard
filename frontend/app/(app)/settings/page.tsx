"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { AuditTab, UsersTab } from "@/components/settings/admin";
import { TallyLinkTab } from "@/components/settings/tally-link";
import { PageHeader, Tabs } from "@/components/ui";

type T = "tally" | "users" | "audit";

export default function SettingsPage() {
  const { can } = useAuth();
  const items = ([
    { value: "tally", label: "Tally link", show: can("settings.manage") },
    { value: "users", label: "Users", show: can("users.manage") },
    { value: "audit", label: "Activity log", show: can("audit.view") },
  ] as { value: T; label: string; show: boolean }[]).filter((i) => i.show);
  const [tab, setTab] = useState<T>(items[0]?.value ?? "tally");

  return (
    <>
      <PageHeader title="Settings" subtitle="For the administrator: the link with Tally, and who can sign in." />
      <Tabs value={tab} onChange={setTab} items={items} />
      {tab === "tally" && <TallyLinkTab />}
      {tab === "users" && <UsersTab />}
      {tab === "audit" && <AuditTab />}
    </>
  );
}
