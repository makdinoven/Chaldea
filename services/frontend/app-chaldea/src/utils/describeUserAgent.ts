/**
 * A short human name for a browser's User-Agent: «Chrome · Windows»,
 * «Safari · iPhone». Good enough to recognise one's own devices in a list;
 * not meant for feature detection.
 */
export const describeUserAgent = (ua: string | null | undefined): string => {
  if (!ua) return 'Неизвестное устройство';

  const browser =
    /YaBrowser/i.test(ua) ? 'Яндекс Браузер'
    : /Edg\//i.test(ua) ? 'Edge'
    : /OPR\/|Opera/i.test(ua) ? 'Opera'
    : /Firefox\//i.test(ua) ? 'Firefox'
    : /Chrome\/|CriOS/i.test(ua) ? 'Chrome'
    : /Safari\//i.test(ua) ? 'Safari'
    : null;

  const system =
    /iPhone/i.test(ua) ? 'iPhone'
    : /iPad/i.test(ua) ? 'iPad'
    : /Android/i.test(ua) ? 'Android'
    : /Windows/i.test(ua) ? 'Windows'
    : /Mac OS X|Macintosh/i.test(ua) ? 'macOS'
    : /Linux/i.test(ua) ? 'Linux'
    : null;

  if (browser && system) return `${browser} · ${system}`;
  return browser ?? system ?? 'Неизвестное устройство';
};
