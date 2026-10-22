import type { CSSProperties } from 'react';
import type { ProfileStyleSettings } from '../../redux/slices/userProfileSlice';

/** Build combined text-shadow for nickname glow + text shadow effects. */
export const buildNicknameTextShadow = (
  nicknameColor: string | null | undefined,
  glow: number,
  textShadowDepth: number,
  extraShadow?: string,
): string | undefined => {
  const parts: string[] = [];
  if (glow > 0 && nicknameColor) {
    parts.push(`0 0 ${glow}px ${nicknameColor}`);
  }
  if (textShadowDepth > 0) {
    parts.push(`2px 2px ${textShadowDepth}px rgba(0,0,0,0.8)`);
  }
  if (extraShadow) {
    parts.push(extraShadow);
  }
  return parts.length > 0 ? parts.join(', ') : undefined;
};

/** Default values for slider-based style settings */
export const SLIDER_DEFAULTS: Record<string, number> = {
  post_color_opacity: 1,
  post_color_blur: 0,
  post_color_glow: 0,
  post_color_saturation: 1,
  bg_color_opacity: 1,
  bg_color_blur: 0,
  bg_color_glow: 0,
  bg_color_saturation: 1,
};

/** Convert a hex color string to an rgba() string with the given alpha. */
export const hexToRgba = (hex: string, alpha: number): string => {
  const cleaned = hex.replace('#', '');
  const r = parseInt(cleaned.substring(0, 2), 16);
  const g = parseInt(cleaned.substring(2, 4), 16);
  const b = parseInt(cleaned.substring(4, 6), 16);
  if (isNaN(r) || isNaN(g) || isNaN(b)) return hex;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
};

/** Build inline CSS style from slider values for a given color section.
 *  Uses rgba() for opacity instead of CSS opacity (which would affect children).
 *  Does NOT apply filter:saturate() on containers (it would affect children too).
 */
export const buildColorEffectStyle = (
  color: string,
  prefix: 'post_color' | 'bg_color',
  ss: ProfileStyleSettings | null | undefined,
): CSSProperties => {
  const settings = ss ?? {};
  const opacity = (settings[`${prefix}_opacity` as keyof ProfileStyleSettings] as number | undefined) ?? SLIDER_DEFAULTS[`${prefix}_opacity`];
  const blur = (settings[`${prefix}_blur` as keyof ProfileStyleSettings] as number | undefined) ?? SLIDER_DEFAULTS[`${prefix}_blur`];
  const glow = (settings[`${prefix}_glow` as keyof ProfileStyleSettings] as number | undefined) ?? SLIDER_DEFAULTS[`${prefix}_glow`];

  const style: CSSProperties = {};
  if (color) {
    style.backgroundColor = opacity !== 1 ? hexToRgba(color, opacity) : color;
  }
  if (blur > 0) {
    style.backdropFilter = `blur(${blur}px)`;
    style.WebkitBackdropFilter = `blur(${blur}px)`;
  }
  if (glow > 0 && color) {
    style.boxShadow = `0 0 ${glow}px ${color}`;
  }
  return style;
};
