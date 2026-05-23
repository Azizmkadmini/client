"use client";

import { useEffect, useState } from "react";

import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { EmptyState } from "@/components/ui/EmptyState";
import { apiGet, apiPost } from "@/lib/api";

type Account = {
  id: string;
  label: string;
  health_score: number;
  purpose_scrape: number;
  purpose_outreach: number;
  purpose_publish: number;
};

export default function AccountsPage() {
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [label, setLabel] = useState("");

  async function load() {
    const data = await apiGet<{ accounts: Account[] }>("/api/v1/accounts/linkedin");
    setAccounts(data.accounts || []);
  }

  useEffect(() => {
    load().catch(console.error);
  }, []);

  async function add() {
    if (!label.trim()) return;
    await apiPost("/api/v1/accounts/linkedin", { label, scrape: true, outreach: false, publish: true });
    setLabel("");
    await load();
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Comptes LinkedIn" description="Pool multi-comptes scrape / publish." />
      {accounts.length === 0 ? (
        <EmptyState title="Aucun compte" description="Ajoutez un compte pour publier." />
      ) : (
        <ul className="space-y-3">
          {accounts.map((a) => (
            <li key={a.id} className="rounded-xl border border-slate-800 p-4">
              <div className="flex justify-between items-center gap-4">
                <strong className="text-white">{a.label}</strong>
                <span className="text-sm text-emerald-400">santé {a.health_score}%</span>
              </div>
              <div className="mt-2 h-2 rounded-full bg-slate-800 overflow-hidden">
                <div className="h-full bg-emerald-600" style={{ width: `${a.health_score}%` }} />
              </div>
              <p className="mt-2 text-xs text-slate-500">
                scrape={a.purpose_scrape} · outreach={a.purpose_outreach} · publish={a.purpose_publish}
              </p>
            </li>
          ))}
        </ul>
      )}
      <div className="flex gap-2 max-w-md">
        <Input value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Label compte" />
        <Button onClick={add}>Ajouter</Button>
      </div>
    </div>
  );
}
