import type { ReactNode } from 'react';

interface SectionTitleProps {
  /** Small gold uppercase section label (per the main-page reference). */
  label: string;
  /** Optional right-side slot (e.g. the "Онлайн" pulse indicator). */
  children?: ReactNode;
}

/**
 * Section title row for the main page: small gold uppercase label followed
 * by a gradient rule that fades out to the right.
 */
export default function SectionTitle({ label, children }: SectionTitleProps) {
  return (
    <div className="flex items-center gap-4">
      <h2 className="gold-text whitespace-nowrap text-[13px] font-medium uppercase tracking-[0.2em]">
        {label}
      </h2>
      <span className="h-px flex-1 bg-gradient-to-r from-gold/50 to-transparent" />
      {children}
    </div>
  );
}
