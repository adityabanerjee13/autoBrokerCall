/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // The five semantic tokens used across all three dashboards.
        agent: "#0B6E75",   // agent / automated / renter
        human: "#A2560B",   // human action needed
        alarm: "#9E2129",   // escalation, safety fail, denied tool
        judge: "#3C4B9B",   // analysis / evaluation
      },
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};
