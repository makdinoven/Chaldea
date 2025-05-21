import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import svgr from "vite-plugin-svgr";

export default defineConfig({
  plugins: [react(), svgr()],
  server: {
    host: true,
    port: 5555,
    watch: {
      usePolling: true,
    },
    allowedHosts: ["4452515-co41851.twc1.net"],
  },
});
