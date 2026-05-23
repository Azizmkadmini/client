import { OpsLayout } from "@/components/ops/OpsLayout";

const STEPS = [
  "Configurer .env et Redis",
  "Lancer scraper LinkedIn / IG / Web",
  "Pipeline connector + ingest",
  "Sessions outreach (login linkedin)",
  "Suivi follow-ups",
  "Planifier orchestrator",
  "API FastAPI + workers",
];

export default function OpsGuidePage() {
  return (
    <OpsLayout title="Guide opérationnel">
      <ol className="space-y-3">
        {STEPS.map((s, i) => (
          <li key={s} className="flex gap-3 rounded-lg border border-slate-800 bg-slate-900/40 p-4">
            <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-indigo-950 text-indigo-300 text-sm font-bold">
              {i + 1}
            </span>
            <span className="text-sm text-slate-200 pt-1">{s}</span>
          </li>
        ))}
      </ol>
    </OpsLayout>
  );
}
