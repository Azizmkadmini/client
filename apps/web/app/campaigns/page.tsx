"use client";

import { useEffect, useState } from "react";

import { PageHeader } from "@/components/ui/PageHeader";
import { MetricCard } from "@/components/ui/MetricCard";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { apiGet, apiPost } from "@/lib/api";

type Job = { id?: string; job_type?: string; status?: string; error?: string };

export default function CampaignsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [limits, setLimits] = useState<Record<string, { remaining: number; daily_max: number }>>({});

  useEffect(() => {
    apiGet<{ jobs: Job[] }>("/api/v1/platform/jobs/scraper?limit=15").then((d) => setJobs(d.jobs || []));
    apiGet<Record<string, { remaining: number; daily_max: number }>>("/api/v1/platform/rate-limits").then(
      setLimits
    );
  }, []);

  async function runLinkedInJob() {
    await apiPost("/jobs/scraper", { job_type: "linkedin-run", payload: {}, sync: false });
    const d = await apiGet<{ jobs: Job[] }>("/api/v1/platform/jobs/scraper?limit=15");
    setJobs(d.jobs || []);
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Campagnes & jobs"
        description="Rate limits, file Redis et jobs scraper."
        actions={<Button onClick={runLinkedInJob}>Lancer scrape LinkedIn</Button>}
      />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {Object.entries(limits).map(([ch, v]) => (
          <MetricCard key={ch} label={ch} value={`${v.remaining}/${v.daily_max}`} hint="restant / max jour" />
        ))}
      </div>
      <div className="rounded-xl border border-slate-800 divide-y divide-slate-800">
        {jobs.map((j, i) => (
          <div key={j.id || i} className="flex items-center justify-between gap-4 p-4 text-sm">
            <span className="font-mono text-slate-300">{j.job_type}</span>
            <Badge status={j.status || "default"} />
            {j.error ? <span className="text-red-400 truncate max-w-xs">{j.error}</span> : null}
          </div>
        ))}
      </div>
    </div>
  );
}
