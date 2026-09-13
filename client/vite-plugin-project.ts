import * as path from "path";
import * as fs from "fs";
import type { Plugin } from "vite";

const EXTENSIONS = [
  ".tsx", ".ts", ".jsx", ".js",
  "/index.tsx", "/index.ts", "/index.jsx", "/index.js",
];

function resolveWithExts(base: string): string | null {
  if (fs.existsSync(base) && fs.statSync(base).isFile()) return base;
  for (const ext of EXTENSIONS) {
    const p = base + ext;
    if (fs.existsSync(p)) return p;
  }
  return null;
}

/**
 * Project overlay plugin — transparently substitutes files from
 * projects/<project>/client/ for their framework equivalents in client/src/.
 *
 * Resolution order for any import:
 *   1. If a project override exists for the resolved framework file → use it.
 *   2. If a project file can't find its relative dep locally → fall back to
 *      the framework equivalent path (then check #1 again).
 *
 * This means project files can use the exact same relative imports as their
 * framework counterparts and everything "just works".
 */
export function projectOverlayPlugin(project: string): Plugin {
  const rootDir = path.resolve(__dirname, "..");
  const srcDir = path.resolve(__dirname, "src");
  const projectDir = path.resolve(rootDir, "projects", project, "client");
  const sep = path.sep;

  function inProject(p: string) {
    return p.startsWith(projectDir + sep) || p === projectDir;
  }

  function inSrc(p: string) {
    return p.startsWith(srcDir + sep) || p === srcDir;
  }

  function projectOverride(frameworkPath: string): string | null {
    if (!frameworkPath.startsWith(srcDir + sep)) return null;
    const rel = path.relative(srcDir, frameworkPath);
    // Don't double-nest — if the resolved path is already inside projects/
    if (rel.startsWith("projects" + sep)) return null;
    return resolveWithExts(path.join(projectDir, rel));
  }

  return {
    name: "vite-project-overlay",
    enforce: "pre",

    async resolveId(id: string, importer: string | undefined) {
      if (!importer || id.startsWith("\0")) return null;

      const importerInSrc = inSrc(importer);
      const importerInProject = inProject(importer);
      if (!importerInSrc && !importerInProject) return null;

      // ── Bare specifier from a project file ──
      // Vite 8 fails to resolve node_modules for files outside the project
      // root.  Re-resolve against a framework file inside src/ so Vite's
      // built-in resolver can walk the correct node_modules tree, then
      // check whether the resolved framework file has a project override.
      if (importerInProject && !id.startsWith(".")) {
        const resolution = await this.resolve(
          id,
          srcDir + "/index.tsx",
          { skipSelf: true },
        );
        if (!resolution) return null;
        const override = projectOverride(resolution.id);
        return override ? { ...resolution, id: override } : resolution;
      }

      // Only handle relative imports.
      if (!id.startsWith(".")) return null;


      if (!importerInProject) {
        // ── Framework file importing something ──
        // Resolve normally, then check for a project override.
        const target = path.resolve(path.dirname(importer), id);
        const resolved = resolveWithExts(target);
        if (!resolved) return null;
        return projectOverride(resolved) ?? null;
      }

      // ── Project file importing something relative ──
      const target = path.resolve(path.dirname(importer), id);
      const resolved = resolveWithExts(target);

      if (resolved) {
        // File found; if it's a framework file, check for a project override.
        if (!inProject(resolved)) {
          return projectOverride(resolved) ?? null;
        }
        // Already a project file — let Vite handle normally.
        return null;
      }

      // File not found relative to project location.
      // Fall back: resolve the same import relative to the framework
      // equivalent path.
      const frameworkImporter = importer.replace(
        projectDir + sep,
        srcDir + sep,
      );
      const frameworkTarget = path.resolve(
        path.dirname(frameworkImporter),
        id,
      );
      const frameworkResolved = resolveWithExts(frameworkTarget);
      if (!frameworkResolved) return null;

      // Prefer a project override; otherwise use the framework file.
      return projectOverride(frameworkResolved) ?? frameworkResolved;
    },
  };
}
