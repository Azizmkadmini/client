import Link from "next/link";

import { MetricCard } from "@/components/ui/MetricCard";
import { PageHeader } from "@/components/ui/PageHeader";

const CARDS = [
  { href: "/acquisition", title: "Acquisition", desc: "Leads, scraper, outreach multi-canal", icon: "◎" },
  { href: "/content", title: "Content OS", desc: "Hooks, posts IA, calendrier, publication", icon: "✎" },
  { href: "/analytics", title: "Analytics", desc: "KPIs acquisition + contenu", icon: "▤" },
  { href: "/campaigns", title: "Campagnes", desc: "Jobs Redis, rate limits", icon: "⚡" },
  { href: "/ops/overview", title: "Ops Console", desc: "Scraper, pipeline, logs", icon: "⚙" },
  { href: "/billing", title: "Billing", desc: "Plans Starter / Pro, crédits", icon: "◈" },
] as const;

export default function Home() {
  return (
    <div className="space-y-10 animate-fade-in">
      <section className="card p-8 md:p-10 border-emerald-900/30">
        <p className="text-xs font-medium uppercase tracking-widest text-emerald-500">Plateforme SaaS</p>
        <h1 className="mt-2 text-3xl md:text-4xl font-bold text-white">
          <span className="text-gradient">AI Acquisition OS</span>
        </h1>
        <p className="mt-3 max-w-2xl text-slate-400 text-sm md:text-base leading-relaxed">
          Acquisition B2B, Content LinkedIn, analytics et console ops — une seule interface.
        </p>
      </section>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <MetricCard label="Statut API" value="OK" hint="FastAPI" />
        <MetricCard label="Content" value="OS" hint="Génération IA" />
        <MetricCard label="Queue" value="Redis" hint="Jobs" />
        <MetricCard label="UI" value="v1.0" hint="Next.js 14" />
      </div>

      <section>
        <h2 className="text-sm font-medium uppercase tracking-wide text-slate-500 mb-4">Modules</h2>
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
          {CARDS.map((c) => (
            <Link key={c.href} href={c.href} className="card-hover p-6 block group">
              <span className="text-2xl text-emerald-500/80 group-hover:text-emerald-400 transition-colors">
                {c.icon}
              </span>
              <h3 className="mt-3 font-semibold text-lg text-white">{c.title}</h3>
              <p className="text-sm text-slate-500 mt-2 leading-relaxed">{c.desc}</p>
              <span className="inline-block mt-4 text-xs font-medium text-emerald-400 group-hover:underline">
                Ouvrir →
              </span>
            </Link>
          ))}
        </div>
      </section>

      <section className="card p-5 text-sm">
        <h3 className="font-medium text-slate-300 mb-2">Configuration</h3>
        <p className="text-slate-500">
          API :{" "}
          <span className="font-mono text-slate-400">
            {process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"}
          </span>
        </p>
        <p className="text-slate-500 mt-1">
          Clé API :{" "}
          <Link href="/settings" className="text-emerald-400 hover:underline">
            Paramètres
          </Link>
        </p>
      </section>
    </div>
  );
}
