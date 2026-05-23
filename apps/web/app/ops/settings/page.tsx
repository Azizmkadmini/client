import { OpsLayout } from "@/components/ops/OpsLayout";

export default function OpsSettingsPage() {
  return (
    <OpsLayout title="Paramètres ops">
      <pre className="rounded-xl border border-slate-800 bg-slate-900 p-4 text-xs text-emerald-400/90 mb-6 overflow-auto max-h-48">
        {JSON.stringify({ ai_provider: "ollama", storage_backend: "postgres", redis_url: "set" }, null, 2)}
      </pre>
      <table className="w-full text-xs rounded-xl border border-slate-800">
        <thead className="bg-slate-900 text-slate-400">
          <tr>
            <th className="p-2 text-left">canal</th>
            <th className="p-2">restant</th>
            <th className="p-2">max/jour</th>
          </tr>
        </thead>
        <tbody className="text-slate-300">
          {["linkedin", "email", "instagram", "content_publish"].map((c) => (
            <tr key={c} className="border-t border-slate-800">
              <td className="p-2">{c}</td>
              <td className="p-2">18</td>
              <td className="p-2">25</td>
            </tr>
          ))}
        </tbody>
      </table>
    </OpsLayout>
  );
}
