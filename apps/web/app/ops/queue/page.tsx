import { OpsLayout } from "@/components/ops/OpsLayout";

export default function OpsQueuePage() {
  return (
    <OpsLayout title="File d'attente">
      <table className="w-full text-xs rounded-xl border border-slate-800 overflow-hidden">
        <thead className="bg-slate-900 text-slate-400">
          <tr>
            <th className="p-2 text-left">fingerprint</th>
            <th className="p-2">name</th>
            <th className="p-2">company</th>
            <th className="p-2">tag</th>
            <th className="p-2">enqueued_at</th>
          </tr>
        </thead>
        <tbody className="text-slate-300">
          <tr className="border-t border-slate-800">
            <td className="p-2 font-mono">a3f9…</td>
            <td className="p-2">Sophie L.</td>
            <td className="p-2">TechCo</td>
            <td className="p-2">cold</td>
            <td className="p-2">2026-05-21</td>
          </tr>
        </tbody>
      </table>
    </OpsLayout>
  );
}
