import * as path from "path";
import * as fs from "fs";
import type { Plugin } from "vite";

// ── Meta tag config interface ────────────────────────────────

interface ProjectMeta {
  title?: string;
  description?: string;
  url?: string;
  siteName?: string;
  image?: string;
  imageAlt?: string;
  imageWidth?: string;
  imageHeight?: string;
  twitterCard?: "summary" | "summary_large_image" | "app" | "player";
  twitterSite?: string;
}

// ── Default meta for sites without a project config ──────────

const DEFAULT_META: ProjectMeta = {
  title: "AIRunner",
  description: "AI Runner — build and deploy AI-powered applications.",
  url: "https://airunner.ai",
  siteName: "AIRunner",
  twitterCard: "summary",
};

// ── HTML entity escaping ─────────────────────────────────────

const QUOT = '"';
const AMP = "&";

function escapeHtml(str: string): string {
  let result = "";
  for (const ch of str) {
    switch (ch) {
      case AMP:
        result += AMP + "amp;";
        break;
      case QUOT:
        result += AMP + "quot;";
        break;
      case "<":
        result += AMP + "lt;";
        break;
      case ">":
        result += AMP + "gt;";
        break;
      default:
        result += ch;
    }
  }
  return result;
}

// ── Tag generation ───────────────────────────────────────────

function buildMetaTags(meta: ProjectMeta): string {
  const tags: string[] = [];

  // Standard SEO
  if (meta.title) {
    tags.push(`<title>${escapeHtml(meta.title)}</title>`);
  }
  if (meta.description) {
    tags.push(
      `<meta name="description" content="${escapeHtml(meta.description)}" />`,
    );
  }

  // Open Graph
  if (meta.title) {
    tags.push(
      `<meta property="og:title" content="${escapeHtml(meta.title)}" />`,
    );
  }
  if (meta.description) {
    tags.push(
      `<meta property="og:description" content="${escapeHtml(meta.description)}" />`,
    );
  }
  if (meta.url) {
    tags.push(`<meta property="og:url" content="${escapeHtml(meta.url)}" />`);
  }
  if (meta.siteName) {
    tags.push(
      `<meta property="og:site_name" content="${escapeHtml(meta.siteName)}" />`,
    );
  }
  tags.push('<meta property="og:type" content="website" />');
  if (meta.image) {
    tags.push(
      `<meta property="og:image" content="${escapeHtml(meta.image)}" />`,
    );
    if (meta.imageAlt) {
      tags.push(
        `<meta property="og:image:alt" content="${escapeHtml(meta.imageAlt)}" />`,
      );
    }
    if (meta.imageWidth) {
      tags.push(
        `<meta property="og:image:width" content="${escapeHtml(meta.imageWidth)}" />`,
      );
    }
    if (meta.imageHeight) {
      tags.push(
        `<meta property="og:image:height" content="${escapeHtml(meta.imageHeight)}" />`,
      );
    }
  }

  // Twitter Card
  const card = meta.twitterCard || "summary_large_image";
  tags.push(`<meta name="twitter:card" content="${card}" />`);
  if (meta.title) {
    tags.push(
      `<meta name="twitter:title" content="${escapeHtml(meta.title)}" />`,
    );
  }
  if (meta.description) {
    tags.push(
      `<meta name="twitter:description" content="${escapeHtml(meta.description)}" />`,
    );
  }
  if (meta.image) {
    tags.push(
      `<meta name="twitter:image" content="${escapeHtml(meta.image)}" />`,
    );
  }
  if (meta.twitterSite) {
    tags.push(
      `<meta name="twitter:site" content="${escapeHtml(meta.twitterSite)}" />`,
    );
  }

  return `\n    <!-- Social media meta tags -->\n    ${tags.join("\n    ")}\n`;
}

// ── Config loading ───────────────────────────────────────────

function loadMetaConfig(): ProjectMeta {
  const project = process.env.VITE_PROJECT;
  if (project) {
    const projectDir = path.resolve(
      __dirname,
      "..",
      "projects",
      project,
      "client",
    );
    const metaPath = path.join(projectDir, "meta.json");
    try {
      if (fs.existsSync(metaPath)) {
        const raw = JSON.parse(fs.readFileSync(metaPath, "utf-8"));
        return { ...DEFAULT_META, ...raw };
      }
    } catch {
      console.warn("[meta-plugin] Could not read meta.json from", metaPath);
    }
  }
  return DEFAULT_META;
}

// ── Plugin ───────────────────────────────────────────────────

/**
 * Injects Open Graph, Twitter Card, and SEO meta tags into the
 * HTML head at build time. Reads configuration from the project's
 * meta.json when VITE_PROJECT is set; falls back to generic
 * AIRunner defaults otherwise.
 */
export function metaPlugin(): Plugin {
  const meta = loadMetaConfig();

  return {
    name: "vite-meta-tags",
    enforce: "post",

    transformIndexHtml(html: string) {
      const tags = buildMetaTags(meta);
      // Remove any existing <title> so ours takes precedence.
      let result = html.replace(/<title>.*?<\/title>/, "");
      result = result.replace("</head>", `${tags}  </head>`);
      return result;
    },
  };
}
