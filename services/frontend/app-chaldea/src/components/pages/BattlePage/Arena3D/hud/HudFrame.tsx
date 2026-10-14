import type { ReactNode } from "react";

const CORNER = "pointer-events-none absolute h-2.5 w-2.5 border-gold/60";

interface HudFrameProps {
  children: ReactNode;
  className?: string;
  /** Classes for the content wrapper, e.g. to continue a flex/height chain into the panel. */
  innerClassName?: string;
}

/** Dark tooled-leather panel with gilded corners — the shared skin of the 3D battle HUD. */
const HudFrame = ({ children, className = "", innerClassName = "" }: HudFrameProps) => (
  <div
    className={`relative rounded-card border border-gold-dark/35 bg-[linear-gradient(180deg,rgba(34,26,19,0.9)_0%,rgba(12,11,10,0.92)_100%)] shadow-[0_10px_30px_rgba(0,0,0,0.55),inset_0_1px_0_rgba(240,217,92,0.14)] ${className}`}
  >
    <div className="pointer-events-none absolute inset-0 rounded-card bg-[url('/textures/dark-leather.png')] bg-repeat opacity-[0.14] mix-blend-overlay" />
    <span className={`${CORNER} left-1.5 top-1.5 border-l border-t`} />
    <span className={`${CORNER} right-1.5 top-1.5 border-r border-t`} />
    <span className={`${CORNER} bottom-1.5 left-1.5 border-b border-l`} />
    <span className={`${CORNER} bottom-1.5 right-1.5 border-b border-r`} />
    <div className={`relative ${innerClassName}`}>{children}</div>
  </div>
);

export default HudFrame;
