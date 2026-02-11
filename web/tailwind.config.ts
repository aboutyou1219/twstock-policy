import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0e0f1a",
        mist: "#f7f6f2",
        coral: "#ff6b4a",
        teal: "#1c9b8a",
        sand: "#f2d7b6",
      },
      boxShadow: {
        glow: "0 0 40px rgba(255, 107, 74, 0.25)",
      },
    },
  },
  plugins: [],
};

export default config;
