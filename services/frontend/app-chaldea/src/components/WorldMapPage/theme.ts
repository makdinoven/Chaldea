import type { MarkerType } from '../../api/worldGraph';

export type ColorMode = 'marker' | 'country' | 'component' | 'level';

export const COLOR_MODE_LABELS: Record<ColorMode, string> = {
  marker: 'Тип локации',
  country: 'Страна',
  component: 'Связность',
  level: 'Уровень',
};

export const MARKER_COLORS: Record<MarkerType, string> = {
  safe: '#5fb98f',
  dangerous: '#f37753',
  dungeon: '#a78bfa',
  farm: '#f0d95c',
};

export const MARKER_LABELS: Record<MarkerType, string> = {
  safe: 'Безопасная',
  dangerous: 'Опасная',
  dungeon: 'Подземелье',
  farm: 'Фарм',
};

/** Distinct hues for countries; wraps if more countries are ever added. */
export const COUNTRY_COLORS = [
  '#76a6bd', '#f0d95c', '#5fb98f', '#f37753', '#a78bfa', '#e879a6',
  '#63b3ed', '#d9a86c',
];

/**
 * Palette for connected components. Index 0..n follows component size rank, so
 * the largest landmasses always get the most legible colours. Isolated
 * locations are deliberately muted grey — they are dead ends, not content.
 */
export const COMPONENT_COLORS = [
  '#f0d95c', '#76a6bd', '#5fb98f', '#f37753', '#a78bfa', '#e879a6',
  '#63b3ed', '#d9a86c', '#7dd3fc', '#fbbf24', '#34d399', '#fb7185',
];

export const ISOLATED_COLOR = '#4b5563';

export const ROUTE_COLOR = '#f0d95c';
export const ROUTE_ENDPOINT_COLOR = '#ffffff';

/** Green -> amber -> red ramp over recommended level. */
export const levelColor = (level: number, maxLevel: number): string => {
  if (maxLevel <= 0) return '#5fb98f';
  const t = Math.min(Math.max(level / maxLevel, 0), 1);
  const hue = 145 - t * 145; // 145deg green -> 0deg red
  return `hsl(${hue.toFixed(0)}, 62%, 58%)`;
};
