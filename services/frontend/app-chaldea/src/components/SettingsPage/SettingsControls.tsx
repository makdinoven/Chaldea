import type { ReactNode } from 'react';

/* The building blocks every settings tab is made of. */

export interface Option<T extends string> {
  value: T;
  label: string;
}

/** One block of settings on the page, under its own heading. */
export const SettingsCard = ({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children: ReactNode;
}) => (
  <section className="gray-bg p-4 sm:p-5 flex flex-col gap-5 min-w-0">
    <div className="flex flex-col gap-1">
      <h2 className="gold-text text-base sm:text-lg font-medium uppercase tracking-wider">{title}</h2>
      {description && <p className="text-white/50 text-xs">{description}</p>}
    </div>
    {children}
  </section>
);

/** A row of mutually exclusive choices, wrapping on narrow screens. */
export const ChoiceGroup = <T extends string>({
  label,
  hint,
  options,
  value,
  onChange,
  disabled = false,
}: {
  label: string;
  hint?: string;
  options: Option<T>[];
  value: T;
  onChange: (value: T) => void;
  disabled?: boolean;
}) => (
  <fieldset className="min-w-0" disabled={disabled}>
    <legend className="text-white text-sm mb-2">{label}</legend>
    <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={label}>
      {options.map((option) => {
        const active = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(option.value)}
            className={`flex items-center gap-2 px-3 py-2 rounded-card border text-sm transition-colors duration-200 ease-site disabled:opacity-40 disabled:cursor-not-allowed ${
              active
                ? 'bg-site-blue/15 border-site-blue/40 text-white'
                : 'bg-white/[0.04] border-white/10 text-white/70 hover:bg-white/[0.07] hover:text-white'
            }`}
          >
            <span
              className={`w-4 h-4 rounded-full border-2 flex items-center justify-center shrink-0 ${
                active ? 'border-site-blue' : 'border-white/30'
              }`}
            >
              {active && <span className="w-2 h-2 rounded-full bg-site-blue" />}
            </span>
            {option.label}
          </button>
        );
      })}
    </div>
    {hint && <p className="text-white/40 text-xs mt-2">{hint}</p>}
  </fieldset>
);

export const Toggle = ({
  label,
  hint,
  checked,
  onChange,
  disabled = false,
}: {
  label: string;
  hint?: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
}) => (
  <label className={`flex items-start gap-3 ${disabled ? 'opacity-40 cursor-not-allowed' : 'cursor-pointer'}`}>
    <span className="relative mt-0.5 shrink-0">
      <input
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
        className="sr-only peer"
      />
      <span className="block w-10 h-5 rounded-full bg-white/10 peer-checked:bg-site-blue/50 transition-colors" />
      <span className="absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform peer-checked:translate-x-5" />
    </span>
    <span className="flex flex-col">
      <span className="text-white text-sm">{label}</span>
      {hint && <span className="text-white/40 text-xs mt-0.5">{hint}</span>}
    </span>
  </label>
);
