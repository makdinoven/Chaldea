/**
 * The single sanitiser for player-written post HTML.
 *
 * Roleplay posts are authored in the TipTap editor
 * (`components/CommonComponents/WysiwygEditor`) and stored as raw HTML. Every
 * renderer feeds that HTML to `dangerouslySetInnerHTML`, so this module is the
 * only thing standing between one player's markup and every other player's
 * (and every moderator's) browser.
 *
 * ## Why an allow-list, not a deny-list
 *
 * The editor's output is a **known, bounded set**: StarterKit's nodes/marks
 * plus Underline, TextAlign, TextStyle, Color, Highlight, Link, ResizableImage
 * and ArchiveLink. We can enumerate every tag and attribute it can emit, so we
 * do, and drop everything else.
 *
 * A deny-list only closes the holes we happened to think of. DOMPurify's
 * defaults keep `<form>`, `<input>`, `<button>`, `<select>`, `<textarea>`,
 * `<label>`, `<style>`, `<audio>`, `<video>`, `<svg>` and more. That is how a
 * player could paste a convincing fake login form pointing at their own server
 * into a location feed, or ship a `<style>` block whose selectors reach the
 * *whole page* and hide or cover other players' posts. Neither serves any
 * authoring purpose. An allow-list fails closed: a tag we never listed --
 * including one a future DOMPurify release starts permitting -- is gone.
 *
 * ## The `style` attribute
 *
 * Inline `style` cannot be dropped wholesale: text colour (`Color`), highlight
 * (`Highlight`), alignment (`TextAlign`) and image sizing (`ResizableImage`)
 * all live there, and FEAT-157 deliberately relies on the author's own colour
 * surviving. So `style` survives, but only an allow-list of CSS **properties**
 * does -- the ones the editor actually emits, each pinned to the tags it can
 * appear on and to a pattern its value must match. That removes `position`,
 * `z-index`, `top`/`left`, `transform`, `opacity`, `pointer-events`,
 * `font-size` and every other property that lets a post escape its own box or
 * cover the interface, and it also stops a legitimate property from being
 * turned into a weapon: `width` exists for images, so it is capped to `px`/`%`
 * on `div`/`img` and a `width: 100vw` box never survives.
 *
 * ## What is still possible, honestly
 *
 * - Colour abuse inside the post: text painted the same colour as the card, or
 *   a loud highlight. It stays inside the post's own box; that is a moderation
 *   matter, not an XSS one.
 * - External links. `<a href="https://...">` is a legitimate feature, so a
 *   player can still write «войдите здесь» over a link to a phishing page. The
 *   sanitiser cannot tell that from a normal link -- moderation can.
 * - Images from arbitrary hosts (the editor takes an image URL), which leaks
 *   the viewer's IP to that host and can be a large download. Unchanged by
 *   this module; worth a separate policy decision.
 */
import DOMPurify from 'dompurify';

/**
 * Own DOMPurify instance. Hooks registered with `addHook` are **per-instance**,
 * and the app sanitises other, differently-trusted content elsewhere (archive
 * articles, rules -- both admin-authored). Using the shared default instance
 * would silently apply this post policy to those too.
 */
const purifier = DOMPurify(window);

/**
 * Every tag the editor can produce. `figure`/`div`/`img` are the
 * ResizableImage wrapper; `b`/`i`/`del`/`strike` are legacy synonyms that
 * pasted content may still carry.
 */
const ALLOWED_TAGS = [
  'p', 'br', 'hr',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'ul', 'ol', 'li',
  'blockquote', 'pre', 'code',
  'strong', 'b', 'em', 'i', 's', 'del', 'strike', 'u', 'mark', 'span',
  'a',
  'figure', 'div', 'img',
];

/**
 * `data-archive-slug` is what the archive-link feature keys off
 * (`ArchiveLinkExtension` / `ArchiveLinkPreview`) -- dropping it would silently
 * break archive links. `data-color` is Highlight's, `data-type`/`data-align`
 * are ResizableImage's. Note there is deliberately no `id` (DOM clobbering),
 * no `on*` (DOMPurify drops those anyway), no `width`/`height` attributes (the
 * editor sizes images through `style`), and no `target` -- DOMPurify's defaults
 * already dropped `target`, so keeping it would newly let a post open tabs.
 */
const ALLOWED_ATTR = [
  'href', 'rel',
  'class', 'style',
  'src', 'alt',
  'data-archive-slug', 'data-color', 'data-type', 'data-align',
];

/** Colour-ish values: `rgb(...)`, `#f0d95c`, `red`, `inherit`, `transparent`. */
const COLOUR_VALUE = /^[a-z0-9#.,%()\s]+$/i;
/** One length. Deliberately no viewport units -- `100vw` is how a box escapes. */
const LENGTH_VALUE = /^(auto|0|\d+(\.\d+)?(px|%|em|rem))$/i;
/** Up to four lengths, for the `margin` shorthand (`0 auto`). */
const MARGIN_VALUE = /^(auto|0|\d+(\.\d+)?(px|%|em|rem))(\s+(auto|0|\d+(\.\d+)?(px|%|em|rem))){0,3}$/i;

const TEXT_TAGS = null; // any allowed tag
const BLOCK_TAGS = new Set(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'figure']);
const IMAGE_BOX_TAGS = new Set(['div']);
const IMAGE_TAGS = new Set(['img']);

interface StyleRule {
  /** Tags the property may appear on; `null` means any allowed tag. */
  tags: Set<string> | null;
  /** Pattern the property's value must match in full. */
  value: RegExp;
}

