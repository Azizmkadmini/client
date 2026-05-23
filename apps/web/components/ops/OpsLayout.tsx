"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { href: "/ops/overview", label: "Vue d'ensemble" },
  { href: "/ops/scraper", label: "Scraper" },
  { href: "/ops/content", label: "Content OS" },
  { href: "/ops/pipeline", label: "Pipeline" },
  { href: "/ops/leads", label: "Leads" },
  { href: "/ops/queue", label: "File" },
  { href: "/ops/logs", label: "Logs" },
  { href: "/ops/compliance", label: "Conformité" },
  { href: "/ops/guide", label: "Guide" },
  { href: "/ops/settings", label: "Paramètres" },
];

export function OpsLayout({ children, title }: { children: React.ReactNode; title: string }) {
  const pathname = usePathname();
  return (
    <div className="flex min-h-[calc(100vh-120px)] gap-0 rounded-xl border border-slate-800 overflow-hidden">
      <aside className="w-56 shrink-0 bg-slate-900 border-r border-slate-800 p-3">
        <p className="text-xs font-semibold uppercase tracking-wide text-indigo-400 mb-3">Ops Console</p>
        <nav className="space-y-0.5">
          {TABS.map((t) => (
            <Link
              key={t.href}
              href={t.href}
              className={`block rounded-md px-2 py-1.5 text-xs ${
                pathname === t.href ? "bg-indigo-950 text-indigo-300" : "text-slate-400 hover:bg-slate-800"
              }`}
            >
              {t.label}
            </Link>
          ))}
        </nav>
      </aside>
      <div className="flex-1 p-6 bg-slate-950">
        <h1 className="text-xl font-bold text-white mb-4">{title}</h1>
        {children}
      </div>
    </div>
  );
}
