/**
 * FEAT-209/210 — «Готовность: все / Готовые / Не готовые» select.
 * Pair with `useReadyFilterUrlState()` (`value={ready}`, `onChange={(v) => { setReady(v); setPage(1); }}`).
 */
interface ReadyFilterSelectProps {
  value: boolean | null;
  onChange: (value: boolean | null) => void;
  /** Width classes (default `sm:max-w-[200px]`) */
  className?: string;
}

const OPTION_CLASS = 'bg-site-dark text-white';

const ReadyFilterSelect = ({ value, onChange, className = 'sm:max-w-[200px]' }: ReadyFilterSelectProps) => (
  <select
    className={`input-underline ${className}`}
    aria-label="Готовность"
    value={value === null ? '' : value ? '1' : '0'}
    onChange={(e) => onChange(e.target.value === '' ? null : e.target.value === '1')}
  >
    <option value="" className={OPTION_CLASS}>Готовность: все</option>
    <option value="1" className={OPTION_CLASS}>Готовые</option>
    <option value="0" className={OPTION_CLASS}>Не готовые</option>
  </select>
);

export default ReadyFilterSelect;
