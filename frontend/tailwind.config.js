/** Cascade design tokens — the Velluto language from 03_FRONTEND_INSTRUCTIONS §1.
 *  One warm accent, reserved strictly for live status, alerts and the predicted
 *  bottleneck. Everything else is monochrome. */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#F4F3F1",
        surface: "#FAFAF9",
        ink: "#141414",
        muted: "#8A8A8A",
        hairline: "#E2E0DC",
        blueprint: "#C9C6C0",
        // the single accent — never decorative
        accent: { DEFAULT: "#F0552B", soft: "#FFE7E0", bright: "#FF5A1F" },
        status: {
          running: "#4B9B6E",
          watch:   "#D8A138",
          fault:   "#F0552B",
          idle:    "#B6B3AD",
        },
      },
      fontFamily: {
        display: ["Archivo", "system-ui", "sans-serif"],
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["'IBM Plex Mono'", "ui-monospace", "monospace"],
      },
      borderRadius: { card: "16px", pill: "999px" },
      boxShadow: {
        float: "0 8px 32px -12px rgba(20,20,20,.18), 0 2px 8px -4px rgba(20,20,20,.08)",
        rail:  "0 1px 3px rgba(20,20,20,.06)",
      },
      backdropBlur: { card: "14px" },
      keyframes: {
        pulseRing: {
          "0%":   { transform: "scale(1)",   opacity: "0.55" },
          "70%":  { transform: "scale(2.6)", opacity: "0" },
          "100%": { transform: "scale(2.6)", opacity: "0" },
        },
        slideIn: {
          from: { opacity: "0", transform: "translateY(-6px)" },
          to:   { opacity: "1", transform: "translateY(0)" },
        },
        fadeIn: { from: { opacity: "0" }, to: { opacity: "1" } },
        dash: { to: { strokeDashoffset: "-24" } },
      },
      animation: {
        pulseRing: "pulseRing 2.4s cubic-bezier(.4,0,.6,1) infinite",
        slideIn: "slideIn .28s cubic-bezier(.2,.7,.3,1)",
        fadeIn: "fadeIn .2s ease-out",
        dash: "dash 1s linear infinite",
      },
    },
  },
  plugins: [],
};
