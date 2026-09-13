import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { extensionLoaderPlugin } from "./vite-plugin-extensions";
import { projectOverlayPlugin } from "./vite-plugin-project";
import { metaPlugin } from "./vite-plugin-meta";
import * as path from "path";

const VITE_PROJECT = process.env.VITE_PROJECT ?? "";

// https://vite.dev/config/
export default defineConfig({
  envDir: path.resolve(__dirname, ".."),
  define: {
    "import.meta.env.VITE_DEPLOYMENT": JSON.stringify(
      process.env.VITE_DEPLOYMENT ?? "edge",
    ),
    "import.meta.env.VITE_PROJECT": JSON.stringify(VITE_PROJECT),
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
  // Project/extension overlay files (projects/uwuchat/client,
  // extensions/*/client) live outside client/'s directory tree and
  // have no tsconfig.json of their own, so esbuild can't discover
  // "jsx": "react-jsx" for them via the normal tsconfig lookup and
  // falls back to the classic transform (which needs `React` in
  // scope). Pin the automatic runtime explicitly so it applies
  // uniformly regardless of which directory a .tsx file lives in.
  esbuild: {
    jsx: "automatic",
    jsxImportSource: "react",
  },
  plugins: [
    ...(VITE_PROJECT ? [projectOverlayPlugin(VITE_PROJECT)] : []),
    react(),
    extensionLoaderPlugin(),
    metaPlugin(),
  ],
  css: {
    preprocessorOptions: {
      scss: {
        silenceDeprecations: [
          "import",
          "if-function",
          "global-builtin",
          "color-functions",
        ],
      },
    },
  },
  server: {
    port: parseInt(process.env.VITE_PORT || "5173", 10),
    fs: {
      allow: [
        "..",
        path.resolve(__dirname, "../extensions"),
        path.resolve(__dirname, "../projects"),
      ],
    },
    watch: {
      usePolling: true,
      interval: 1000,
    },
    proxy: {
      "/api/v1": {
        target: process.env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8188",
        changeOrigin: true,
        secure: false,
        ws: true,
        proxyTimeout: 60_000,
        timeout: 60_000,
        configure: (proxy) => {
          proxy.on("error", (err, req, res) => {
            console.error(
              "[vite-proxy] error:",
              err.message,
              "url:",
              req.url,
            );
            if (res && "writeHead" in res) {
              try {
                const sr = res as import("http").ServerResponse;
                if (!sr.headersSent) {
                  sr.writeHead(502, {
                    "Content-Type": "application/json",
                  });
                  sr.end(
                    JSON.stringify({
                      error: "Proxy error",
                      detail: err.message,
                    }),
                  );
                }
              } catch {
                // Connection closed
              }
            }
          });
          proxy.on("proxyReq", (_proxyReq, req) => {
            console.log("[vite-proxy] →", req.method, req.url);
          });
          proxy.on("proxyRes", (proxyRes, req) => {
            console.log(
              "[vite-proxy] ←",
              req.method,
              req.url,
              proxyRes.statusCode,
            );
          });
        },
      },
    },
  },
});
