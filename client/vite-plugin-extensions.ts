/**
 * Vite plugin that generates a `virtual:extensions` module at build time.
 *
 * The plugin reads the `AIRUNNER_EXTENSIONS` environment variable (from .env)
 * to discover which extensions are active. If empty, it auto-scans the
 * `extensions/` directory for any subdirectories containing a `config.py`.
 *
 * For each active extension, it checks the convention-based client directory
 * and generates appropriate imports for route elements and providers.
 */

import type { Plugin } from "vite";
import * as fs from "fs";
import * as path from "path";

const VIRTUAL_MODULE_ID = "virtual:extensions";
const RESOLVED_VIRTUAL_MODULE_ID = "\0" + VIRTUAL_MODULE_ID;

/** Root directory where extensions live. */
const EXTENSIONS_DIR = path.resolve(__dirname, "../extensions");

/**
 * Parse the AIRUNNER_EXTENSIONS setting into a list of extension names.
 */
function parseExtensionNames(): string[] {
  const raw = process.env.AIRUNNER_EXTENSIONS || "";
  return raw
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
    .map((s) =>
      s.replace(/^extensions\./, "").replace(/\.config$/, ""),
    );
}

/**
 * Auto-discover extensions by scanning the extensions/ directory.
 * Returns names of subdirectories that contain a config.py file.
 */
function autodiscoverExtensions(): string[] {
  const names: string[] = [];
  try {
    if (!fs.existsSync(EXTENSIONS_DIR)) return names;
    for (const entry of fs.readdirSync(EXTENSIONS_DIR)) {
      const entryPath = path.join(EXTENSIONS_DIR, entry);
      if (!fs.statSync(entryPath).isDirectory()) continue;
      const configPath = path.join(entryPath, "config.py");
      if (fs.existsSync(configPath)) {
        names.push(entry);
      }
    }
  } catch {
    // extensions/ dir doesn't exist — normal in core
  }
  return names;
}

