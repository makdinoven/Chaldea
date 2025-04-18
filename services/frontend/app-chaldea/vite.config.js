import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5555,
    watch: {
      usePolling: true,
    },
    allowedHosts: ["4452515-co41851.twc1.net"],
  },
});
