"use client";

import { useEffect, useState } from "react";

import Link from "next/link";

import { ErrorBanner } from "@/components/ui/ErrorBanner";
import { EmptyState } from "@/components/ui/EmptyState";
import { MetricCard } from "@/components/ui/MetricCard";
import { PageHeader } from "@/components/ui/PageHeader";
import { Button } from "@/components/ui/Button";
import { apiGet } from "@/lib/api";

type LeadsRes = {
  items?: { id: string; name: string; email?: string; status: string; channel: string }[];
  total?: number;
  offset?: number;
  limit?: number;
};

export default function AcquisitionPage() {
  const [leads, setLeads] = useState<LeadsRes | null>(null);
  const [stats, setStats] = useState<Record<string, number>>({});
  const [err, setErr] = useState("");

  async function load() {
    setErr("");
    try {
      const overview = await apiGet<{ acquisition?: { leads?: Record<string, number> } }>(
        "/api/v1/analytics/overview"
      );
      setStats(overview.acquisition?.leads || {});
      const data = await apiGet<LeadsRes>("/leads?limit=20&offset=0");
      setLeads(data);
    } catch (e) {
      setErr(String(e));
    }
  }

  useEffect(() => {
    load();
  }, []);

  const total = Object.values(stats).reduce((a, b) => a + b, 0);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Acquisition"
        description="Leads, import CSV et métriques outreach."
        actions={
          <>
            <Button variant="secondary">Importer CSV</Button>
            <Link href="/ops/leads" className="text-sm text-indigo-400 hover:underline self-center">
              Ops Console →
            </Link>
          </>
        }
      />
      <ErrorBanner message={err} onRetry={load} />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard label="Total leads" value={total} />
        <MetricCard label="Nouveaux" value={stats.new ?? 0} />
        <MetricCard label="Contactés" value={stats.contacted ?? 0} />
        <MetricCard label="Réponses" value={stats.replied ?? 0} />
      </div>
      {(leads?.items || []).length === 0 && !err ? (
        <EmptyState title="Aucun lead" description="Importez un CSV ou lancez le scraper depuis Campagnes." />
      ) : null}
      <div className="rounded-xl border border-slate-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-slate-900 text-slate-400 text-xs">
            <tr>
              <th className="p-3 text-left">Nom</th>
              <th className="p-3 text-left">Email</th>
              <th className="p-3">Statut</th>
              <th className="p-3">Canal</th>
            </tr>
          </thead>
          <tbody className="text-slate-300">
            {(leads?.items || []).map((l) => (
              <tr key={l.id} className="border-t border-slate-800">
                <td className="p-3">{l.name}</td>
                <td className="p-3">{l.email || "—"}</td>
                <td className="p-3 text-center">{l.status}</td>
                <td className="p-3 text-center">{l.channel}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="p-3 text-xs text-slate-500 border-t border-slate-800">
          {leads?.total ?? 0} leads — offset {leads?.offset ?? 0}
        </p>
      </div>
    </div>
  );
}
