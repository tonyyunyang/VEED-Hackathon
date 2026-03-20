import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load env file based on `mode` in the current working directory.
  // Set the third parameter to '' to load all envs regardless of the `VITE_` prefix.
  const env = loadEnv(mode, process.cwd(), "");

  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: {
        "@veed-hackathon": "/src",
      },
    },
    server: {
      proxy: {
        "/api": {
          target: env.VITE_BACKEND_TARGET || "http://localhost:8000",
          changeOrigin: true,
          secure: false,
        },
      },
    },
    preview: {
      proxy: {
        "/api": {
          target: env.VITE_BACKEND_TARGET || "http://localhost:8000",
          changeOrigin: true,
          secure: false,
        },
      },
    },
  };
});
