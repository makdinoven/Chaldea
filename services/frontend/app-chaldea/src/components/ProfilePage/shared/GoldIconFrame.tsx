// FEAT-166 — shared profile-tab primitive: gold-gradient ring around an icon,
// avatar or item image (skills, gathering, professions, recipes, party, quests).
import type { ReactNode } from 'react';

interface GoldIconFrameProps {
  /** Outer size in px (ring included) */
  size: number;
  shape?: 'circle' | 'square';
  /** Soft gold glow (identity bands / avatars) */
  glow?: boolean;
  /** Image URL; when empty, `fallback` (or `children`) is rendered instead */
  src?: string | null;
  alt?: string;
  fallback?: ReactNode;
  className?: string;
  children?: ReactNode;
}

const GLOW_CLASS = 'shadow-[0_0_14px_rgba(240,217,92,0.35)]';

const GoldIconFrame = ({
  size,
  shape = 'square',
  glow = false,
  src,
  alt = '',
  fallback,
  className = '',
  children,
}: GoldIconFrameProps) => {
  const outerRadius = shape === 'circle' ? 'rounded-full' : 'rounded-[10px]';
  const innerRadius = shape === 'circle' ? 'rounded-full' : 'rounded-[8px]';

  return (
    <div
      className={`p-[2px] bg-gradient-to-b from-gold-light to-gold-dark shrink-0 ${outerRadius} ${
        glow ? GLOW_CLASS : ''
      } ${className}`}
      style={{ width: size, height: size }}
    >
      <div
        className={`w-full h-full bg-site-dark flex items-center justify-center overflow-hidden ${innerRadius}`}
      >
        {src ? (
          <img src={src} alt={alt} className="w-full h-full object-cover" />
        ) : (
          fallback ?? children
        )}
      </div>
    </div>
  );
};

export default GoldIconFrame;
