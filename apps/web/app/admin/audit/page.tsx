import { PageHeader } from "@/components/ui/PageHeader";

export default function AdminAuditPage() {
  return (
    <div className="space-y-6">
      <PageHeader title="Audit log" description="Enterprise — événements sécurité et actions utilisateurs." />
      <table className="w-full text-sm rounded-xl border border-slate-800">
        <thead className="bg-slate-900 text-slate-400 text-xs">
          <tr>
            <th className="p-3 text-left">action</th>
            <th className="p-3">actor</th>
            <th className="p-3">at</th>
          </tr>
        </thead>
        <tbody className="text-slate-300">
          <tr className="border-t border-slate-800">
            <td className="p-3">content.publish</td>
            <td className="p-3 text-center">admin@local.dev</td>
            <td className="p-3 text-center">2026-05-21</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
