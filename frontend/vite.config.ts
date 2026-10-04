import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { loadEnv } from "vite";
import { defineConfig } from "vitest/config";

export default defineConfig(({ command, mode }) => {
  const env = loadEnv(mode, "..", "VITE_");
  const allowed = new Set(["VITE_API_BASE_URL", "VITE_GOOGLE_CLIENT_ID"]);

  const unexpected = Object.keys(env).filter(
    (key) => !allowed.has(key) && !key.startsWith("VITE_VERCEL_"),
  );

  if (unexpected.length > 0) {
    throw new Error(
      "Only approved frontend variables and Vercel system variables may use VITE_.",
    );
  }
  if (command === "build") {
    let api: URL;
    try {
      api = new URL(env.VITE_API_BASE_URL);
    } catch {
      throw new Error("A production VITE_API_BASE_URL is required.");
    }
    if (
      api.protocol !== "https:" ||
      api.username ||
      api.password ||
      api.search ||
      api.hash ||
      api.pathname !== "/api/v1" ||
      ["localhost", "127.0.0.1"].includes(api.hostname)
    ) {
      throw new Error(
        "VITE_API_BASE_URL must be an HTTPS deployed API ending in /api/v1.",
      );
    }
    if (!env.VITE_GOOGLE_CLIENT_ID?.endsWith(".apps.googleusercontent.com")) {
      throw new Error("The production Google OAuth Web client ID is required.");
    }
  }
  return {
    envDir: "..",
    plugins: [react(), tailwindcss()],
    build: { sourcemap: false },
    test: {
      include: ["src/**/*.test.{ts,tsx}"],
      environment: "jsdom",
      globals: true,
      setupFiles: "./src/test/setup.ts",
    },
  };
});
