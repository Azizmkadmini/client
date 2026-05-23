import type { ButtonHTMLAttributes, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

const variants: Record<Variant, string> = {
  primary:
    "bg-emerald-600 text-white hover:bg-emerald-500 disabled:opacity-50 disabled:pointer-events-none",
  secondary:
    "bg-slate-800 text-slate-100 border border-slate-700 hover:border-slate-600 disabled:opacity-50",
  ghost: "text-slate-300 hover:bg-slate-800 disabled:opacity-50",
  danger: "bg-red-900/40 text-red-300 border border-red-800 hover:bg-red-900/60",
};

export function Button({
  variant = "primary",
  className = "",
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; children: ReactNode }) {
  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center rounded-lg px-4 py-2 text-sm font-medium transition ${variants[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  );
}
