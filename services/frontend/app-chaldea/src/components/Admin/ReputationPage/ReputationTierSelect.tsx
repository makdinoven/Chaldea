import { useReputationTiers } from './useReputationRefs';

interface ReputationTierSelectProps {
  /** Tier code or null (= no gate). */
  value: string | null;
  onChange: (code: string | null) => void;
  label?: string;
  /** Short explanation under the field. */
  hint?: string;
  disabled?: boolean;
  id?: string;
  /** Extra classes for the `<select>` (defaults to the underline input). */
  selectClassName?: string;
  labelClassName?: string;
}

const DEFAULT_LABEL_CLASS = 'text-white/50 text-xs font-medium uppercase tracking-[0.06em]';

/**
 * FEAT-197 shared gate field «Мин. репутация»: the 8 tiers (names from the live settings), empty = «без ограничения».
 * Used by the quest editor, the NPC form, house plots, bank loans and teleport links.
 */
const ReputationTierSelect = ({
  value,
  onChange,
  label = 'Мин. репутация',
  hint,
  disabled = false,
  id,
  selectClassName = 'input-underline w-full',
  labelClassName = DEFAULT_LABEL_CLASS,
}: ReputationTierSelectProps) => {
  const options = useReputationTiers();
  const known = value == null || options.some((o) => o.code === value);

  return (
    <label className="flex flex-col gap-1 min-w-0" htmlFor={id}>
      {label && <span className={labelClassName}>{label}</span>}
      <select
        id={id}
        value={value ?? ''}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value === '' ? null : e.target.value)}
        className={selectClassName}
      >
        <option value="" className="bg-site-dark text-white">
          Без ограничения
        </option>
        {options.map((o) => (
          <option key={o.code} value={o.code} className="bg-site-dark text-white">
            {o.name}
          </option>
        ))}
        {!known && value && (
          <option value={value} className="bg-site-dark text-white">
            {value}
          </option>
        )}
      </select>
      {hint && <span className="text-white/40 text-xs">{hint}</span>}
    </label>
  );
};

export default ReputationTierSelect;
