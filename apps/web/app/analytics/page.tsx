"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { MetricCard } from "@/components/ui/MetricCard";
import { PageHeader } from "@/components/ui/PageHeader";
import { EmptyState } from "@/components/ui/EmptyState";
import { apiGet } from "@/lib/api";

type Overview = {
  acquisition?: { leads?: Record<string, number> };
  content?: { drafts?: number; scheduled?: number; published?: number; published_today?: number };
};

export default function AnalyticsPage() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [error, setError] = useState("");

  async function load() {
    setError("");
    try {
      setOverview(await apiGet<Overview>("/api/v1/analytics/overview"));
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    load();
  }, []);

  const leadData = Object.entries(overview?.acquisition?.leads || {}).map(([k, v]) => ({
    name: k,
    count: v,
  }));
  const content = overview?.content;
  const hasData = leadData.length > 0 || !!content;

  return (
    <div className="space-y-8">
      <PageHeader
        title="Analytics"
        description="KPIs acquisition et Content OS — agrégés depuis l'API."
        actions={
          <Link href="/campaigns" className="text-sm text-emerald-400 hover:underline">
            Campagnes →
          </Link>
        }
      />
      <ErrorBanner message={error} onRetry={load} />
      {content ? (
        <section className="space-y-3">
          <h2 className="text-sm font-medium text-slate-500">Content OS</h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <MetricCard label="Brouillons" value={content.drafts ?? 0} />
            <MetricCard label="Planifiés" value={content.scheduled ?? 0} />
            <MetricCard label="Publiés" value={content.published ?? 0} />
            <MetricCard label="Aujourd'hui" value={content.published_today ?? 0} hint="publications du jour" />
          </div>
        </section>
      ) : null}
      {leadData.length > 0 ? (
        <section className="space-y-3">
          <h2 className="text-sm font-medium text-slate-500">Acquisition — leads par statut</h2>
          <div className="h-64 w-full rounded-xl border border-slate-800 p-4 bg-slate-900/30">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={leadData}>
                <XAxis dataKey="name" stroke="#94a3b8" fontSize={12} />
                <YAxis stroke="#94a3b8" fontSize={12} />
                <Tooltip contentStyle={{ background: "#0f172a", border: "1px solid #334155" }} />
                <Bar dataKey="count" fill="#059669" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      ) : null}
      {!hasData && !error ? (
        <EmptyState
          title="Pas encore de données"
          description="Lancez un scraper ou générez du contenu pour alimenter les KPIs."
          action={
            <Link href="/acquisition" className="text-sm text-emerald-400 hover:underline">
              Aller à Acquisition
            </Link>
          }
        />
      ) : null}
    </div>
  );
}
