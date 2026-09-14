/**
 * FEAT-160 (T7) — turning a post's stored TipTap HTML into the plain text the
 * version diff runs on.
 *
 * ## Why this is a separate function from `stripHtmlTags`
 *
 * `stripHtmlTags` in `components/pages/LocationPage/gateConstants.ts` looks like
 * it does the same job. It does not, and the two must never be merged:
 *
 * | | `gateConstants.stripHtmlTags` | `postText.htmlToPlainText` |
 * |---|---|---|
 * | Purpose | count symbols the way the SERVER counts them | produce readable text for a HUMAN diff |
 * | Model | byte-for-byte mirror of `crud.strip_html_tags` | correct extraction |
 * | Block boundaries | none — `<p>Один</p><p>Два</p>` -> `"ОдинДва"` | `\n` — paragraphs survive |
 * | Entities | not decoded — `&amp;` stays `&amp;` | decoded — `&amp;` becomes `&` |
 *
 * FEAT-157 froze `stripHtmlTags` with those quirks **on purpose**: it drives the
 * character counter, and the counter must agree with what the server charges for
 * intent gates. Fixing it is a balance decision, tracked in `docs/ISSUES.md`.
 * Using it here would instead poison the diff: two paragraphs would glue into one
 * word, and every `&nbsp;` / `&amp;` would show up as fake diff noise.
 *
 * So: **do not reuse `stripHtmlTags` here, do not "fix" it there, and do not
 * collapse these two into one helper.** Different questions, different answers.
 *
 * (A third, similarly-named `htmlToPlainText` lives in `utils/htmlExcerpt.ts`.
 * That one feeds Архив article excerpts and is tuned for excerpting — it keeps
 * blank lines between paragraphs and does not sanitise. Left alone deliberately.)
 *
 * ## Why the text and not the HTML
 *
 * Per the architecture decision (3.1): the diff shown to an admin is a
 * word-level diff of the plain text, because a diff of raw HTML turns a whole
 * passage red-and-green the moment one `<em>` appears — useless for settling
 * «что персонаж на самом деле сказал». Formatting-only edits are not swept under
 * the rug; the modal states them in words (see `isFormattingOnlyChange`) and
 * offers an escaped HTML-source panel. That is the modal's job, not this file's.
 */

import DOMPurify from 'dompurify';

/**
 * Tags whose start and end are a visual line break in the rendered post.
 * TipTap emits `p`, `h1`-`h6`, `ul`/`ol`/`li`, `blockquote` and `pre`; the rest
 * are here so pasted markup degrades sensibly.
 */
const BLOCK_TAGS = new Set([
  'P', 'DIV', 'H1', 'H2', 'H3', 'H4', 'H5', 'H6',
  'UL', 'OL', 'LI', 'BLOCKQUOTE', 'PRE', 'HR',
  'TABLE', 'TR', 'SECTION', 'ARTICLE', 'FIGURE', 'FIGCAPTION',
]);

/** Fallback entity decoding for environments without a DOM (SSR / tests). */
const FALLBACK_ENTITIES: Record<string, string> = {
  '&nbsp;': ' ',
  '&amp;': '&',
  '&lt;': '<',
  '&gt;': '>',
  '&quot;': '"',
  '&#39;': "'",
  '&apos;': "'",
};

/** Depth-first walk emitting text fragments, with `\n` at block boundaries. */
const collect = (node: Node, out: string[]): void => {
  node.childNodes.forEach((child) => {
    if (child.nodeType === Node.TEXT_NODE) {
      out.push(child.nodeValue ?? '');
      return;
    }
    if (child.nodeType !== Node.ELEMENT_NODE) return;

    const tag = (child as Element).tagName;
    if (tag === 'BR') {
      out.push('\n');
      return;
    }
    const isBlock = BLOCK_TAGS.has(tag);
    if (isBlock) out.push('\n');
    collect(child, out);
    if (isBlock) out.push('\n');
  });
};

/**
 * Normalises extracted text so that only meaningful differences reach the diff.
 *
 * - CRLF -> LF;
 * - every run of non-newline whitespace (including the NBSP that `&nbsp;`
 *   decodes to) collapses to a single space, so an invisible whitespace change
 *   does not read as an edit;
 * - a run of newlines collapses to exactly one — one paragraph boundary is one
 *   `\n`, which is what the diff renderer draws a line break for.
 */
const normalise = (text: string): string =>
  text
    .replace(/\r\n?/g, '\n')
    .replace(/[^\S\n]+/g, ' ')
    .replace(/ *\n */g, '\n')
    .replace(/\n+/g, '\n')
    .trim();

/**
 * Post HTML in, readable plain text out.
 *
 * Sanitises with DOMPurify, parses the result into a **detached** document (no
 * scripts run, no resources are fetched), then walks it so block boundaries
 * become `\n` and HTML entities are decoded by the parser itself.
 *
 * `null`, `undefined` and `''` all yield `''` — a missing version is not an
 * error here, the modal renders it as an empty side of the diff.
 */
export const htmlToPlainText = (html: string | null | undefined): string => {
  if (!html) return '';

  const canUseDom = typeof DOMParser !== 'undefined';
  if (!canUseDom) {
    // No DOM: strip tags, decode the handful of entities TipTap can emit.
    let text = html.replace(/<(script|style)[\s\S]*?<\/\1\s*>/gi, ' ');
    text = text
      .replace(/<\/(p|div|h[1-6]|ul|ol|li|blockquote|pre|tr|section|article|figcaption)\s*>/gi, '\n')
      .replace(/<(br|hr)\s*\/?>/gi, '\n')
      .replace(/<[^>]*>/g, '');
    text = text.replace(/&nbsp;|&amp;|&lt;|&gt;|&quot;|&#39;|&apos;/gi, (m) =>
      FALLBACK_ENTITIES[m.toLowerCase()] ?? m,
    );
    return normalise(text);
  }

  const clean = DOMPurify.sanitize(html, { USE_PROFILES: { html: true } });
  const doc = new DOMParser().parseFromString(clean, 'text/html');
  const out: string[] = [];
  if (doc.body) collect(doc.body, out);

  return normalise(out.join(''));
};

/**
 * True when the edit changed only the markup — the words are identical but the
 * HTML is not.
 *
 * Drives the «Текст не изменился — правка коснулась только оформления.» banner
 * (3.1, case 2): without it a purely cosmetic edit would render as an empty diff
 * and read as «ничего не менялось», which is untrue.
 */
export const isFormattingOnlyChange = (
  before: string | null | undefined,
  after: string | null | undefined,
): boolean => {
  const rawBefore = before ?? '';
  const rawAfter = after ?? '';
  if (rawBefore === rawAfter) return false;
  return htmlToPlainText(rawBefore) === htmlToPlainText(rawAfter);
};
