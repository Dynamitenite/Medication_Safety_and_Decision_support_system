import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// The dev server forwards /api to the FastAPI app (python -m uvicorn api.app:app --port 8000),
// so the browser sees one origin. The API also allows http://localhost:5173 through CORS.
// Set MEDSAFE_API to point the proxy at another port.
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "MEDSAFE_");
  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: { "/api": { target: env.MEDSAFE_API ?? "http://127.0.0.1:8000", changeOrigin: true } },
    },
  };
});
