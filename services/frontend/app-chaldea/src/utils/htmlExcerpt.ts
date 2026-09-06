/**
 * FEAT-154 — turning an Архив article (HTML) into a plain-text excerpt.
 *
 * The article body comes from the backend as HTML. It is NEVER rendered with
 * `dangerouslySetInnerHTML` outside the Архив pages themselves: besides the
 * obvious XSS surface, cutting HTML at N characters slices through the middle
 * of a tag and the layout breaks in unpredictable ways. So we strip the markup,
 * keep the text, and cut the TEXT on a word/sentence boundary.
 */

/** Block-level tags whose end (or self-close) becomes a line break. */
const BLOCK_BREAK_RE =
  /<\/(p|div|h[1-6]|li|tr|blockquote|section|article|figcaption)\s*>|<br\s*\/?>/gi;

/** Tags whose *content* must not survive at all. */
const DROPPED_CONTENT_RE = /<(script|style)[\s\S]*?<\/\1\s*>/gi;

/**
 * Strips HTML markup and returns readable plain text.
 *
 * Uses `DOMParser`, which parses into a detached document — no scripts run and
 * no resources are fetched. Falls back to a regex strip if `DOMParser` is
 * unavailable (SSR / exotic environments).
 */
export const htmlToPlainText = (html: string): string => {
  if (!html) return '';

  const withBreaks = html.replace(DROPPED_CONTENT_RE, ' ').replace(BLOCK_BREAK_RE, '\n');

  let text: string;
  if (typeof DOMParser !== 'undefined') {
    const doc = new DOMParser().parseFromString(withBreaks, 'text/html');
    text = doc.body?.textContent ?? '';
  } else {
    text = withBreaks.replace(/<[^>]*>/g, '');
  }

  return text
    .replace(/\r\n?/g, '\n')
    // Collapse runs of spaces/tabs, but keep newlines — they carry paragraphs.
    .replace(/[^\S\n]+/g, ' ')
    .replace(/[ ]*\n[ ]*/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
};

export interface TextExcerpt {
  text: string;
  /** `true` when the source was longer than the limit and the text was cut. */
  truncated: boolean;
}

/**
 * Cuts `text` to about `limit` characters on a sentence boundary when one is
 * near the limit, otherwise on a word boundary. Never cuts mid-word.
 */
export const excerptText = (text: string, limit: number): TextExcerpt => {
  const source = text.trim();
  if (source.length <= limit) return { text: source, truncated: false };

  // Look a little past the limit so a sentence ending right after it still wins.
  const window = source.slice(0, limit);
  const sentenceEnd = Math.max(
    window.lastIndexOf('. '),
    window.lastIndexOf('! '),
    window.lastIndexOf('? '),
    window.lastIndexOf('.\n'),
    window.lastIndexOf('!\n'),
    window.lastIndexOf('?\n'),
  );

  // Only trust a sentence boundary if it does not throw away too much text.
  if (sentenceEnd >= limit * 0.6) {
    return { text: source.slice(0, sentenceEnd + 1).trim(), truncated: true };
  }

  const wordEnd = window.lastIndexOf(' ');
  const cut = wordEnd > 0 ? wordEnd : limit;
  return { text: `${source.slice(0, cut).trim()}…`, truncated: true };
};

/** Convenience: HTML in, ready-to-render excerpt out. */
export const htmlExcerpt = (html: string, limit: number): TextExcerpt =>
  excerptText(htmlToPlainText(html), limit);
