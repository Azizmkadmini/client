"use client";

import { useEffect, useState } from "react";

import { PageHeader } from "@/components/ui/PageHeader";
import { MetricCard } from "@/components/ui/MetricCard";
import { Button } from "@/components/ui/Button";
import { apiGet, apiPost } from "@/lib/api";

type Credits = { balance: number; plan: string };

export default function BillingPage() {
  const [credits, setCredits] = useState<Credits | null>(null);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    apiGet<Credits>("/api/v1/billing/credits").then(setCredits).catch((e) => setMsg(String(e)));
  }, []);

  async function checkout(plan: string) {
    const res = await apiPost<{ checkout_url?: string; message?: string }>(
      `/api/v1/billing/checkout?plan=${plan}`,
      {}
    );
    if (res.checkout_url) window.location.href = res.checkout_url;
    else setMsg(res.message || "Checkout initié");
    const c = await apiGet<Credits>("/api/v1/billing/credits");
    setCredits(c);
  }

  return (
    <div className="space-y-6">
      <PageHeader title="Billing" description="Plan, crédits et checkout Stripe." />
      {credits ? (
        <div className="grid md:grid-cols-2 gap-4 max-w-lg">
          <MetricCard label="Plan" value={credits.plan} />
          <MetricCard label="Crédits" value={credits.balance} />
        </div>
      ) : null}
      <div className="grid md:grid-cols-2 gap-4 max-w-2xl">
        <div className="rounded-xl border border-slate-800 p-6 space-y-4">
          <h3 className="font-semibold">Starter</h3>
          <p className="text-sm text-slate-400">Scraping et outreach essentiels.</p>
          <Button variant="secondary" onClick={() => checkout("starter")}>
            Choisir Starter
          </Button>
        </div>
        <div className="rounded-xl border border-emerald-900/50 bg-emerald-950/20 p-6 space-y-4">
          <h3 className="font-semibold text-emerald-400">Pro</h3>
          <p className="text-sm text-slate-400">Content OS + limites élevées.</p>
          <Button onClick={() => checkout("pro")}>Choisir Pro</Button>
        </div>
      </div>
      {msg ? <p className="text-sm text-slate-400">{msg}</p> : null}
    </div>
  );
}
