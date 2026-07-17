// FEAT-151 — shared profile-tab primitive: mini gold section label
// with a fading gold rule (mock's «Задачи / Награда / Рецепты» headers).
import type { ReactNode } from 'react';

interface SectionHeaderProps {
  title: string;
  /** Right-aligned extra content after the rule (e.g. a counter) */
  extra?: ReactNode;
  className?: string;
}

const SectionHeader = ({ title, extra, className = '' }: SectionHeaderProps) => {
  return (
    <div className={`flex items-center gap-2.5 ${className}`}>
      <span className="gold-text text-[11px] font-medium uppercase tracking-[0.14em] shrink-0">
        {title}
      </span>
      <span className="flex-1 h-px bg-gradient-to-r from-gold/40 to-transparent" />
      {extra && <span className="shrink-0">{extra}</span>}
    </div>
  );
};

export default SectionHeader;
