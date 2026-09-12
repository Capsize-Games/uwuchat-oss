/**
 * Repair tokenizer word-boundary artifacts in a streamed LLM reply.
 *
 * Byte-level BPE tokenizers stream sub-word tokens where digits are
 * emitted as separate space-prefixed tokens (`'1'`, `' 2'`, `' 3'` →
 * naive concat "1 2 3").  This artifact is model/tokenizer-agnostic —
 * any BPE model (local GGUF or cloud) can exhibit it — so this
 * normalization is applied to every streamed completion before it is
 * stored or displayed.
 *
 * Deliberately does NOT insert a space between a digit run and a
 * following letter: identifiers and hashes are overwhelmingly
 * alphanumeric (hex worktree IDs, commit SHAs, version numbers like
 * "2.98.0", "issue #162"), and re-spacing them corrupts real content
 * the model is quoting ("airunner-71 a8 e2 d7").
 */

/** Collapse spaces inside digit runs (single-digit-token sub-words). */
export function normalizeStreamedSpacing(text: string): string {
  if (!text) return text;
  // "1 2 3" / "2 0 2 6" → contiguous digits (single-digit-token
  // sub-words of one number).  A real "1 2 3" list is uncommon and
  // usually written with commas; the tokenizer artifact is the far
  // more likely case.
  return text.replace(/(?<=\d) (?=\d)/g, "");
}
