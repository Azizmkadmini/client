import { PageHeader } from "@/components/ui/PageHeader";

export default function FeatureFlagsPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Feature flags" description="Enterprise — activation par tenant." />
      <ul className="space-y-2 text-sm">
        {["browser_grid", "stripe_billing", "oauth_linkedin", "postgres_ssot"].map((f) => (
          <li key={f} className="flex justify-between rounded-lg border border-slate-800 px-4 py-3">
            <span className="font-mono text-slate-300">{f}</span>
            <span className="text-emerald-400">on</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
