import { useEffect, useState } from 'react';
import { X } from 'lucide-react';
import { fetchEconomyAccounts } from '../../../api/economyAdmin';
import { apiErrorMessage } from '../../../api/errors';
import useDebounce from '../../../hooks/useDebounce';
import { useCurrency } from '../../../hooks/useCurrency';
import type { EconAccount, EconAccountKind } from '../../../types/economy';
import { accountKindLabel } from './economyLabels';

const RESULTS_PAGE_SIZE = 20;
const SEARCH_DEBOUNCE_MS = 300;

interface AccountPickerProps {
  /** Account kinds offered as chips; with `allowAnyKind` a «Все» chip searches every kind. */
  kinds: EconAccountKind[];
  allowAnyKind?: boolean;
  value: EconAccount | null;
  onChange: (account: EconAccount | null) => void;
  /** Closed accounts can be picked (journal filter) or not (money actions). */
  allowInactive?: boolean;
  label: string;
  inputId: string;
}

/** Search-and-pick an economy account via `/admin/economy/accounts`. */
const AccountPicker = ({
  kinds,
  allowAnyKind = false,
  value,
  onChange,
  allowInactive = false,
  label,
  inputId,
}: AccountPickerProps) => {
  const { format } = useCurrency();
  const [kind, setKind] = useState<EconAccountKind | ''>(allowAnyKind ? '' : kinds[0]);
  const [query, setQuery] = useState('');
  const debouncedQuery = useDebounce(query, SEARCH_DEBOUNCE_MS) as string;
  const [results, setResults] = useState<EconAccount[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchEconomyAccounts({
      kind: kind || undefined,
      q: debouncedQuery.trim() || undefined,
      page: 1,
      page_size: RESULTS_PAGE_SIZE,
    })
      .then((page) => {
        if (!cancelled) setResults(page.items);
      })
      .catch((e) => {
        if (cancelled) return;
        setResults([]);
        setError(apiErrorMessage(e, 'Не удалось загрузить список счетов'));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, kind, debouncedQuery]);

  const pick = (account: EconAccount) => {
    if (!account.is_active && !allowInactive) return;
    onChange(account);
    setOpen(false);
    setQuery('');
  };

  const chips: (EconAccountKind | '')[] = allowAnyKind ? ['', ...kinds] : kinds;

  return (
    <div className="flex flex-col gap-2 min-w-0">
      <label htmlFor={inputId} className="text-white/60 text-xs uppercase tracking-[0.06em]">
        {label}
      </label>

      {value ? (
        <div className="flex items-center gap-2 min-w-0">
          <p className="text-white text-sm min-w-0 break-words">
            <span className="text-gold font-medium">{value.name ?? `#${value.account_id}`}</span>{' '}
            <span className="text-white/50">
              · {accountKindLabel(value.kind)} · {format(value.balance)}
            </span>
          </p>
          <button
            type="button"
            onClick={() => onChange(null)}
            className="shrink-0 text-white/50 hover:text-site-blue transition-colors duration-200 ease-site"
            aria-label="Сбросить выбор счёта"
          >
            <X size={16} />
          </button>
        </div>
      ) : (
        <>
          {chips.length > 1 && (
            <div className="flex flex-wrap gap-2">
              {chips.map((k) => (
                <button
                  key={k || 'any'}
                  type="button"
                  onClick={() => {
                    setKind(k);
                    setOpen(true);
                  }}
                  className={`chip-outline rounded-full px-3 py-1.5 text-xs font-medium ${
                    kind === k ? 'chip-outline-active' : ''
                  }`}
                >
                  {k ? accountKindLabel(k) : 'Все'}
                </button>
              ))}
            </div>
          )}
          <input
            id={inputId}
            type="text"
            className="input-underline w-full"
            placeholder="Название счёта или имя персонажа..."
            value={query}
            maxLength={100}
            onFocus={() => setOpen(true)}
            onChange={(e) => {
              setQuery(e.target.value);
              setOpen(true);
            }}
          />
          {open && (
            <div className="dropdown-menu w-full max-h-60 overflow-y-auto gold-scrollbar">
              {loading && <p className="px-4 py-2 text-white/50 text-sm">Поиск...</p>}
              {!loading && error && <p className="px-4 py-2 text-site-red text-sm">{error}</p>}
              {!loading && !error && results.length === 0 && (
                <p className="px-4 py-2 text-white/40 text-sm">Счета не найдены</p>
              )}
              {!loading &&
                !error &&
                results.map((acc) => {
                  const disabled = !acc.is_active && !allowInactive;
                  return (
                    <button
                      key={acc.account_id}
                      type="button"
                      disabled={disabled}
                      onClick={() => pick(acc)}
                      className="dropdown-item w-full text-left flex flex-wrap items-baseline gap-x-2 disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      <span className="text-white break-words">{acc.name ?? `#${acc.account_id}`}</span>
                      <span className="text-white/40 text-xs">
                        {accountKindLabel(acc.kind)}
                        {!acc.is_active && ' · закрыт'}
                      </span>
                      <span className={`ml-auto text-xs ${acc.balance < 0 ? 'text-site-red' : 'text-white/60'}`}>
                        {format(acc.balance)}
                      </span>
                    </button>
                  );
                })}
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default AccountPicker;
