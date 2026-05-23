import { OpsLayout } from "@/components/ops/OpsLayout";
import { MetricCard } from "@/components/ui/MetricCard";

export default function OpsOverviewPage() {
  return (
    <OpsLayout title="Vue d'ensemble">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-4 mb-6">
        <MetricCard label="Envoyés" value={120} />
        <MetricCard label="Échecs" value={3} />
        <MetricCard label="Réponses" value={8} />
        <MetricCard label="Succès %" value="93%" />
        <MetricCard label="File" value={42} />
        <MetricCard label="Traités" value={78} />
      </div>
      <div className="grid md:grid-cols-2 gap-4">
        <div className="rounded-xl border border-slate-800 p-4 h-48 flex items-center justify-center text-slate-500 text-sm">
          Graphique — leads par statut
        </div>
        <div className="rounded-xl border border-slate-800 p-4 h-48 flex items-center justify-center text-slate-500 text-sm">
          Graphique — envois par canal
        </div>
      </div>
    </OpsLayout>
  );
}
