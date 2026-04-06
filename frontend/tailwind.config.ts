import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        display: ["Sora", "sans-serif"],
        body: ["IBM Plex Sans", "sans-serif"],
      },
      boxShadow: {
        aurora: "0 24px 80px -30px rgba(11, 19, 43, 0.85)",
      },
      animation: {
        glow: "glow 7s ease-in-out infinite",
      },
      keyframes: {
        glow: {
          "0%, 100%": { opacity: "0.65", transform: "scale(1)" },
          "50%": { opacity: "1", transform: "scale(1.04)" },
        },
      },
    },
  },
  plugins: [],
};

export default config;
