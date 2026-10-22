import { SEGMENT_LABELS, YEAR_SEGMENTS } from '../../../utils/gameTime';
import { parseServerDate } from '../../../utils/serverDate';
import type { PassportData } from './types';

/**
 * How the passport puts its data into words. Shared by every surface that
 * prints a passport — the sheet itself and the paper copy lying on the skill
 * tree's table — so the two always read the same.
 */

export const DASH = '—';

export const SEX_LABELS: Record<string, string> = {
  male: 'Мужской',
  female: 'Женский',
  genderless: 'Бесполый',
};

export const formatRegisteredAt = (iso: string | null | undefined): string => {
  if (!iso) return DASH;
  const date = parseServerDate(iso);
  if (!date) return DASH;
  return date.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
};

/** «Весна 1787 г.» — the segment index maps into the shared game calendar. */
export const formatTenure = (data: PassportData, currentGameYear?: number | null): string => {
  const tenure = data.skitaltsySince;
  if (!tenure) return DASH;

  const segment =
    typeof tenure.segment === 'number' ? YEAR_SEGMENTS[tenure.segment] : undefined;
  const segmentLabel = segment ? SEGMENT_LABELS[segment.name] : undefined;
  const base = segmentLabel ? `${segmentLabel} ${tenure.year} г.` : `${tenure.year} г.`;

  if (typeof currentGameYear !== 'number') return base;
  const years = currentGameYear - tenure.year;
  if (years < 0) return base;
  return `${base} (в строю ${years} ${years === 1 ? 'год' : years < 5 ? 'года' : 'лет'})`;
};

/** «Рюджин из Империи Шинзо» — the one line that carries the most identity. */
export const formatLineage = (data: PassportData): string => {
  const who = data.subraceName ?? data.raceName;
  if (who && data.origin?.name) return `${who} из ${data.origin.name}`;
  return who ?? data.origin?.name ?? DASH;
};

/**
 * The only `src` we are willing to hand to an `<img>`.
 *
 * `characters.avatar` still carries legacy junk — literally the string
 * `"string"`, the trace of the very bug FEAT-154 fixed. Such a value is
 * TRUTHY, so a bare `avatarUrl || subraceImage` fallback never fires and the
 * browser resolves `src="string"` against the current path: a `GET
 * /characters/string` (405) and a broken tile in the grid.
 *
 * Deliberately cheap and predictable rather than real URL validation: a value
 * is usable only if it is absolute (`http(s)://`, protocol-relative), rooted
 * (`/...`) or an inline image. Anything else — `""`, `"   "`, `"string"`, a
 * bare filename — counts as absent, so the subrace picture takes over.
 */
export const usableImageSrc = (value?: string | null): string | null => {
  const src = value?.trim();
  if (!src) return null;
  return /^(https?:\/\/|\/\/|\/|data:image\/)/i.test(src) ? src : null;
};
