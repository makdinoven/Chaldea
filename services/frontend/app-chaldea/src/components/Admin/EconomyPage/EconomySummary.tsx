import { useState } from 'react';
import { CheckCircle2, ChevronDown, ChevronRight, RefreshCw, TriangleAlert } from 'lucide-react';
import { useCurrency } from '../../../hooks/useCurrency';
import type { EconCountryTreasury, EconSummary } from '../../../types/economy';
import { accountKindLabel } from './economyLabels';
import { BigMoney, useBigMoney } from './CompactValue';
import { COMPACT_MONEY_FROM } from '../../../utils/compactNumber';

interface EconomySummaryProps {
  summary: EconSummary;
  refreshing: boolean;
  onRefresh: () => void;
}

const balanceClass = (n: number) => (n < 0 ? 'text-site-red' : 'text-white');

const StatCard = ({ label, value, title, accent = false }: { label: string; value: string; title?: string; accent?: boolean }) => (
  <div className="bg-site-bg rounded-card border border-white/[0.07] p-3 sm:p-4 flex flex-col gap-1 min-w-0">
    <span className="text-white/50 text-[11px] sm:text-xs uppercase tracking-[0.06em]">{label}</span>
    <span className={`text-sm sm:text-base font-medium break-words ${accent ? 'text-gold' : 'text-white'}`} title={title}>
      {value}
    </span>
  </div>
);

