"use client";

import { useState } from "react";
import { useAuth } from "@/lib/auth";
import { AuditTab, CompanyTab, ControlsTab, TallyTab, UsersTab } from "@/components/settings/admin";
import { BanksTab, CategoriesTermsTab, PartiesTab, ProductsTab } from "@/components/settings/masters";
import { PageHeader, Tabs } from "@/components/ui";

type T = "company" | "parties" | "products" | "banks" | "cats" | "controls" | "users" | "audit" | "tally";

export default function SettingsPage() {
  const { can } = useAuth();
  const items = ([
    { value: "company", label: "Company", show: can("dashboard.view") },
    { value: "parties", label: "Dealers & suppliers", show: can("masters.view") },
    { value: "products", label: "Products", show: can("masters.view") },
    { value: "banks", label: "Bank & cash", show: can("masters.view") },
    { value: "cats", label: "Categories & terms", show: can("masters.view") },
    { value: "controls", label: "Numbering & controls", show: true },
    { value: "users", label: "Users & roles", show: can("users.manage") },
    { value: "audit", label: "Audit log", show: can("audit.view") },
    { value: "tally", label: "Tally ledgers", show: can("settings.manage") },
  ] as { value: T; label: string; show: boolean }[]).filter((i) => i.show);
  const [tab, setTab] = useState<T>(items[0]?.value ?? "company");

  return (
    <>
      <PageHeader title="Settings & User Management" subtitle="Company details, master lists, controls and access" />
      <div className="overflow-x-auto"><Tabs value={tab} onChange={setTab} items={items} /></div>
      {tab === "company" && <CompanyTab />}
      {tab === "parties" && <PartiesTab />}
      {tab === "products" && <ProductsTab />}
      {tab === "banks" && <BanksTab />}
      {tab === "cats" && <CategoriesTermsTab />}
      {tab === "controls" && <ControlsTab />}
      {tab === "users" && <UsersTab />}
      {tab === "audit" && <AuditTab />}
      {tab === "tally" && <TallyTab />}
    </>
  );
}
