/** @type {import('tailwindcss').Config} */
/** Aligné docs/design-tokens.json */
module.exports = {
  content: ["./app/**/*.{js,ts,jsx,tsx}", "./components/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        aios: {
          base: "#020617",
          elevated: "#0f172a",
          subtle: "#1e293b",
          accent: "#059669",
          "accent-hover": "#10b981",
          "accent-muted": "#064e3b",
          ops: "#6366f1",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
      boxShadow: {
        glow: "0 0 40px -10px rgba(5, 150, 105, 0.35)",
      },
    },
  },
  plugins: [],
};