const CountryRow = ({ country }: { country: EconCountryTreasury }) => {
  const { big, exact } = useBigMoney();
  const [open, setOpen] = useState(false);
  const regionsSum = country.regions.reduce((s, r) => s + r.balance, 0);
  const pursesSum = country.regions.reduce((s, r) => s + (r.purse_balance ?? 0), 0);
  const hasPurses = country.regions.some((r) => r.purse_account_id != null);
  const noCountry = country.account_id === null;

  return (
    <li className="border-b border-white/[0.07] last:border-b-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="w-full flex items-center gap-2 py-3 text-left hover:text-site-blue transition-colors duration-200 ease-site"
      >
        {open ? <ChevronDown size={16} className="text-gold shrink-0" /> : <ChevronRight size={16} className="text-gold shrink-0" />}
        <span className="flex-1 min-w-0">
          <span className="text-white text-sm font-medium break-words">
            {noCountry ? 'Без страны' : country.name ?? `Страна #${country.country_id}`}
          </span>
          {!country.is_active && !noCountry && <span className="ml-2 text-white/40 text-xs">закрыта</span>}
          <span className="block text-white/40 text-xs">
            Регионов: {country.regions.length} · в казнах регионов{' '}
            <span title={exact(regionsSum)}>{big(regionsSum)}</span>
            {hasPurses && (
              <>
                {' · у жителей '}
                <span title={exact(pursesSum)}>{big(pursesSum)}</span>
              </>
            )}
          </span>
        </span>
        {!noCountry && (
          <BigMoney value={country.balance} className={`text-sm shrink-0 text-right ${balanceClass(country.balance)}`} />
        )}
      </button>
      {open && (
        <ul className="pl-6 pb-3 flex flex-col gap-1.5">
          {country.regions.length === 0 && <li className="text-white/40 text-xs italic">Регионов нет</li>}
          {country.regions.map((r) => (
            <li key={r.account_id} className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 text-sm">
              <span className="flex-1 min-w-[50%] text-white/80 break-words">
                {r.name ?? `Регион #${r.region_id}`}
                {!r.is_active && <span className="ml-2 text-white/40 text-xs">закрыта</span>}
              </span>
              {r.purse_account_id != null && (
                <span className="shrink-0 text-white/50 text-xs" title={`Кошелёк жителей: ${exact(r.purse_balance ?? 0)}`}>
                  жители {big(r.purse_balance ?? 0)}
                </span>
              )}
              <span className={`shrink-0 ${balanceClass(r.balance)}`} title={`Казна региона: ${exact(r.balance)}`}>
                {big(r.balance)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </li>
  );
};

/** «Где деньги мира»: totals, the conservation check and the treasury tree. */
const EconomySummary = ({ summary, refreshing, onRefresh }: EconomySummaryProps) => {
  const { format, forms } = useCurrency();
  const { big } = useBigMoney();
  const { totals, invariant } = summary;

  const cards: { label: string; value: number; accent?: boolean }[] = [
    { label: 'Выпущено', value: totals.issued, accent: true },
    { label: 'На руках (всего)', value: totals.held, accent: true },
    { label: 'Игроки', value: totals.players },
    { label: 'НПС', value: totals.npcs },
    { label: 'Ставки аукциона', value: totals.escrow },
    { label: 'Хранилище аукциона', value: totals.auction_storage },
    { label: 'Казны регионов', value: totals.region_treasuries },
    { label: 'Кошельки жителей', value: totals.population_purses ?? 0 },
    { label: 'Казны стран', value: totals.country_treasuries },
    { label: 'Казна Скитальцев', value: totals.world_treasury },
  ];
  // FEAT-184: shown once the backend reports banks (older responses have no such fields).
  if (totals.banks !== undefined) cards.push({ label: 'Банки (свои средства)', value: totals.banks });
  if (totals.bank_deposits !== undefined) cards.push({ label: 'Вклады игроков', value: totals.bank_deposits });

  const hasBankCheck = invariant.bank_deposits_expected !== undefined && invariant.bank_deposits_actual !== undefined;
  const bankVaultOk = !hasBankCheck || invariant.bank_deposits_expected === invariant.bank_deposits_actual;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        {invariant.ok ? (
          <span className="inline-flex items-center gap-2 self-start rounded-full border border-stat-energy/40 bg-stat-energy/10 px-3 py-1.5 text-stat-energy text-sm font-medium">
            <CheckCircle2 size={16} />
            Сходится
          </span>
        ) : (
          <span className="inline-flex items-center gap-2 self-start rounded-full border border-site-red/50 bg-site-red/10 px-3 py-1.5 text-site-red text-sm font-medium">
            <TriangleAlert size={16} />
            Расхождение
          </span>
        )}
        <span className="text-white/50 text-sm">
          Налог регионов в казну страны: {Math.round(summary.settings.country_tax_rate * 1000) / 10}%
        </span>
        {hasBankCheck && (
          <span
            className={`text-sm ${bankVaultOk ? 'text-white/50' : 'text-site-red'}`}
            title="Сумма открытых вкладов игроков должна совпадать с деньгами в хранилищах банков"
          >
            Вклады = хранилище: {bankVaultOk ? 'сходится' : 'расхождение'}
          </span>
        )}
        <button
          type="button"
          onClick={onRefresh}
          disabled={refreshing}
          className="sm:ml-auto self-start inline-flex items-center gap-1.5 text-sm text-white/60 hover:text-site-blue transition-colors duration-200 ease-site disabled:opacity-40"
        >
          <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
          Обновить
        </button>
      </div>

      {!invariant.ok && (
        <div className="rounded-card border border-site-red/40 bg-site-red/[0.06] p-4 flex flex-col gap-2 text-sm">
          <p className="text-white">
            Сумма всех счетов мира: <span className={invariant.ledger_sum !== 0 ? 'text-site-red' : 'text-white'}>{format(invariant.ledger_sum)}</span>{' '}
            <span className="text-white/50">(должна быть 0)</span>
          </p>
          <p className="text-white">
            Ставки аукциона: счёт {format(invariant.escrow_actual)}, по лотам {format(invariant.escrow_expected)}
          </p>
          <p className="text-white">
            Хранилище аукциона: счёт {format(invariant.storage_actual)}, по записям {format(invariant.storage_expected)}
          </p>
          {hasBankCheck && (
            <p className={bankVaultOk ? 'text-white' : 'text-site-red'}>
              Вклады игроков: хранилища банков {format(invariant.bank_deposits_actual ?? 0)}, по вкладам{' '}
              {format(invariant.bank_deposits_expected ?? 0)}
            </p>
          )}
          {invariant.drifting_characters.length > 0 && (
            <div className="flex flex-col gap-1">
              <p className="text-white/60">Баланс персонажа не совпадает с журналом:</p>
              <ul className="flex flex-col gap-1 max-h-60 overflow-y-auto gold-scrollbar">
                {invariant.drifting_characters.map((c) => (
                  <li key={c.character_id} className="flex flex-wrap gap-x-3 text-white/80">
                    <span className="text-white">{c.name ?? `#${c.character_id}`}</span>
                    <span>баланс {format(c.balance)}</span>
                    <span>по журналу {format(c.ledger)}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {cards.map((c) => (
          <StatCard
            key={c.label}
            label={c.label}
            value={big(c.value)}
            title={Math.abs(c.value) >= COMPACT_MONEY_FROM ? format(c.value) : undefined}
            accent={c.accent}
          />
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <section className="lg:col-span-2 bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-5 flex flex-col gap-2 min-w-0">
          <h2 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Страны и регионы</h2>
          {summary.countries.length === 0 ? (
            <p className="text-white/40 text-sm italic">Казн пока нет.</p>
          ) : (
            <ul className="flex flex-col">
              {summary.countries.map((c) => (
                <CountryRow key={c.account_id ?? `none-${c.country_id ?? 'x'}`} country={c} />
              ))}
            </ul>
          )}
        </section>

        <section className="self-start w-full bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-5 flex flex-col gap-2 min-w-0">
          <h2 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Системные счета</h2>
          <ul className="flex flex-col gap-2">
            {summary.system_accounts.map((a) => (
              <li key={a.account_id} className="flex items-baseline gap-2 text-sm">
                <span className="flex-1 min-w-0 text-white/80 break-words">{a.name ?? accountKindLabel(a.kind)}</span>
                <BigMoney value={a.balance} className={`shrink-0 ${balanceClass(a.balance)}`} />
              </li>
            ))}
          </ul>
          <p className="text-white/40 text-xs mt-2">
            Счёт «Эмиссия» уходит в минус ровно на столько {forms.genitive}, сколько выпущено в мир; «Корректировки» —
            разница ручных списаний и начислений.
          </p>
        </section>
      </div>
    </div>
  );
};

export default EconomySummary;
