"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/Button";
import { login } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("admin@local.dev");
  const [password, setPassword] = useState("admin123");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      router.push("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Erreur login");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-[calc(100vh-2rem)] items-center justify-center px-4 py-12">
      <div className="grid w-full max-w-4xl overflow-hidden rounded-2xl border border-slate-800 shadow-glow md:grid-cols-2">
        <div className="hidden md:flex flex-col justify-between bg-gradient-to-br from-emerald-950 via-slate-900 to-slate-950 p-10">
          <div>
            <span className="inline-flex h-12 w-12 items-center justify-center rounded-xl bg-emerald-600/30 border border-emerald-500/40 text-xl font-bold text-emerald-300">
              A
            </span>
            <h1 className="mt-8 text-3xl font-bold text-white leading-tight">AI Acquisition OS</h1>
            <p className="mt-3 text-slate-400 text-sm leading-relaxed">
              Acquisition B2B · Content LinkedIn · Analytics · Ops
            </p>
          </div>
          <p className="text-xs text-slate-600">v1.0 · Plateforme unifiée</p>
        </div>
        <div className="bg-slate-900/80 p-8 md:p-10 backdrop-blur-sm">
          <h2 className="text-xl font-semibold text-white md:hidden">Connexion</h2>
          <p className="mt-1 text-sm text-slate-400 md:mt-0">Accédez à votre espace</p>
          <form onSubmit={onSubmit} className="mt-8 space-y-5">
            <div>
              <label className="label-field">Email</label>
              <input
                className="input-field mt-1.5"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
              />
            </div>
            <div>
              <label className="label-field">Mot de passe</label>
              <input
                className="input-field mt-1.5"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
              />
            </div>
            {error ? (
              <p className="rounded-lg border border-red-900/50 bg-red-950/40 px-3 py-2 text-sm text-red-300">
                {error}
              </p>
            ) : null}
            <Button type="submit" className="w-full py-2.5" disabled={loading}>
              {loading ? "Connexion…" : "Se connecter"}
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
