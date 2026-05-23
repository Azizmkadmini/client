"use client";

import { useEffect, useState } from "react";

import { PageHeader } from "@/components/ui/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { EmptyState } from "@/components/ui/EmptyState";
import { apiGet } from "@/lib/api";

type Slot = { id: string; slot_start?: string; status: string; body: string; hook?: string };

export default function CalendarPage() {
  const [slots, setSlots] = useState<Slot[]>([]);

  useEffect(() => {
    apiGet<{ slots: Slot[] }>("/api/v1/content/calendar")
      .then((d) => setSlots(d.slots || []))
      .catch(() => setSlots([]));
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader title="Calendrier éditorial" description="Créneaux planifiés et statuts de publication." />
      {slots.length === 0 ? (
        <EmptyState
          title="Aucun créneau"
          description="Planifiez depuis Content OS ou l'Ops Console."
        />
      ) : (
        <div className="grid gap-3">
          {slots.map((s) => (
            <div
              key={s.id}
              className="rounded-xl border border-slate-800 p-4 flex justify-between gap-4 bg-slate-900/30"
            >
              <div>
                <p className="text-sm text-slate-300">{s.slot_start}</p>
                <p className="mt-2 text-sm line-clamp-2">{s.hook || s.body}</p>
              </div>
              <Badge status={s.status} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
