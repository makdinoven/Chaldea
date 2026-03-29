const YANDEX_SPELLER_URL =
  'https://speller.yandex.net/services/spellservice.json/checkText';

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
 * Calls Yandex.Speller API to check Russian text for spelling errors.
 * Only plain text should be passed (strip HTML before calling).
 */
export const checkSpelling = async (text: string): Promise<SpellError[]> => {
  const params = new URLSearchParams({
    text,
    lang: 'ru',
    options: '0',
  });

  const response = await fetch(`${YANDEX_SPELLER_URL}?${params.toString()}`);

  if (!response.ok) {
    throw new Error('Сервис проверки правописания недоступен');
  }

  const data: YandexSpellerResponse[] = await response.json();

  return data.map((item) => ({
    word: item.word,
    pos: item.pos,
    len: item.len,
    suggestions: item.s,
  }));
};

/**
 * Replaces a word at a given plain-text position inside an HTML string,
 * preserving all HTML tags and formatting.
 *
 * Walks through the HTML, tracking a plain-text offset that skips tags.
 * When the offset matches `pos`, replaces the next `len` chars of non-tag
 * text with `replacement`.
 */
export const replaceWordInHtml = (
  html: string,
  pos: number,
  len: number,
  replacement: string,
): string => {
  let plainOffset = 0;
  let i = 0;
  let result = '';
  let replaced = false;

  while (i < html.length) {
    // Skip HTML tags — copy them as-is
    if (html[i] === '<') {
      const tagEnd = html.indexOf('>', i);
      if (tagEnd === -1) {
        // Malformed HTML — copy rest as-is
        result += html.slice(i);
        break;
      }
      result += html.slice(i, tagEnd + 1);
      i = tagEnd + 1;
      continue;
    }

    // Plain text character
    if (!replaced && plainOffset >= pos && plainOffset < pos + len) {
      // We are inside the word to replace — collect remaining chars of the word
      let charsToSkip = len - (plainOffset - pos);
      // Insert replacement at the start of the word match
      if (plainOffset === pos) {
        result += replacement;
      }
      // Skip plain-text chars that belong to the old word, but copy any tags inside
      while (charsToSkip > 0 && i < html.length) {
        if (html[i] === '<') {
          const tagEnd = html.indexOf('>', i);
          if (tagEnd === -1) {
            break;
          }
          result += html.slice(i, tagEnd + 1);
          i = tagEnd + 1;
        } else {
          charsToSkip--;
          plainOffset++;
          i++;
        }
      }
      replaced = true;
      continue;
    }

    result += html[i];
    plainOffset++;
    i++;
  }

  return result;
};