/**
 * CSS the editor emits, property by property, pinned to where it may appear.
 *
 * - `color` — TextStyle/Color, on anything.
 * - `background-color` — Highlight, and Highlight only renders `<mark>`.
 * - `text-align` — TextAlign (headings + paragraphs) and the image `<figure>`.
 * - `display`/`width`/`max-width`/`margin*` — the ResizableImage wrapper `<div>`.
 * - `width`/`height` — the `<img>` itself (`width: 100%; height: auto`).
 *
 * Shorthands are listed alongside their longhands because engines disagree on
 * which of the two `CSSStyleDeclaration` enumerates; listing both keeps a
 * legitimate `margin: 0 auto` byte-identical instead of re-serialised.
 */
const STYLE_RULES: Record<string, StyleRule> = {
  'color': { tags: TEXT_TAGS, value: COLOUR_VALUE },
  'background-color': { tags: new Set(['mark']), value: COLOUR_VALUE },
  'text-align': { tags: BLOCK_TAGS, value: /^(left|center|right|justify|start|end)$/i },
  'display': { tags: IMAGE_BOX_TAGS, value: /^inline-block$/i },
  'max-width': { tags: IMAGE_BOX_TAGS, value: LENGTH_VALUE },
  'width': { tags: new Set([...IMAGE_BOX_TAGS, ...IMAGE_TAGS]), value: LENGTH_VALUE },
  'height': { tags: IMAGE_TAGS, value: LENGTH_VALUE },
  'margin': { tags: IMAGE_BOX_TAGS, value: MARGIN_VALUE },
  'margin-top': { tags: IMAGE_BOX_TAGS, value: LENGTH_VALUE },
  'margin-right': { tags: IMAGE_BOX_TAGS, value: LENGTH_VALUE },
  'margin-bottom': { tags: IMAGE_BOX_TAGS, value: LENGTH_VALUE },
  'margin-left': { tags: IMAGE_BOX_TAGS, value: LENGTH_VALUE },
};

/**
 * Extra guard on top of the per-property patterns, for values that could pull
 * in an external resource or a CSS variable: `url(...)`, legacy IE
 * `expression(...)`, `image-set(...)`, custom properties, at-rules, escapes.
 */
const UNSAFE_STYLE_VALUE = /url\s*\(|expression\s*\(|image-set|--|@|\\/i;

/**
 * Classes the editor emits. Arbitrary classes are dropped: the compiled CSS
 * bundle contains real layout/overlay utilities (`modal-overlay`, `fixed`, ...),
 * so a free-form `class` is a second route to covering the page.
 */
const ALLOWED_CLASSES = new Set(['archive-link', 'editor-link']);

/**
 * Strips disallowed CSS declarations. Leaves the attribute **byte-identical**
 * when nothing had to go, so legitimate posts render exactly as before rather
 * than through a re-serialisation.
 */
const filterStyle = (el: Element): void => {
  if (!el.hasAttribute('style')) return;

  const style = (el as HTMLElement).style;
  if (!style) {
    el.removeAttribute('style');
    return;
  }

  const tag = el.tagName.toLowerCase();
  const doomed: string[] = [];
  for (let i = 0; i < style.length; i += 1) {
    const prop = style[i];
    const rule = STYLE_RULES[prop];
    const value = style.getPropertyValue(prop).trim();
    const ok =
      rule !== undefined &&
      (rule.tags === null || rule.tags.has(tag)) &&
      rule.value.test(value) &&
      !UNSAFE_STYLE_VALUE.test(value);
    if (!ok) doomed.push(prop);
  }
  if (doomed.length === 0) return;

  doomed.forEach((prop) => style.removeProperty(prop));
  if (style.length === 0) el.removeAttribute('style');
};

/** Same contract as {@link filterStyle}, for `class`. */
const filterClass = (el: Element): void => {
  if (!el.hasAttribute('class')) return;

  const original = (el.getAttribute('class') ?? '').split(/\s+/).filter(Boolean);
  const kept = original.filter((name) => ALLOWED_CLASSES.has(name));
  if (kept.length === original.length) return;

  if (kept.length === 0) el.removeAttribute('class');
  else el.setAttribute('class', kept.join(' '));
};

purifier.addHook('afterSanitizeAttributes', (node) => {
  if (node.nodeType !== 1) return;
  filterStyle(node as Element);
  filterClass(node as Element);
});

/**
 * Sanitises player-written post HTML for `dangerouslySetInnerHTML`.
 *
 * @param html Raw stored post content (TipTap HTML). A nullish value is
 *   tolerated and yields an empty string.
 * @returns HTML safe to inject: no scripts, no event handlers, no
 *   `javascript:` URLs, no forms or inputs, no page-wide `<style>`, and only
 *   the CSS properties the editor itself uses.
 *
 * **Never loosen this.** Both render surfaces (`LocationPage/PostCard.tsx` and
 * `AdminModerationPage.tsx`) call it and nothing else; a new surface must call
 * it too rather than re-deriving a config.
 */
export const sanitizePostHtml = (html: string | null | undefined): string =>
  purifier.sanitize(html ?? '', {
    ALLOWED_TAGS,
    ALLOWED_ATTR,
    ALLOW_DATA_ATTR: false,
    ALLOW_ARIA_ATTR: false,
    ALLOW_UNKNOWN_PROTOCOLS: false,
  });

export default sanitizePostHtml;
