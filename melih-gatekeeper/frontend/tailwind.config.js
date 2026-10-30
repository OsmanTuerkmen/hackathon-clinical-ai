/** @type {import('tailwindcss').Config} */
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`;
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: v("bg"),
        surface: v("surface"),
        sunken: v("sunken"),
        ink: v("ink"),
        "ink-fg": v("ink-fg"),
        muted: v("muted"),
        line: v("line"),
        accent: v("accent"),
        gold: v("gold"),
        reject: { DEFAULT: v("reject"), bg: v("reject-bg") },
        stat: { DEFAULT: v("stat"), bg: v("stat-bg") },
        spe: { DEFAULT: v("spe"), bg: v("spe-bg") },
        warn: { DEFAULT: v("warn"), bg: v("warn-bg") },
      },
      fontFamily: {
        sans: ['"Inter Tight"', "system-ui", "sans-serif"],
        serif: ['"Source Serif 4"', "Georgia", "serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      fontSize: {
        xs: ["12px", "16px"],
        sm: ["13px", "20px"],
        base: ["14px", "21px"],
        md: ["16px", "24px"],
        lg: ["20px", "28px"],
        xl: ["28px", "34px"],
        "2xl": ["40px", "44px"],
        "3xl": ["52px", "56px"],
      },
      borderRadius: { xl: "12px", lg: "10px", md: "8px" },
      keyframes: {
        "pulse-ring": {
          "0%": { boxShadow: "0 0 0 0 rgb(var(--accent) / 0.45)" },
          "70%": { boxShadow: "0 0 0 10px rgb(var(--accent) / 0)" },
          "100%": { boxShadow: "0 0 0 0 rgb(var(--accent) / 0)" },
        },
        shimmer: { "0%": { backgroundPosition: "-400px 0" }, "100%": { backgroundPosition: "400px 0" } },
      },
      animation: {
        "pulse-ring": "pulse-ring 1.4s cubic-bezier(.4,0,.6,1) infinite",
        shimmer: "shimmer 1.4s linear infinite",
      },
    },
  },
  plugins: [],
};