export function extensionLoaderPlugin(): Plugin {
  return {
    name: "airunner-extension-loader",
    // Run before Vite's built-in `resolve.alias`, otherwise the alias rewrites
    // `@extensions/...` to an out-of-root absolute path that Vite cannot
    // resolve when imported from this virtual module.
    enforce: "pre",

    // Watch the extensions directory via the dev server's file watcher so the
    // virtual module is regenerated when extensions are added or removed.
    //
    // NOTE: We deliberately do NOT use `this.addWatchFile(EXTENSIONS_DIR)` in
    // `load()`. In Vite, `addWatchFile(id)` also adds `id` to the module's
    // `_addedImports`, which import-analysis then tries to resolve as a real
    // module. A directory is not a resolvable module, so that produces a
    // hard "Failed to resolve import \"<extensions dir>\"" error on a cold
    // start (it only appears to "work" after a soft restart because the
    // resolve cache is warm). Watching through the chokidar watcher here
    // avoids polluting the import graph entirely.
    configureServer(server) {
      server.watcher.add(EXTENSIONS_DIR);
      server.watcher.on("all", (_event, file) => {
        if (!file.startsWith(EXTENSIONS_DIR)) return;
        const mod = server.moduleGraph.getModuleById(
          RESOLVED_VIRTUAL_MODULE_ID,
        );
        if (mod) {
          server.moduleGraph.invalidateModule(mod);
          server.ws.send({ type: "full-reload" });
        }
      });
    },

    resolveId(id) {
      if (id === VIRTUAL_MODULE_ID) return RESOLVED_VIRTUAL_MODULE_ID;
      // Resolve `@extensions/...` imports to absolute file paths ourselves.
      // The `@extensions` config alias points outside the Vite root, which
      // Vite cannot resolve when the import originates from this virtual
      // module (a virtual importer has no file path to anchor the alias).
      if (id.startsWith("@extensions/")) {
        const rel = id.slice("@extensions/".length);
        const base = path.join(EXTENSIONS_DIR, rel);
        const candidates = [
          base,
          `${base}.tsx`,
          `${base}.ts`,
          `${base}.jsx`,
          `${base}.js`,
          path.join(base, "index.tsx"),
          path.join(base, "index.ts"),
        ];
        for (const candidate of candidates) {
          if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) {
            return candidate;
          }
        }
      }
      return null;
    },

    load(id) {
      if (id !== RESOLVED_VIRTUAL_MODULE_ID) return null;

      // Watch .env (a real file) so the virtual module is regenerated when the
      // AIRUNNER_EXTENSIONS setting changes. The extensions *directory* is
      // watched in `configureServer` instead — see the note there for why we
      // must not pass a directory to `addWatchFile`.
      const envPath = path.resolve(__dirname, "..", ".env");
      if (fs.existsSync(envPath)) {
        this.addWatchFile(envPath);
      }

      // Try AIRUNNER_EXTENSIONS first, fall back to auto-scan
      let extNames = parseExtensionNames();
      if (extNames.length === 0) {
        extNames = autodiscoverExtensions();
      }

      console.log("[airunner-extensions] loading:", extNames);

      const imports: string[] = [];
      const routeElements: string[] = [];
      const providers: string[] = [];
      const headerGetters: string[] = [];
      const bottomBarIndices: number[] = [];

      extNames.forEach((name, i) => {
        const clientDir = path.join(EXTENSIONS_DIR, name, "client");

        if (!fs.existsSync(clientDir)) return;

        const routesPath = path.join(clientDir, "routes.tsx");
        if (fs.existsSync(routesPath)) {
          imports.push(
            `import { extensionRouteElements as ext${i}RouteElements } from "@extensions/${name}/client/routes";`,
          );
          routeElements.push(`...ext${i}RouteElements`);
        }

        const providerPath = path.join(clientDir, "Provider.tsx");
        if (fs.existsSync(providerPath)) {
          imports.push(
            `import { Provider as Ext${i}Provider } from "@extensions/${name}/client/Provider";`,
          );
          providers.push(`Ext${i}Provider`);
        }

        const bottomBarPath = path.join(clientDir, "BottomBar.tsx");
        if (fs.existsSync(bottomBarPath)) {
          imports.push(
            `import { BottomBar as Ext${i}BottomBar } from "@extensions/${name}/client/BottomBar";`,
          );
          bottomBarIndices.push(i);
        }

        const headersPath = path.join(clientDir, "headers.ts");
        if (fs.existsSync(headersPath)) {
          imports.push(
            `import { getRequestHeaders as ext${i}GetRequestHeaders } from "@extensions/${name}/client/headers";`,
          );
          headerGetters.push(`ext${i}GetRequestHeaders`);
        }
      });

      const bottomBarName =
        bottomBarIndices.length === 0
          ? "null"
          : bottomBarIndices.length === 1
            ? `/* @__PURE__ */React.createElement(Ext${bottomBarIndices[0]}BottomBar)`
            : `/* @__PURE__ */React.createElement(React.Fragment, null, ${bottomBarIndices.map((i) => `/* @__PURE__ */React.createElement(Ext${i}BottomBar)`).join(", ")})`;

      const headerGetterBody =
        headerGetters.length > 0
          ? headerGetters
              .map((fn) => `Object.assign(h, ${fn}())`)
              .join("; ")
          : "";
      const getRequestHeadersFn = headerGetterBody
        ? `export function getRequestHeaders() { const h = {}; ${headerGetterBody}; return h; }`
        : `export function getRequestHeaders() { return {}; }`;

      const source = [
        'import { Route } from "react-router-dom";',
        'import React from "react";',
        "",
        imports.join("\n"),
        "",
        `export const extensionRouteElements = [${routeElements.join(", ")}];`,
        `export const extensionProviders = [${providers.join(", ")}];`,
        `export const extensionBottomBarItems = ${bottomBarName};`,
        getRequestHeadersFn,
      ].join("\n");

      return source;
    },
  };
}
