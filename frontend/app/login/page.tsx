"use client";

import { Eye, EyeOff, LogIn } from "lucide-react";
import { useEffect, useState } from "react";
import { post } from "@/lib/api";
import { Button, Field, Input, Notice } from "@/components/ui";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [show, setShow] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [caps, setCaps] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    try { document.documentElement.dataset.text = localStorage.getItem("vbt-text-size") || "normal"; } catch { /* ignore */ }
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!username.trim() || !password) return setErr("Please type both your username and your password.");
    setBusy(true);
    setErr(null);
    try {
      const me = await post<{ must_change_password: boolean }>("/api/auth/login", { username: username.trim(), password });
      const next = new URLSearchParams(window.location.search).get("next");
      const safeNext = next && next.startsWith("/") && !next.startsWith("//") ? next : "/";
      window.location.href = me.must_change_password ? "/change-password" : safeNext;
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[1fr_1.1fr]">
      <div className="relative hidden flex-col justify-between overflow-hidden bg-sidebar p-12 text-white lg:flex">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-accent text-2xl font-bold">V</div>
          <div>
            <div className="text-xl font-semibold">Vishakan Bio Tech</div>
            <div className="text-base text-white/75">Accounts Department</div>
          </div>
        </div>
        <div className="max-w-md">
          <p className="text-3xl font-semibold leading-snug">Invoices, bills, payments and reports — all in one place.</p>
        </div>
        <div className="text-sm text-white/65">For accounts staff of Vishakan Bio Tech. Everything you do here is recorded.</div>
        <div className="pointer-events-none absolute -bottom-24 -right-24 h-80 w-80 rounded-full border-[40px] border-accent/15" />
      </div>
      <div className="flex items-center justify-center p-6">
        <form onSubmit={submit} className="w-full max-w-md">
          <div className="mb-8 lg:hidden">
            <div className="text-xl font-semibold">Vishakan Bio Tech</div>
            <div className="text-base text-muted">Accounts Department</div>
          </div>
          <h1 className="text-3xl font-semibold">Sign in</h1>
          <p className="mt-2 text-base text-muted">Type the username and password given to you.</p>
          <div className="mt-8 space-y-5">
            <Field label="Username">
              <Input autoFocus autoComplete="username" autoCapitalize="none" spellCheck={false} value={username} onChange={(e) => setUsername(e.target.value)} className="min-h-13 text-lg" />
            </Field>
            <Field label="Password" hint={caps ? <span className="font-medium text-warn">Caps Lock is ON — capital letters are being typed.</span> : undefined}>
              <div className="relative">
                <Input type={show ? "text" : "password"} autoComplete="current-password" value={password}
                  onChange={(e) => setPassword(e.target.value)} onKeyUp={(e) => setCaps(e.getModifierState("CapsLock"))}
                  className="min-h-13 pr-28 text-lg" />
                <button type="button" onClick={() => setShow((s) => !s)}
                  className="absolute right-2 top-1/2 inline-flex min-h-10 -translate-y-1/2 items-center gap-1.5 rounded-md px-2.5 text-base text-accent-strong hover:bg-soft-2">
                  {show ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}{show ? "Hide" : "Show"}
                </button>
              </div>
            </Field>
            {err && <Notice tone="bad">{err}</Notice>}
            <Button variant="primary" size="lg" className="w-full" type="submit" busy={busy} icon={<LogIn className="h-5 w-5" />}>Sign in</Button>
          </div>
          <p className="mt-6 text-base text-muted">Forgot your password? Ask the office administrator to reset it for you.</p>
        </form>
      </div>
    </div>
  );
}
