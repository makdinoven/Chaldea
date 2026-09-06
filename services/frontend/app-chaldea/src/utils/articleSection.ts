/**
 * FEAT-154 — pulling a *part* of an Архив article out of its HTML.
 *
 * `htmlExcerpt` answers «show me the beginning of this article». That is what
 * the «Родина» step needs. The «Присяга» step needs something else: the two
 * lists of offences live in the *middle* of the «Скитальцы» article, under the
 * heading «Законы и правила», and an excerpt of the opening paragraphs would
 * never reach them.
 *
 * So this module parses the article and returns the part we want as
 * **structured blocks** — paragraphs and lists — which the component renders as
 * real React elements. The article body is HTML, but it is NEVER handed to
 * `dangerouslySetInnerHTML`: `DOMParser` builds a detached document (no scripts
 * run, no resources are fetched) and only `textContent` ever leaves this file.
 *
 * Two lookups are offered, and the caller is meant to use them in order —
 * the precise one first, the forgiving one as a safety net for a rewritten
 * article:
 *
 * 1. `extractArticleSection` — «everything under the heading X».
 * 2. `extractArticleBlocksFrom` — «everything from the first block that talks
 *    about X», which survives the heading being renamed or dropped.
 */

export type ArticleBlock =
  | { kind: 'paragraph'; text: string }
  | { kind: 'list'; ordered: boolean; items: string[] };

const HEADING_TAGS = new Set(['H1', 'H2', 'H3', 'H4', 'H5', 'H6']);

/** Whitespace- and case-insensitive comparison of two headings. */
const normalize = (value: string): string =>
  value.replace(/\s+/g, ' ').trim().toLowerCase();

/** Collapses the runs of whitespace `textContent` leaves behind. */
const cleanText = (value: string): string => value.replace(/\s+/g, ' ').trim();

/** Parses the article body, or `null` when it cannot be parsed at all. */
const parseBody = (html: string | null | undefined): HTMLElement | null => {
  if (!html || typeof DOMParser === 'undefined') return null;
  try {
    return new DOMParser().parseFromString(html, 'text/html').body ?? null;
  } catch {
    return null;
  }
};

/** One top-level element → one block, or `null` when it carries no text. */
const toBlock = (node: Element): ArticleBlock | null => {
  if (node.tagName === 'OL' || node.tagName === 'UL') {
    const items = Array.from(node.children)
      .map((item) => cleanText(item.textContent ?? ''))
      .filter(Boolean);
    return items.length > 0
      ? { kind: 'list', ordered: node.tagName === 'OL', items }
      : null;
  }
  const text = cleanText(node.textContent ?? '');
  return text ? { kind: 'paragraph', text } : null;
};

/**
 * Returns the blocks that follow the heading whose text matches `headingText`,
 * up to the next heading of any level. An empty array means «not found».
 *
 * The match is exact after normalisation, so a renamed heading in the Архив
 * degrades to «not found» instead of silently grabbing the wrong section.
 */
export const extractArticleSection = (
  html: string | null | undefined,
  headingText: string,
): ArticleBlock[] => {
  const body = parseBody(html);
  if (!body) return [];

  const wanted = normalize(headingText);
  const children = Array.from(body.children);
  const startIndex = children.findIndex(
    (node) => HEADING_TAGS.has(node.tagName) && normalize(node.textContent ?? '') === wanted,
  );
  if (startIndex === -1) return [];

  const blocks: ArticleBlock[] = [];
  for (const node of children.slice(startIndex + 1)) {
    if (HEADING_TAGS.has(node.tagName)) break;
    const block = toBlock(node);
    if (block) blocks.push(block);
  }
  return blocks;
};

export interface BlocksFromOptions {
  /** Hard cap, so a match near the top cannot drag in half the article. */
  maxBlocks?: number;
}

/**
 * The forgiving lookup: returns the blocks starting at the first non-heading
 * element whose text matches `pattern`, stopping at the next heading.
 *
 * This is the safety net for `extractArticleSection`. If a lore editor renames
 * «Законы и правила», the section lookup fails, but the paragraph that
 * introduces Анафема is still in the article and still says «Анафема» — so the
 * player still gets the real rules rather than an empty panel.
 */
export const extractArticleBlocksFrom = (
  html: string | null | undefined,
  pattern: RegExp,
  { maxBlocks = 20 }: BlocksFromOptions = {},
): ArticleBlock[] => {
  const body = parseBody(html);
  if (!body) return [];

  const children = Array.from(body.children);
  const startIndex = children.findIndex(
    (node) => !HEADING_TAGS.has(node.tagName) && pattern.test(node.textContent ?? ''),
  );
  if (startIndex === -1) return [];

  const blocks: ArticleBlock[] = [];
  for (const node of children.slice(startIndex)) {
    if (HEADING_TAGS.has(node.tagName)) break;
    const block = toBlock(node);
    if (block) blocks.push(block);
    if (blocks.length >= maxBlocks) break;
  }
  return blocks;
};
