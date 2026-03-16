import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import svgr from "vite-plugin-svgr";
import path from "path";

/**
 * Vite plugin that triggers a full browser reload when a source file is deleted.
 * This handles the "delete" half of a file rename (e.g. .jsx → .tsx),
 * forcing the browser to reload with fresh module URLs instead of 404-ing.
 */
function reloadOnDelete() {
  return {
    name: "reload-on-delete",
    configureServer(server) {
      server.watcher.on("unlink", (filePath) => {
        const relative = path.relative(process.cwd(), filePath);
        if (
          relative.startsWith("src/") &&
          /\.(jsx?|tsx?)$/.test(filePath)
        ) {
          server.ws.send({ type: "full-reload" });
        }
      });
    },
  };
}

export default defineConfig({
  plugins: [react(), svgr(), reloadOnDelete()],
  optimizeDeps: {
    force: true,
  },
  server: {
    host: true,
    port: 5555,
    watch: {
      usePolling: true,
    },
    allowedHosts: true,
    hmr: {
      host: 'localhost',
      port: 5555,
      protocol: 'ws',
    },
  },
});
