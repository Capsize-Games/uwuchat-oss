export function stripMarkdownPreview(text: string): string {
  return text
    // Images (before links — images share the [alt](url) tail syntax)
    .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
    // Links
    .replace(/\[([^\]]*)\]\([^)]*\)/g, "$1")
    // Bold (before italic so ** pairs aren't partially consumed)
    .replace(/\*\*([^*]+)\*\*/g, "$1")
    .replace(/__([^_]+)__/g, "$1")
    // Strikethrough
    .replace(/~~([^~]+)~~/g, "$1")
    // Inline code
    .replace(/`([^`]+)`/g, "$1")
    // ATX headers
    .replace(/^#{1,6}\s+/gm, "")
    // Collapse multi-space and trim
    .replace(/\s{2,}/g, " ")
    .trim();
}
