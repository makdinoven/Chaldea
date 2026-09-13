const YANDEX_SPELLER_URL =
  'https://speller.yandex.net/services/spellservice.json/checkText';

/** Hard ceiling for a single speller request (FEAT-157, T2). */
const SPELLCHECK_TIMEOUT_MS = 10_000;

export interface YandexSpellerResponse {
  code: number;
  pos: number;
  row: number;
  col: number;
  len: number;
  word: string;
  s: string[];
}

export interface SpellError {
  word: string;
  pos: number;
  len: number;
  suggestions: string[];
}

/**
 * Failure of the spell-check request. `message` is always a player-facing
 * Russian string; `status` is the HTTP status when there was one.
 */
export class SpellCheckError extends Error {
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = 'SpellCheckError';
    this.status = status;
  }
}

/**
 * Calls Yandex.Speller API to check Russian text for spelling errors.
 *
 * FEAT-157 (T2): the text goes in a form-encoded **POST body**, never in the
 * query string — Cyrillic costs 6 URL characters per letter, so a normal RP
 * post produced a multi-kilobyte URL that intermediaries rejected with 414.
 * The call stays client-side on purpose: the endpoint answers with
 * `access-control-allow-origin: *`, advertises `OPTIONS, GET, POST` and was
 * measured accepting a ~10.8 KB Cyrillic body, and Yandex's quota is counted
 * per calling IP — so keeping it in the browser spreads it over the players
 * instead of funnelling the whole game through the server's single IP.
 *
 * `application/x-www-form-urlencoded` is a CORS-simple content type, so the
 * normal path does not even trigger a preflight.
 *
 * Only plain text should be passed — use `htmlToSpellText(html).text`.
 *
 * @throws {SpellCheckError} with a Russian, cause-specific message.
 */
export const checkSpelling = async (text: string): Promise<SpellError[]> => {
  const body = new URLSearchParams({
    text,
    lang: 'ru',
    options: '0',
  });

  const controller = new AbortController();
  let timedOut = false;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, SPELLCHECK_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(YANDEX_SPELLER_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
      },
      body: body.toString(),
      signal: controller.signal,
    });
  } catch (e) {
    if (timedOut) {
      console.warn('[spellcheck] request timed out after', SPELLCHECK_TIMEOUT_MS, 'ms');
      throw new SpellCheckError(
        'Проверка правописания заняла слишком много времени. Попробуйте ещё раз.',
      );
    }
    // A bare `fetch` rejection cannot be told apart from a CORS failure or an
    // extension-blocked request, so the message stays generic on purpose.
    console.warn('[spellcheck] request failed:', e);
    throw new SpellCheckError(
      'Не удалось связаться с сервисом проверки правописания. Проверьте соединение и попробуйте ещё раз.',
    );
  } finally {
    clearTimeout(timer);
  }

  if (!response.ok) {
    console.warn('[spellcheck] HTTP', response.status, response.statusText);
    if (response.status === 429) {
      throw new SpellCheckError(
        'Превышен лимит проверок правописания. Попробуйте через несколько минут.',
        response.status,
      );
    }
    if (response.status >= 500) {
      throw new SpellCheckError(
        'Сервис проверки правописания сейчас недоступен. Попробуйте позже.',
        response.status,
      );
    }
    throw new SpellCheckError(
      `Сервис проверки правописания отклонил запрос (код ${response.status}).`,
      response.status,
    );
  }

  let data: YandexSpellerResponse[];
  try {
    data = await response.json();
  } catch (e) {
    console.warn('[spellcheck] malformed response:', e);
    throw new SpellCheckError('Сервис проверки правописания вернул некорректный ответ.');
  }

  if (!Array.isArray(data)) {
    console.warn('[spellcheck] unexpected response shape:', data);
    throw new SpellCheckError('Сервис проверки правописания вернул некорректный ответ.');
  }

  return data.map((item) => ({
    word: item.word,
    pos: item.pos,
    len: item.len,
    suggestions: Array.isArray(item.s) ? item.s : [],
  }));
};

/* ------------------------------------------------------------------ *
 * HTML -> plain text, with an index map (FEAT-157, T4)
 * ------------------------------------------------------------------ */

/**
 * Plain text of an HTML fragment plus the mapping back into that HTML.
 *
 * `map` / `mapEnd` / `synthetic` are parallel to `text`: for plain character
 * `i`, the original HTML characters are `html.slice(map[i], mapEnd[i])`.
 * A synthetic character (a block-boundary `\n`) has no HTML of its own —
 * `map[i] === mapEnd[i]` — and must never be part of a replaced range.
 */
export interface SpellTextMapping {
  text: string;
  map: number[];
  mapEnd: number[];
  synthetic: boolean[];
}

/** Closing/void tags that end a visual block and therefore separate words. */
const BLOCK_BOUNDARY_TAG =
  /^<\s*(?:\/\s*(?:p|div|li|ul|ol|h[1-6]|blockquote|figure|figcaption|tr|td|th|table|pre|section|article|header|footer)|br\s*\/?)\s*>$/i;

/** The handful of named entities TipTap output can realistically contain. */
const NAMED_ENTITIES: Record<string, string> = {
  // &nbsp; is decoded to a plain space so the speller tokenises words normally.
  nbsp: ' ',
  amp: '&',
  lt: '<',
  gt: '>',
  quot: '"',
  apos: "'",
  laquo: '«',
  raquo: '»',
  ldquo: '“',
  rdquo: '”',
  lsquo: '‘',
  rsquo: '’',
  mdash: '—',
  ndash: '–',
  hellip: '…',
  deg: '°',
  times: '×',
  shy: '­',
};

