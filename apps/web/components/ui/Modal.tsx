"use client";

import { useEffect } from "react";
import { Button } from "@/components/ui/Button";

export function Modal({
  open,
  title,
  children,
  onClose,
  actions,
}: {
  open: boolean;
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  actions?: React.ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 animate-fade-in">
      <button type="button" className="absolute inset-0 bg-black/60" aria-label="Fermer" onClick={onClose} />
      <div className="relative w-full max-w-md rounded-xl border border-slate-700 bg-slate-900 p-6 shadow-xl animate-scale-in">
        <h2 className="text-lg font-semibold text-white">{title}</h2>
        <div className="mt-4 text-sm text-slate-300">{children}</div>
        <div className="mt-6 flex justify-end gap-2">
          {actions ?? (
            <Button variant="secondary" onClick={onClose}>
              Fermer
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
