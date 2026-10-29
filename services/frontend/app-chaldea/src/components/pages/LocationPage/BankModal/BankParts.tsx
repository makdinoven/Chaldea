import type { ReactNode } from 'react';
import type { BankActionResult, BankView } from '../../../../types/bank';

/** Runs one bank POST with a fresh `request_id`; toasts the result; `true` on success. */
export type BankRun = (
  call: (requestId: string) => Promise<BankActionResult>,
  fallback: string,
) => Promise<boolean>;

/** Props shared by the three tabs of the bank modal. */
export interface BankTabProps {
  view: BankView;
  characterId: number;
  npcId: number;
  pending: boolean;
  run: BankRun;
}

export const SELECT_CLASS =
  'w-full bg-black/30 border border-white/20 rounded px-2 py-1.5 text-white text-sm ' +
  'focus:border-gold/50 outline-none disabled:opacity-40';

/** Bank section: small uppercase heading + content. */
export const BankSection = ({ title, children }: { title: string; children: ReactNode }) => (
  <section className="flex flex-col gap-3">
    <h3 className="gold-text text-sm sm:text-base font-medium uppercase tracking-wide">{title}</h3>
    {children}
  </section>
);

/** Flat inner card of the bank modal. */
export const BankCard = ({ children, className = '' }: { children: ReactNode; className?: string }) => (
  <div className={`flex flex-col gap-2 bg-white/[0.03] rounded-card p-3 border border-white/5 ${className}`}>
    {children}
  </div>
);

/** «Label: value» line. */
export const BankLine = ({ label, children }: { label: string; children: ReactNode }) => (
  <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 text-xs sm:text-sm">
    <span className="text-white/50">{label}</span>
    <span className="text-white font-medium text-right">{children}</span>
  </div>
);

interface AmountInputProps {
  value: string;
  onChange: (v: string) => void;
  /** «Всё» fills this amount; hidden when not given or 0. */
  allAmount?: number;
  disabled?: boolean;
  label?: string;
}

/** Integer amount field with an optional «Всё» shortcut. */
export const AmountInput = ({ value, onChange, allAmount, disabled, label = 'Сумма' }: AmountInputProps) => (
  <div className="flex items-end gap-2 min-w-0 flex-1">
    <label className="flex flex-col gap-0.5 min-w-0 flex-1">
      <span className="text-white/50 text-[11px] uppercase tracking-wide">{label}</span>
      <input
        type="text"
        inputMode="numeric"
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value.replace(/[^\d]/g, '').slice(0, 10))}
        placeholder="0"
        className="input-underline !text-sm w-full min-w-0"
      />
    </label>
    {allAmount !== undefined && allAmount > 0 && (
      <button
        type="button"
        disabled={disabled}
        onClick={() => onChange(String(allAmount))}
        className="shrink-0 text-[11px] uppercase tracking-wide text-gold/80 hover:text-gold disabled:opacity-40 pb-1"
      >
        Всё
      </button>
    )}
  </div>
);

interface ChoiceProps<T extends string | number> {
  options: { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  disabled?: boolean;
}

/** Segmented choice (deposit kind, term). Wraps on narrow screens. */
export const Choice = <T extends string | number>({ options, value, onChange, disabled }: ChoiceProps<T>) => (
  <div className="flex flex-wrap gap-1.5">
    {options.map((o) => (
      <button
        key={String(o.value)}
        type="button"
        disabled={disabled}
        onClick={() => onChange(o.value)}
        className={`px-2.5 py-1 rounded-card border text-xs transition-colors duration-200 disabled:opacity-40 ${
          o.value === value
            ? 'border-gold/60 bg-gold/10 text-gold'
            : 'border-white/15 text-white/60 hover:border-white/30 hover:text-white'
        }`}
      >
        {o.label}
      </button>
    ))}
  </div>
);

/** Small action button inside cards. */
export const SmallButton = ({
  children,
  onClick,
  disabled,
  variant = 'primary',
}: {
  children: ReactNode;
  onClick: () => void;
  disabled?: boolean;
  variant?: 'primary' | 'line';
}) => (
  <button
    type="button"
    onClick={onClick}
    disabled={disabled}
    className={`px-3 py-1.5 rounded text-xs font-medium uppercase transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed ${
      variant === 'primary'
        ? 'bg-gradient-to-r from-[#2e353e] to-[#537895] text-white hover:shadow-hover'
        : 'border border-white/30 text-white/80 hover:bg-white/10 hover:border-white/50 hover:text-white'
    }`}
  >
    {children}
  </button>
);

/** Red «Должник» mark (site-red = errors / alerts). */
export const DebtorBadge = () => (
  <span className="inline-flex items-center border border-site-red/40 bg-site-red/10 text-site-red rounded-full px-2 py-0.5 text-[10px] sm:text-xs uppercase tracking-wide whitespace-nowrap">
    Должник
  </span>
);