const ENTITY_RE = /^&(#\d{1,7}|#[xX][0-9a-fA-F]{1,6}|[a-zA-Z][a-zA-Z0-9]{1,31});/;

const decodeEntity = (source: string): string | null => {
  const m = ENTITY_RE.exec(source);
  if (!m) return null;
  const body = m[1];
  if (body[0] === '#') {
    const code =
      body[1] === 'x' || body[1] === 'X'
        ? parseInt(body.slice(2), 16)
        : parseInt(body.slice(1), 10);
    if (!Number.isFinite(code) || code <= 0 || code > 0x10ffff) return null;
    try {
      return String.fromCodePoint(code);
    } catch {
      return null;
    }
  }
  const named = NAMED_ENTITIES[body.toLowerCase()];
  return named ?? null;
};

/**
 * Single-pass HTML -> plain text walker that also records, for every plain
 * character, where it came from in the HTML (FEAT-157, section 3.3).
 *
 * Rules: tags are skipped; a `\n` is emitted at each block boundary (runs
 * collapse, no leading or trailing separator); entities are decoded; and the
 * result is deliberately **not** trimmed — trimming here while
 * `replaceWordInHtml` counted over the untrimmed HTML is exactly what made a
 * leading space duplicate the first corrected word.
 *
 * NOTE: this is **not** the same model as `stripHtmlTags` in
 * `PostCreateForm.tsx`. That one has to keep mirroring the backend's
 * `crud.strip_html_tags` byte-for-byte, because the character counter it feeds
 * drives the post gates and must not promise what the server then refuses.
 * This one is correct instead, and is used only for spell-checking.
 * Do not "unify" them.
 */
export const htmlToSpellText = (html: string): SpellTextMapping => {
  let text = '';
  const map: number[] = [];
  const mapEnd: number[] = [];
  const synthetic: boolean[] = [];

  /** A block boundary was crossed; emit the `\n` only if real text follows. */
  let pendingSeparatorAt: number | null = null;

  const push = (chunk: string, start: number, end: number, isSynthetic: boolean) => {
    for (const ch of chunk) {
      text += ch;
      map.push(start);
      mapEnd.push(end);
      synthetic.push(isSynthetic);
    }
  };

  let i = 0;
  while (i < html.length) {
    if (html[i] === '<') {
      const tagEnd = html.indexOf('>', i);
      if (tagEnd === -1) break; // malformed tail — nothing renderable follows
      const tag = html.slice(i, tagEnd + 1);
      if (BLOCK_BOUNDARY_TAG.test(tag)) {
        pendingSeparatorAt = tagEnd + 1;
      }
      i = tagEnd + 1;
      continue;
    }

    let chunk: string;
    let consumed: number;
    if (html[i] === '&') {
      const rest = html.slice(i);
      const decoded = decodeEntity(rest);
      if (decoded !== null) {
        chunk = decoded;
        consumed = ENTITY_RE.exec(rest)![0].length;
      } else {
        chunk = '&';
        consumed = 1;
      }
    } else {
      chunk = html[i];
      consumed = 1;
    }

    // Flush a pending block separator right before the next real character, so
    // runs of </p><p> collapse and no empty token is produced.
    if (pendingSeparatorAt !== null) {
      if (text.length > 0 && text[text.length - 1] !== '\n') {
        push('\n', pendingSeparatorAt, pendingSeparatorAt, true);
      }
      pendingSeparatorAt = null;
    }

    push(chunk, i, i + consumed, false);
    i += consumed;
  }

  return { text, map, mapEnd, synthetic };
};

/**
 * Replaces the plain-text range `[pos, pos + len)` inside an HTML string,
 * preserving the surrounding markup.
 *
 * FEAT-157 (T4): positions are resolved through the very same walker that
 * produced the text sent to the speller (`htmlToSpellText`), so the two can no
 * longer disagree about where a word is. Tags that happen to sit inside the
 * replaced range are kept.
 *
 * If the range cannot be resolved — outside the text, or spanning a synthetic
 * block separator — the HTML is returned **unchanged** rather than corrupted.
 */
export const replaceWordInHtml = (
  html: string,
  pos: number,
  len: number,
  replacement: string,
): string => {
  if (len <= 0 || pos < 0) return html;

  const { text, map, mapEnd, synthetic } = htmlToSpellText(html);
  if (pos + len > text.length) return html;

  for (let k = pos; k < pos + len; k += 1) {
    if (synthetic[k]) return html;
  }

  const start = map[pos];
  const end = mapEnd[pos + len - 1];
  if (start === undefined || end === undefined || end < start) return html;

  // Keep markup that lives inside the replaced range (e.g. a word split by a
  // <strong> boundary) so the post's formatting survives the correction.
  let inner = '';
  let j = start;
  while (j < end) {
    if (html[j] === '<') {
      const tagEnd = html.indexOf('>', j);
      if (tagEnd === -1 || tagEnd >= end) break;
      inner += html.slice(j, tagEnd + 1);
      j = tagEnd + 1;
    } else {
      j += 1;
    }
  }

  return html.slice(0, start) + replacement + inner + html.slice(end);
};
