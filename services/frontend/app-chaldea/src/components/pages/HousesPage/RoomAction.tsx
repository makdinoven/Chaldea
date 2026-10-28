import type { ReactNode } from 'react';
import type { LucideIcon } from 'lucide-react';
import { InfoTooltip, WithTooltip } from '../../CommonComponents/InfoTooltip';

/*
  FEAT-180 — one functional button of the room's action bar («Лечь спать»,
  «Попариться», «Читать», a shrine blessing…): an icon, a label and a short
  second line (a factor, a cooldown). The explanation lives in a tooltip:
  hover on desktop, the «i» badge on touch; a disabled button shows its
  reason on hover or tap.
*/

export type RoomActionTone = 'default' | 'active' | 'ready';

interface RoomActionProps {
  icon: LucideIcon;
  label: string;
  /** A short second line: «×2», «через 7 ч», «+3 %». */
  sub?: string | null;
  onClick?: () => void;
  disabled?: boolean;
  /** Why the button is disabled — first line of the tooltip. */
  reason?: string | null;
  /** What the action does — the rest of the tooltip. */
  hint?: ReactNode;
  /** `active` — the character is doing it now (sleeping, reading); `ready` — a gold call to act. */
  tone?: RoomActionTone;
  className?: string;
}

const TONE: Record<RoomActionTone, { box: string; icon: string }> = {
  default: {
    box: 'border-white/[0.12] bg-white/[0.03] hover:border-gold/60 hover:bg-gold/[0.06]',
    icon: 'bg-gold/10 text-gold',
  },
  active: {
    box: 'border-site-blue/50 bg-site-blue/[0.1] hover:border-site-blue hover:bg-site-blue/[0.16]',
    icon: 'bg-site-blue/20 text-site-blue',
  },
  ready: {
    box: 'border-gold/60 bg-gold/[0.08] hover:border-gold hover:bg-gold/[0.14] shadow-[0_0_14px_rgba(240,217,92,0.15)]',
    icon: 'bg-gold/20 text-gold-light',
  },
};

/** The flex row the action buttons sit in (two per row at 360 px, natural width from `sm`). */
export const ACTION_BAR = 'flex flex-wrap gap-2';

/** Tooltip body: the reason (if any) in gold, then the explanation. */
export const TipBody = ({ reason, hint }: { reason?: string | null; hint?: ReactNode }) => {
  if (!reason && !hint) return null;
  return (
    <span className="flex flex-col gap-1.5">
      {reason && <span className="text-gold-light">{reason}</span>}
      {hint && <span>{hint}</span>}
    </span>
  );
};

const RoomAction = ({
  icon: Icon, label, sub, onClick, disabled = false, reason, hint, tone = 'default', className = '',
}: RoomActionProps) => {
  const tip = reason || hint ? <TipBody reason={reason} hint={hint} /> : null;
  return (
    <WithTooltip content={tip} tapToggle={disabled}
      className={`flex flex-1 basis-[136px] sm:flex-none sm:basis-auto min-w-0 ${className}`}>
      <button type="button" onClick={onClick} disabled={disabled}
        className={`w-full sm:w-auto sm:min-w-[170px] min-h-[52px] flex items-center gap-2.5 pl-2 pr-3 py-1.5 rounded-card border text-left transition-colors duration-200 ease-site disabled:opacity-45 disabled:pointer-events-none ${TONE[tone].box}`}>
        <span className={`w-9 h-9 rounded-full flex items-center justify-center shrink-0 ${TONE[tone].icon}`}>
          <Icon size={17} />
        </span>
        <span className="flex flex-col min-w-0 pr-3">
          <span className="text-white text-[12px] sm:text-[13px] font-medium uppercase tracking-[0.04em] leading-tight break-words">{label}</span>
          {sub && <span className="text-white/55 text-[11px] leading-tight mt-0.5 break-words">{sub}</span>}
        </span>
      </button>
      {/* Touch screens have no hover — an «i» opens the explanation of an enabled button. */}
      {!disabled && tip && (
        <InfoTooltip content={tip} label={`Подробнее: ${label}`} size={12}
          className="absolute top-1 right-1 hidden [@media(hover:none)]:inline-flex" />
      )}
    </WithTooltip>
  );
};

export default RoomAction;
