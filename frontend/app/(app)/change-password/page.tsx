"use client";

import { useState } from "react";
import { post } from "@/lib/api";
import { useAuth } from "@/lib/auth";
import { Button, Card, Field, Input, Notice, PageHeader, useToast } from "@/components/ui";

export default function ChangePasswordPage() {
  const { me, reload } = useAuth();
  const toast = useToast();
  const [cur, setCur] = useState("");
  const [nw, setNw] = useState("");
  const [again, setAgain] = useState("");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const problems = [nw.length < 10 && "10+ characters", !/\d/.test(nw) && "a number", !/[a-zA-Z]/.test(nw) && "a letter"].filter(Boolean);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (problems.length) return setErr(`The new password still needs ${problems.join(", ")}.`);
    if (nw !== again) return setErr("The two new passwords are not the same. Please type them again.");
    setBusy(true);
    setErr(null);
    try {
      await post("/api/auth/change-password", { current_password: cur, new_password: nw });
      await reload();
      toast("Password changed.");
      window.location.href = "/";
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-lg">
      <PageHeader title="Change my password" subtitle="Choose a password only you know. Write it somewhere safe if needed." />
      {me?.must_change_password && <div className="mb-4"><Notice tone="warn">Welcome! Before you start, please choose your own password. Type the password you were given in the first box.</Notice></div>}
      <Card>
        <form onSubmit={submit} className="space-y-4">
          <Field label="Password you use now (or were given)"><Input type="password" autoComplete="current-password" value={cur} onChange={(e) => setCur(e.target.value)} required /></Field>
          <Field label="New password" hint={nw && problems.length ? `Still needs: ${problems.join(", ")}` : "At least 10 letters and numbers. Example: Coimbatore2027"}>
            <Input type="password" autoComplete="new-password" value={nw} onChange={(e) => setNw(e.target.value)} required />
          </Field>
          <Field label="Type the new password again"><Input type="password" autoComplete="new-password" value={again} onChange={(e) => setAgain(e.target.value)} required /></Field>
          {err && <Notice tone="bad">{err}</Notice>}
          <Button variant="primary" size="lg" type="submit" busy={busy}>Save my new password</Button>
        </form>
      </Card>
    </div>
  );
}
