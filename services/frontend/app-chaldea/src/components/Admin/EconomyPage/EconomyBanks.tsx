import { Fragment, useCallback, useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { ChevronDown, ChevronRight, RefreshCw } from 'lucide-react';
import {
  fetchEconomyBank,
  fetchEconomyBankDebtors,
  fetchEconomyBanks,
  fetchEconomyRegions,
  postEconomyBankCapital,
  postEconomyBankLoanWriteOff,
  putEconomyBankFlag,
} from '../../../api/economyAdmin';
import { apiErrorMessage } from '../../../api/errors';
import { useCurrency } from '../../../hooks/useCurrency';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import ConfirmDialog from '../../pages/LocationPage/ConfirmDialog';
import type {
  EconBankAdminDeposit,
  EconBankAdminDetail,
  EconBankAdminItem,
  EconBankAdminLoan,
  EconBankCapitalDirection,
  EconBankDebtor,
  EconBankStats,
  EconBanksResponse,
  EconRegionItem,
} from '../../../types/economy';
import { formatDateTime, formatDecimal, formatPercent } from './economyLabels';
import { BigMoney, useBigMoney } from './CompactValue';
import { COMPACT_MONEY_FROM } from '../../../utils/compactNumber';

const COMMENT_MIN = 3;
const COMMENT_MAX = 500;
const AMOUNT_MAX = 1_000_000_000;
const DAYS_IN_WEEK = 7;

type Format = (n: number, short?: boolean) => string;

type BankFilter = 'all' | 'enabled' | 'disabled' | 'overdue' | 'problems';

const BANK_FILTER_LABEL: Record<BankFilter, string> = {
  all: 'Все банки',
  enabled: 'Работают',
  disabled: 'Закрыты',
  overdue: 'Есть должники',
  problems: 'Требуют внимания',
};

/** Counters of the last bank pass (3.6 stats); unknown keys are shown by their code. */
const STAT_LABELS: Record<string, string> = {
  interest_paid: 'проценты по вкладам игроков',
  interest_skipped: 'не выплачено (банку не хватило)',
  resident_interest_paid: 'проценты по вкладам жителей',
  loan_interest: 'проценты по займам игроков',
  penalties: 'пени',
  resident_loan_interest: 'проценты по займам жителей',
  resident_in: 'жители положили',
  resident_out: 'жители сняли',
  resident_issued: 'выдано жителям в займ',
  resident_repaid: 'жители вернули',
  matured: 'срочных вкладов завершено',
  merged: 'объединено со вкладом до востребования',
};

/** Stats that count deposits, not money. */
const STAT_COUNTS = new Set(['matured', 'merged']);

const regionTitle = (b: { region_id: number; region_name: string | null }) =>
  b.region_name ?? `Удалённый регион #${b.region_id}`;

const bankersCount = (b: EconBankAdminItem): number =>
  Array.isArray(b.bankers) ? b.bankers.length : Number(b.bankers) || 0;

const bankerNames = (b: EconBankAdminItem): string | null =>
  Array.isArray(b.bankers) && b.bankers.length > 0
    ? b.bankers.map((n) => n.name ?? `НПС #${n.npc_id}`).join(', ')
    : null;

const needsAttention = (b: EconBankAdminItem) => !b.vault_ok || (b.enabled && bankersCount(b) === 0);

/** «0,1 % в день · 0,7 % в неделю» for a demand rate. */
const demandRateText = (rateDay: number) =>
  `${formatPercent(rateDay, 2)} в день · ${formatPercent(rateDay * DAYS_IN_WEEK, 2)} в неделю`;

/** «1,4 % за 7 дн.» for a term rate. */
const termRateText = (rateDay: number, termDays: number) =>
  `${formatPercent(rateDay * termDays, 2)} за ${termDays} дн.`;

const depositKindText = (d: EconBankAdminDeposit) =>
  d.kind === 'term' ? `срочный ${d.term_days ?? '?'} дн.` : 'до востребования';

/* ------------------------------------------------------------------ small pieces */

interface SwitchProps {
  checked: boolean;
  disabled: boolean;
  onChange: (next: boolean) => void;
  label: string;
}

const Switch = ({ checked, disabled, onChange, label }: SwitchProps) => (
  <button
    type="button"
    role="switch"
    aria-checked={checked}
    aria-label={label}
    title={label}
    disabled={disabled}
    onClick={(e) => {
      e.stopPropagation();
      onChange(!checked);
    }}
    className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full border transition-colors duration-200 ease-site disabled:opacity-40 disabled:cursor-not-allowed ${
      checked ? 'bg-gold/30 border-gold/60' : 'bg-white/[0.06] border-white/20'
    }`}
  >
    <span
      className={`inline-block h-4 w-4 rounded-full transition-transform duration-200 ease-site ${
        checked ? 'translate-x-6 bg-gold' : 'translate-x-1 bg-white/50'
      }`}
    />
  </button>
);

const Badge = ({ tone, children }: { tone: 'red' | 'gold' | 'green' | 'gray'; children: string }) => {
  const cls = {
    red: 'border-site-red/50 bg-site-red/10 text-site-red',
    gold: 'border-gold/50 bg-gold/10 text-gold',
    green: 'border-stat-energy/40 bg-stat-energy/10 text-stat-energy',
    gray: 'border-white/20 bg-white/[0.04] text-white/60',
  }[tone];
  return (
    <span className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] whitespace-nowrap ${cls}`}>{children}</span>
  );
};

/** Region name, flag state and warnings. */
const BankTitle = ({ b }: { b: EconBankAdminItem }) => {
  const bankers = bankersCount(b);
  const names = bankerNames(b);
  return (
    <span className="flex flex-col gap-1 min-w-0">
      <span className="text-white break-words">{regionTitle(b)}</span>
      {b.country_name && <span className="text-white/40 text-xs break-words">{b.country_name}</span>}
      <span className="flex flex-wrap gap-1">
        {b.enabled ? <Badge tone="green">банк есть</Badge> : <Badge tone="gray">банк закрыт</Badge>}
        {!b.simulated && <Badge tone="gray">без симуляции</Badge>}
        {b.enabled && bankers === 0 && <Badge tone="gold">нет банкира</Badge>}
        {!b.vault_ok && <Badge tone="red">расхождение</Badge>}
      </span>
      {bankers > 0 && (
        <span className="text-white/40 text-xs break-words" title={names ?? undefined}>
          банкиров: {bankers}
          {names && ` (${names})`}
        </span>
      )}
    </span>
  );
};

const Funds = ({ b }: { b: EconBankAdminItem }) => (
  <span className="flex flex-col gap-0.5 text-xs">
    <span className="text-white/80 text-sm whitespace-nowrap"><BigMoney value={b.own_funds} short /></span>
    <span className="text-white/40 whitespace-nowrap">резерв <BigMoney value={b.reserve} short /></span>
    <span className="text-white/40 whitespace-nowrap">можно выдать <BigMoney value={b.lendable} short /></span>
  </span>
);

const Vault = ({ b }: { b: EconBankAdminItem }) => (
  <span className="flex flex-col gap-0.5 text-xs">
    <span className={`text-sm whitespace-nowrap ${b.vault_ok ? 'text-white/80' : 'text-site-red'}`}>
      <BigMoney value={b.vault} short />
    </span>
    {!b.vault_ok && (
      <span className="text-site-red whitespace-nowrap">по вкладам <BigMoney value={b.deposits_sum} short /></span>
    )}
    <span className="text-white/40 whitespace-nowrap">
      вкладов {b.deposits_count}
      {b.term_count > 0 && `, срочных ${b.term_count}`}
    </span>
  </span>
);

const Residents = ({ b }: { b: EconBankAdminItem }) => (
  <span className="flex flex-col gap-0.5 text-xs">
    <span className="text-white/60 whitespace-nowrap">
      вклады <span className="text-white/80"><BigMoney value={b.resident_deposits} short /></span>
    </span>
    <span className="text-white/60 whitespace-nowrap">
      займы <span className="text-white/80"><BigMoney value={b.resident_loans} short /></span>
    </span>
  </span>
);

const Loans = ({ b }: { b: EconBankAdminItem }) => (
  <span className="flex flex-col gap-0.5 text-xs">
    <span className="text-white/80 text-sm whitespace-nowrap"><BigMoney value={b.loans_debt} short /></span>
    <span className="text-white/40 whitespace-nowrap">займов {b.loans_count}</span>
    {b.overdue_count > 0 && <span className="text-site-red whitespace-nowrap">просрочено {b.overdue_count}</span>}
  </span>
);

const Rates = ({ b }: { b: EconBankAdminItem }) => (
  <span className="flex flex-col gap-0.5 text-xs text-white/60">
    <span className="whitespace-nowrap">
      коэффициент <span className="text-white/80">×{formatDecimal(b.rate_factor, 3)}</span>
    </span>
    <span className="break-words">до востребования: {demandRateText(b.demand_rate_day)}</span>
    {b.term_rates.map((t) => (
      <span key={t.term_days} className="break-words">
        срочный: {termRateText(t.rate_day, t.term_days)}
      </span>
    ))}
  </span>
);

const LastPass = ({ b }: { b: EconBankAdminItem }) => {
  const entries = Object.entries((b.last_stats ?? {}) as EconBankStats).filter(
    ([, v]) => typeof v === 'number' && v !== 0,
  ) as [string, number][];
  return (
    <span className="flex flex-col gap-0.5 text-xs text-white/60">
      <span className="text-white/40">{b.last_tick_at ? formatDateTime(b.last_tick_at) : 'ещё не пересчитывался'}</span>
      {entries.map(([key, value]) => (
        <span key={key} className="break-words">
          {STAT_LABELS[key] ?? key}:{' '}
          <span className="text-white/80">{STAT_COUNTS.has(key) ? value : <BigMoney value={value} short />}</span>
        </span>
      ))}
      {b.last_tick_at && entries.length === 0 && <span className="text-white/30">движений не было</span>}
    </span>
  );
};

/* ------------------------------------------------------------------ detail: deposits and loans */

const DepositsList = ({ deposits, format }: { deposits: EconBankAdminDeposit[]; format: Format }) => {
  if (deposits.length === 0) return <p className="text-white/40 text-xs italic">Открытых вкладов нет.</p>;
  return (
    <ul className="flex flex-col divide-y divide-white/[0.07]">
      <li className="hidden md:grid grid-cols-[minmax(0,2fr)_minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.4fr)] gap-3 pb-1.5 text-white/40 text-[11px] uppercase tracking-[0.06em]">
        <span>Персонаж</span>
        <span>Вид</span>
        <span>Сумма</span>
        <span>Проценты</span>
        <span>Ставка</span>
        <span>Открыт / срок</span>
      </li>
      {deposits.map((d) => (
        <li
          key={d.id}
          className="py-2 grid grid-cols-2 md:grid-cols-[minmax(0,2fr)_minmax(0,1.3fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.4fr)] gap-x-3 gap-y-1 text-xs"
        >
          <span className="col-span-2 md:col-span-1 min-w-0">
            <span className="text-white break-words">{d.character_name ?? `Персонаж #${d.character_id}`}</span>
            <span className="text-white/30"> #{d.character_id}</span>
          </span>
          <span className="flex flex-wrap items-center gap-1 text-white/60">
            {depositKindText(d)}
            {d.matured && <Badge tone="green">срок вышел</Badge>}
          </span>
          <span className="text-white/80 whitespace-nowrap">
            <span className="md:hidden text-white/40">Сумма: </span>
            {format(d.amount, true)}
          </span>
          <span className="text-white/60 whitespace-nowrap">
            <span className="md:hidden text-white/40">Проценты: </span>
            {d.kind === 'term' ? format(d.interest_accrued, true) : format(d.interest_total, true)}
            {d.kind === 'term' && d.interest_total !== d.interest_accrued && (
              <span className="text-white/40"> (всего {format(d.interest_total, true)})</span>
            )}
          </span>
          <span className="text-white/60 break-words">
            <span className="md:hidden text-white/40">Ставка: </span>
            {d.rate_day === null
              ? '—'
              : d.kind === 'term' && d.term_days
                ? termRateText(d.rate_day, d.term_days)
                : `${formatPercent(d.rate_day * DAYS_IN_WEEK, 2)} в неделю`}
          </span>
          <span className="col-span-2 md:col-span-1 text-white/40">
            {formatDateTime(d.opened_at)}
            {d.matures_at && <> → {formatDateTime(d.matures_at)}</>}
          </span>
        </li>
      ))}
    </ul>
  );
};

interface LoansListProps {
  loans: EconBankAdminLoan[];
  format: Format;
  onWriteOff: ((loan: EconBankAdminLoan) => void) | null;
}

const LoansList = ({ loans, format, onWriteOff }: LoansListProps) => {
  if (loans.length === 0) return <p className="text-white/40 text-xs italic">Открытых займов нет.</p>;
  return (
    <ul className="flex flex-col divide-y divide-white/[0.07]">
      <li className="hidden md:grid grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.3fr)_minmax(0,1.4fr)_auto] gap-3 pb-1.5 text-white/40 text-[11px] uppercase tracking-[0.06em]">
        <span>Заёмщик</span>
        <span>Займ</span>
        <span>Долг</span>
        <span>Начислено / выплачено</span>
        <span>Выдан / срок</span>
        <span className="sr-only">Действия</span>
      </li>
      {loans.map((l) => (
        <li
          key={l.id}
          className="py-2 grid grid-cols-2 md:grid-cols-[minmax(0,2fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1.3fr)_minmax(0,1.4fr)_auto] gap-x-3 gap-y-1 text-xs items-start"
        >
          <span className="col-span-2 md:col-span-1 flex flex-wrap items-center gap-1.5 min-w-0">
            <span className="text-white break-words">{l.character_name ?? `Персонаж #${l.character_id}`}</span>
            <span className="text-white/30">#{l.character_id}</span>
            {l.overdue && <Badge tone="red">Должник</Badge>}
          </span>
          <span className="flex flex-col text-white/60">
            <span className="text-white/80 whitespace-nowrap">
              <span className="md:hidden text-white/40">Займ: </span>
              {format(l.principal, true)}
            </span>
            <span className="text-white/40 whitespace-nowrap">
              {formatPercent(l.rate_day, 2)} в день, {l.term_days} дн.
            </span>
          </span>
          <span className={`whitespace-nowrap ${l.overdue ? 'text-site-red' : 'text-white/80'}`}>
            <span className="md:hidden text-white/40">Долг: </span>
            {format(l.debt, true)}
          </span>
          <span className="flex flex-col text-white/50">
            <span className="whitespace-nowrap">проценты {format(l.interest_total, true)}</span>
            {l.penalty_total > 0 && <span className="text-site-red whitespace-nowrap">пени {format(l.penalty_total, true)}</span>}
            <span className="whitespace-nowrap">погашено {format(l.paid_total, true)}</span>
            {l.collected_total > 0 && (
              <span className="whitespace-nowrap">взыскано {format(l.collected_total, true)}</span>
            )}
          </span>
          <span className="text-white/40">
            {formatDateTime(l.issued_at)} → <span className={l.overdue ? 'text-site-red' : ''}>{formatDateTime(l.due_at)}</span>
          </span>
          {onWriteOff ? (
            <button
              type="button"
              className="btn-line col-span-2 md:col-span-1 w-full md:w-auto !text-xs !py-1.5 !px-3 whitespace-nowrap"
              onClick={() => onWriteOff(l)}
            >
              Списать долг
            </button>
          ) : (
            <span className="hidden md:block" />
          )}
        </li>
      ))}
    </ul>
  );
};

interface BankDetailProps {
  bank: EconBankAdminItem;
  detail: EconBankAdminDetail | undefined;
  error: string | undefined;
  canSettings: boolean;
  format: Format;
  onCapital: (direction: EconBankCapitalDirection) => void;
  onWriteOff: (loan: EconBankAdminLoan) => void;
}

const BankDetail = ({ bank, detail, error, canSettings, format, onCapital, onWriteOff }: BankDetailProps) => (
  <div className="flex flex-col gap-4">
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-white/50">
      <span>
        Стартовый капитал:{' '}
        {bank.capital_seeded_at ? `взят ${formatDateTime(bank.capital_seeded_at)}` : 'ещё не выдавался'}
      </span>
      {canSettings && (
        <span className="flex flex-col sm:flex-row gap-2 w-full sm:w-auto sm:ml-auto">
          <button type="button" className="btn-line w-full sm:w-auto !text-xs !py-1.5 !px-4" onClick={() => onCapital('in')}>
            Капитал из казны
          </button>
          <button type="button" className="btn-line w-full sm:w-auto !text-xs !py-1.5 !px-4" onClick={() => onCapital('out')}>
            Вернуть капитал в казну
          </button>
        </span>
      )}
    </div>
    {error && !detail && <p className="text-site-red text-sm">{error}</p>}
    {!detail && !error && <div className="w-6 h-6 border-4 border-white/30 border-t-gold rounded-full animate-spin" />}
    {detail && (
      <>
        <div className="flex flex-col gap-2">
          <h4 className="text-white/70 text-xs uppercase tracking-[0.06em]">
            Вклады игроков{detail.deposits.length > 0 && ` (${detail.deposits.length})`}
          </h4>
          <DepositsList deposits={detail.deposits} format={format} />
        </div>
        <div className="flex flex-col gap-2">
          <h4 className="text-white/70 text-xs uppercase tracking-[0.06em]">
            Займы игроков{detail.loans.length > 0 && ` (${detail.loans.length})`}
          </h4>
          <LoansList loans={detail.loans} format={format} onWriteOff={canSettings ? onWriteOff : null} />
        </div>
      </>
    )}
  </div>
);

/* ------------------------------------------------------------------ dialogs */

interface CommentFieldProps {
  id: string;
  value: string;
  onChange: (v: string) => void;
}

const CommentField = ({ id, value, onChange }: CommentFieldProps) => {
  const trimmed = value.trim();
  const valid = trimmed.length >= COMMENT_MIN && trimmed.length <= COMMENT_MAX;
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="text-white/60 text-xs uppercase tracking-[0.06em]">
        Комментарий (обязательно)
      </label>
      <textarea
        id={id}
        className="textarea-bordered w-full"
        rows={3}
        maxLength={COMMENT_MAX}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Причина: попадёт в журнал операций"
      />
      {value !== '' && !valid && (
        <p className="text-site-red text-xs">
          От {COMMENT_MIN} до {COMMENT_MAX} символов
        </p>
      )}
    </div>
  );
};

const commentOk = (c: string) => c.trim().length >= COMMENT_MIN && c.trim().length <= COMMENT_MAX;

interface CapitalDialogProps {
  bank: EconBankAdminItem;
  direction: EconBankCapitalDirection;
  format: Format;
  onClose: () => void;
  onDone: () => void;
}

/** «Капитал из казны» / «Вернуть капитал в казну»: a posting between the region treasury and the bank. */
const CapitalDialog = ({ bank, direction, format, onClose, onDone }: CapitalDialogProps) => {
  const [amountText, setAmountText] = useState('');
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);

  const isIn = direction === 'in';
  const amount = Number(amountText);
  const amountValid =
    Number.isInteger(amount) && amount >= 1 && amount <= AMOUNT_MAX && (isIn || amount <= bank.lendable);

  const submit = async () => {
    setBusy(true);
    try {
      const res = await postEconomyBankCapital(bank.region_id, { direction, amount, comment: comment.trim() });
      toast.success(
        `${isIn ? 'Капитал внесён' : 'Капитал возвращён'}: ${format(amount)}. В банке ${format(res.bank_balance)}, в казне ${format(res.treasury_balance)}`,
      );
      onDone();
    } catch (e) {
      toast.error(apiErrorMessage(e, isIn ? 'Не удалось внести капитал' : 'Не удалось вернуть капитал'));
      setBusy(false);
    }
  };

  return (
    <ModalShell
      open
      onClose={onClose}
      dismissible={!busy}
      title={isIn ? 'Капитал из казны' : 'Вернуть капитал в казну'}
      size="md"
      footer={
        <>
          <button type="button" className="btn-line w-full sm:w-auto !text-xs !py-2 !px-5" onClick={onClose} disabled={busy}>
            Отмена
          </button>
          <button
            type="button"
            className="btn-blue w-full sm:w-auto !py-2 !px-5 !text-xs"
            disabled={!amountValid || !commentOk(comment) || busy}
            onClick={submit}
          >
            {busy ? 'Проводка...' : isIn ? 'Внести' : 'Вернуть'}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-4 text-sm">
        <p className="text-white/80">
          {isIn
            ? `Деньги перейдут из казны региона «${regionTitle(bank)}» на счёт его банка. Внести можно не больше, чем сейчас лежит в казне.`
            : `Деньги перейдут со счёта банка в казну региона «${regionTitle(bank)}». Вернуть можно только то, что банк может выдать: резерв под вклады жителей и вклады игроков не трогаются.`}
        </p>
        <p className="text-white/50">
          Свои средства банка: {format(bank.own_funds)}. Можно вернуть: {format(bank.lendable)}.
        </p>
        <div className="flex flex-col gap-1">
          <label htmlFor="econ-bank-capital-amount" className="text-white/60 text-xs uppercase tracking-[0.06em]">
            Сумма
          </label>
          <input
            id="econ-bank-capital-amount"
            type="number"
            inputMode="numeric"
            min={1}
            max={isIn ? AMOUNT_MAX : bank.lendable}
            step={1}
            className="input-underline w-full sm:max-w-[240px]"
            value={amountText}
            onChange={(e) => setAmountText(e.target.value)}
            placeholder="Например, 1000"
          />
          {amountText !== '' && !amountValid && (
            <p className="text-site-red text-xs">
              {isIn
                ? 'Целое число от 1 до 1 000 000 000'
                : `Целое число от 1 до ${formatDecimal(Math.max(bank.lendable, 0), 0)}`}
            </p>
          )}
          {amountValid && <p className="text-white/40 text-xs">{format(amount)}</p>}
        </div>
        <CommentField id="econ-bank-capital-comment" value={comment} onChange={setComment} />
      </div>
    </ModalShell>
  );
};

/** What the write-off dialog needs from either a detail loan row or a debtor row. */
interface WriteOffTarget {
  loanId: number;
  characterName: string;
  regionName: string;
  debt: number;
}

interface WriteOffDialogProps {
  target: WriteOffTarget;
  format: Format;
  onClose: () => void;
  onDone: () => void;
}

/** «Списать долг»: the loan closes, the bank takes the loss, no money moves. */
const WriteOffDialog = ({ target, format, onClose, onDone }: WriteOffDialogProps) => {
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    setBusy(true);
    try {
      await postEconomyBankLoanWriteOff(target.loanId, comment.trim());
      toast.success(`Долг персонажа «${target.characterName}» списан`);
      onDone();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось списать долг'));
      setBusy(false);
    }
  };

  return (
    <ModalShell
      open
      onClose={onClose}
      dismissible={!busy}
      title="Списать долг"
      size="md"
      footer={
        <>
          <button type="button" className="btn-line w-full sm:w-auto !text-xs !py-2 !px-5" onClick={onClose} disabled={busy}>
            Отмена
          </button>
          <button
            type="button"
            className="btn-blue w-full sm:w-auto !py-2 !px-5 !text-xs"
            disabled={!commentOk(comment) || busy}
            onClick={submit}
          >
            {busy ? 'Списание...' : 'Списать'}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-4 text-sm">
        <p className="text-white/80">
          Займ персонажа «{target.characterName}» в банке «{target.regionName}» будет закрыт, долг{' '}
          {format(target.debt)} — списан. Деньги никуда не переводятся: это убыток банка. Пометка «Должник» снимется.
        </p>
        <CommentField id="econ-bank-writeoff-comment" value={comment} onChange={setComment} />
      </div>
    </ModalShell>
  );
};

/* ------------------------------------------------------------------ debtors */

interface DebtorsProps {
  debtors: EconBankDebtor[] | null;
  error: string | null;
  format: Format;
  onWriteOff: ((d: EconBankDebtor) => void) | null;
}

const Debtors = ({ debtors, error, format, onWriteOff }: DebtorsProps) => (
  <section className="flex flex-col gap-3">
    <h3 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Должники</h3>
    {error && !debtors && <p className="text-site-red text-sm">{error}</p>}
    {!debtors && !error && <div className="w-6 h-6 border-4 border-white/30 border-t-gold rounded-full animate-spin" />}
    {debtors && debtors.length === 0 && <p className="text-white/40 text-sm italic">Просроченных займов нет.</p>}
    {debtors && debtors.length > 0 && (
      <ul className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
        {debtors.map((d) => (
          <li
            key={d.loan_id}
            className="bg-site-bg rounded-card border border-site-red/20 p-3 flex flex-col gap-2 text-sm min-w-0"
          >
            <span className="flex flex-wrap items-center gap-1.5 min-w-0">
              <span className="text-white break-words">{d.character_name ?? `Персонаж #${d.character_id}`}</span>
              <span className="text-white/30 text-xs">#{d.character_id}</span>
              <Badge tone="red">Должник</Badge>
            </span>
            <span className="text-white/50 text-xs break-words">
              Банк «{regionTitle(d)}» · срок {formatDateTime(d.due_at)}
              {d.overdue_days > 0 && `, просрочка ${d.overdue_days} дн.`}
            </span>
            <span className="grid grid-cols-3 gap-2 text-xs">
              <span className="flex flex-col">
                <span className="text-white/40">Долг</span>
                <span className="text-site-red whitespace-nowrap">{format(d.debt, true)}</span>
              </span>
              <span className="flex flex-col">
                <span className="text-white/40">Займ</span>
                <span className="text-white/80 whitespace-nowrap">{format(d.principal, true)}</span>
              </span>
              <span className="flex flex-col">
                <span className="text-white/40">Пени</span>
                <span className="text-white/80 whitespace-nowrap">{format(d.penalty_total, true)}</span>
              </span>
            </span>
            {onWriteOff && (
              <button
                type="button"
                className="btn-line self-stretch sm:self-start !text-xs !py-1.5 !px-4"
                onClick={() => onWriteOff(d)}
              >
                Списать долг
              </button>
            )}
          </li>
        ))}
      </ul>
    )}
  </section>
);

/* ------------------------------------------------------------------ tab */

interface EconomyBanksProps {
  canSettings: boolean;
  /** Called after money moved (capital, first switch-on) — the summary is refreshed. */
  onMoneyChanged: () => void;
}

/** «Банки» (FEAT-184): every bank — own funds, vault vs deposits, residents, loans, rates; flag, capital, write-offs. */
const EconomyBanks = ({ canSettings, onMoneyChanged }: EconomyBanksProps) => {
  const { format } = useCurrency();
  const { big } = useBigMoney();
  const [data, setData] = useState<EconBanksResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [debtors, setDebtors] = useState<EconBankDebtor[] | null>(null);
  const [debtorsError, setDebtorsError] = useState<string | null>(null);
  const [regions, setRegions] = useState<EconRegionItem[]>([]);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<BankFilter>('all');
  const [expanded, setExpanded] = useState<Set<number>>(() => new Set());
  const [details, setDetails] = useState<Record<number, EconBankAdminDetail>>({});
  const [detailErrors, setDetailErrors] = useState<Record<number, string>>({});
  const [flagBusy, setFlagBusy] = useState<number | null>(null);
  const [closeConfirm, setCloseConfirm] = useState<EconBankAdminItem | null>(null);
  const [capital, setCapital] = useState<{ bank: EconBankAdminItem; direction: EconBankCapitalDirection } | null>(null);
  const [writeOff, setWriteOff] = useState<WriteOffTarget | null>(null);
  const [newRegionId, setNewRegionId] = useState('');
  const [seedCapital, setSeedCapital] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    fetchEconomyBanks()
      .then((res) => {
        setData(res);
        setError(null);
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить банки');
        setError(msg);
        toast.error(msg);
      })
      .finally(() => setLoading(false));
    fetchEconomyBankDebtors()
      .then((res) => {
        setDebtors(res);
        setDebtorsError(null);
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить должников');
        setDebtorsError(msg);
        toast.error(msg);
      });
  }, []);

  const loadDetail = useCallback((regionId: number) => {
    fetchEconomyBank(regionId)
      .then((d) => {
        setDetails((prev) => ({ ...prev, [regionId]: d }));
        setDetailErrors((prev) => {
          const next = { ...prev };
          delete next[regionId];
          return next;
        });
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить вклады и займы банка');
        setDetailErrors((prev) => ({ ...prev, [regionId]: msg }));
        toast.error(msg);
      });
  }, []);

  useEffect(load, [load]);

  useEffect(() => {
    if (!canSettings) return;
    fetchEconomyRegions()
      .then(setRegions)
      .catch((e) => toast.error(apiErrorMessage(e, 'Не удалось загрузить список регионов')));
  }, [canSettings]);

  /** Reload the list, the debtors and every open detail after a change. */
  const refreshAll = useCallback(() => {
    load();
    expanded.forEach((id) => loadDetail(id));
  }, [load, loadDetail, expanded]);

  const toggle = (regionId: number) => {
    const opening = !expanded.has(regionId);
    if (opening) loadDetail(regionId);
    setExpanded((prev) => {
      const next = new Set(prev);
      if (opening) next.add(regionId);
      else next.delete(regionId);
      return next;
    });
  };

  const setFlag = async (regionId: number, isEnabled: boolean, seed = true) => {
    setFlagBusy(regionId);
    try {
      const item = await putEconomyBankFlag(regionId, { is_enabled: isEnabled, seed_capital: seed });
      if (!isEnabled) {
        toast.success(`Банк региона «${regionTitle(item)}» закрыт`);
      } else {
        toast.success(`Банк региона «${regionTitle(item)}» открыт. Свои средства банка: ${format(item.own_funds)}`);
      }
      refreshAll();
      onMoneyChanged();
      return true;
    } catch (e) {
      toast.error(apiErrorMessage(e, isEnabled ? 'Не удалось открыть банк' : 'Не удалось закрыть банк'));
      return false;
    } finally {
      setFlagBusy(null);
    }
  };

  const onSwitch = (b: EconBankAdminItem, next: boolean) => {
    if (next) setFlag(b.region_id, true);
    else setCloseConfirm(b);
  };

  const openNewBank = async () => {
    const id = Number(newRegionId);
    if (!id) return;
    if (await setFlag(id, true, seedCapital)) setNewRegionId('');
  };

  const items = useMemo(() => data?.items ?? [], [data]);

  const regionsWithoutBank = useMemo(() => {
    const has = new Set(items.map((b) => b.region_id));
    return regions
      .filter((r) => !has.has(r.region_id))
      .sort((a, b) => (a.name ?? '').localeCompare(b.name ?? '', 'ru'));
  }, [regions, items]);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items
      .filter((b) => {
        if (filter === 'enabled' && !b.enabled) return false;
        if (filter === 'disabled' && b.enabled) return false;
        if (filter === 'overdue' && b.overdue_count === 0) return false;
        if (filter === 'problems' && !needsAttention(b)) return false;
        if (!q) return true;
        return `${b.region_name ?? ''} ${b.country_name ?? ''}`.toLowerCase().includes(q);
      })
      .sort((a, b) => regionTitle(a).localeCompare(regionTitle(b), 'ru'));
  }, [items, search, filter]);

  const loanTarget = (l: EconBankAdminLoan, bank: EconBankAdminItem): WriteOffTarget => ({
    loanId: l.id,
    characterName: l.character_name ?? `Персонаж #${l.character_id}`,
    regionName: regionTitle(bank),
    debt: l.debt,
  });

  const debtorTarget = (d: EconBankDebtor): WriteOffTarget => ({
    loanId: d.loan_id,
    characterName: d.character_name ?? `Персонаж #${d.character_id}`,
    regionName: regionTitle(d),
    debt: d.debt,
  });

  const detailProps = (b: EconBankAdminItem) => ({
    bank: b,
    detail: details[b.region_id],
    error: detailErrors[b.region_id],
    canSettings,
    format,
    onCapital: (direction: EconBankCapitalDirection) => setCapital({ bank: b, direction }),
    onWriteOff: (l: EconBankAdminLoan) => setWriteOff(loanTarget(l, b)),
  });

  const totals = data?.totals;

  return (
    <div className="flex flex-col gap-5">
      <p className="text-white/50 text-sm max-w-3xl">
        Банк региона работает через НПС-банкиров. Свои средства банка — стартовый капитал, вклады жителей, возвраты
        займов и проценты; из них выдаются займы и платятся проценты. Вклады игроков лежат в отдельном хранилище,
        которое всегда равно сумме открытых вкладов и никогда не идёт в займы.
      </p>

      {/* filters + actions */}
      <div className="flex flex-col lg:flex-row lg:items-end gap-4">
        <div className="flex flex-col gap-1 min-w-0 lg:w-64">
          <label htmlFor="econ-banks-search" className="text-white/60 text-xs uppercase tracking-[0.06em]">
            Поиск
          </label>
          <input
            id="econ-banks-search"
            type="search"
            className="input-underline w-full"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Регион или страна"
          />
        </div>
        <div className="flex flex-col gap-1 min-w-0 lg:w-56">
          <label htmlFor="econ-banks-filter" className="text-white/60 text-xs uppercase tracking-[0.06em]">
            Показать
          </label>
          <select
            id="econ-banks-filter"
            className="input-underline w-full"
            value={filter}
            onChange={(e) => setFilter(e.target.value as BankFilter)}
          >
            {(Object.keys(BANK_FILTER_LABEL) as BankFilter[]).map((k) => (
              <option key={k} value={k} className="bg-site-dark text-white">
                {BANK_FILTER_LABEL[k]}
              </option>
            ))}
          </select>
        </div>
        <button
          type="button"
          onClick={refreshAll}
          disabled={loading}
          className="lg:ml-auto self-start lg:self-end inline-flex items-center gap-1.5 text-sm text-white/60 hover:text-site-blue transition-colors duration-200 ease-site disabled:opacity-40"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Обновить
        </button>
      </div>

      {/* open a bank in a region that has none yet */}
      {canSettings && (
        <div className="flex flex-col md:flex-row md:items-end gap-3 rounded-card border border-white/[0.07] px-4 py-3">
          <div className="flex flex-col gap-1 min-w-0 md:w-64">
            <label htmlFor="econ-banks-new" className="text-white/60 text-xs uppercase tracking-[0.06em]">
              Открыть банк в регионе
            </label>
            <select
              id="econ-banks-new"
              className="input-underline w-full"
              value={newRegionId}
              onChange={(e) => setNewRegionId(e.target.value)}
            >
              <option value="" className="bg-site-dark text-white">
                {regionsWithoutBank.length === 0 ? 'Во всех регионах банк уже заведён' : 'Выберите регион'}
              </option>
              {regionsWithoutBank.map((r) => (
                <option key={r.region_id} value={r.region_id} className="bg-site-dark text-white">
                  {r.name ?? `Регион #${r.region_id}`}
                </option>
              ))}
            </select>
          </div>
          <label htmlFor="econ-banks-seed" className="flex items-start gap-2 cursor-pointer select-none text-sm md:pb-1">
            <input
              id="econ-banks-seed"
              type="checkbox"
              checked={seedCapital}
              onChange={(e) => setSeedCapital(e.target.checked)}
              className="w-4 h-4 mt-0.5 shrink-0 accent-gold"
            />
            <span className="flex flex-col gap-0.5">
              <span className="text-white">Взять стартовый капитал из казны</span>
              <span className="text-white/40 text-xs">Один раз, не больше, чем есть в казне региона.</span>
            </span>
          </label>
          <button
            type="button"
            className="btn-blue w-full md:w-auto md:ml-auto !py-2 !px-5 !text-xs"
            disabled={!newRegionId || flagBusy !== null}
            onClick={openNewBank}
          >
            Открыть банк
          </button>
        </div>
      )}

      {/* totals */}
      {totals && (
        <dl className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
          {[
            ['Банков (работают)', `${totals.banks} (${totals.enabled})`, 0],
            ['Свои средства банков', big(totals.own_funds, true), totals.own_funds],
            ['Вклады игроков', big(totals.player_deposits, true), totals.player_deposits],
            ['Вклады жителей', big(totals.resident_deposits, true), totals.resident_deposits],
            ['Долг игроков по займам', big(totals.player_loans_debt, true), totals.player_loans_debt],
            ['Займы жителей', big(totals.resident_loans, true), totals.resident_loans],
            ['Должников', String(totals.debtors), 0],
          ].map(([label, value, amount]) => (
            <div
              key={label}
              className="bg-site-bg rounded-card border border-white/[0.07] px-3 sm:px-4 py-3 flex flex-col gap-0.5 min-w-0"
            >
              <dt className="text-white/50 text-[11px] sm:text-xs uppercase tracking-[0.06em] break-words">{label}</dt>
              <dd
                className={`text-base sm:text-lg break-words ${
                  label === 'Должников' && totals.debtors > 0 ? 'text-site-red' : 'text-white'
                }`}
                title={typeof amount === 'number' && Math.abs(amount) >= COMPACT_MONEY_FROM ? format(amount) : undefined}
              >
                {value}
              </dd>
            </div>
          ))}
        </dl>
      )}

      {error && !data && <p className="text-site-red text-sm">{error}</p>}
      {!data && !error && <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />}
      {data && items.length === 0 && (
        <p className="text-white/40 text-sm italic">
          Банков пока нет. Откройте банк в регионе выше или через «Заполнить регионы по шаблонам».
        </p>
      )}
      {data && items.length > 0 && visible.length === 0 && (
        <p className="text-white/40 text-sm italic">Под фильтр не попал ни один банк.</p>
      )}

      {data && visible.length > 0 && (
        <div className={`transition-opacity ${loading ? 'opacity-60' : ''}`}>
          {/* Table — xl and up */}
          <div className="hidden xl:block bg-site-bg rounded-card border border-white/[0.07] px-4 py-2">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-white/50 text-xs uppercase tracking-[0.06em] text-left border-b border-white/10">
                  <th className="py-2 pr-3 font-normal">Регион</th>
                  <th className="py-2 pr-3 font-normal">Банк есть</th>
                  <th className="py-2 pr-3 font-normal">Свои средства</th>
                  <th className="py-2 pr-3 font-normal">Хранилище вкладов</th>
                  <th className="py-2 pr-3 font-normal">Жители</th>
                  <th className="py-2 pr-3 font-normal">Займы игроков</th>
                  <th className="py-2 pr-3 font-normal">Ставки</th>
                  <th className="py-2 font-normal">Последний пересчёт</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((b) => {
                  const open = expanded.has(b.region_id);
                  return (
                    <Fragment key={b.region_id}>
                      <tr
                        onClick={() => toggle(b.region_id)}
                        className={`align-top cursor-pointer hover:bg-white/[0.04] transition-colors duration-200 ease-site ${
                          open ? '' : 'border-b border-white/[0.07] last:border-b-0'
                        }`}
                      >
                        <td className="py-2 pr-3 max-w-[240px]">
                          <span className="flex items-start gap-1.5">
                            {open ? (
                              <ChevronDown size={15} className="text-gold shrink-0 mt-0.5" />
                            ) : (
                              <ChevronRight size={15} className="text-gold shrink-0 mt-0.5" />
                            )}
                            <BankTitle b={b} />
                          </span>
                        </td>
                        <td className="py-2 pr-3">
                          {canSettings ? (
                            <Switch
                              checked={b.enabled}
                              disabled={flagBusy !== null}
                              onChange={(next) => onSwitch(b, next)}
                              label={b.enabled ? 'Закрыть банк' : 'Открыть банк'}
                            />
                          ) : (
                            <span className="text-white/70">{b.enabled ? 'да' : 'нет'}</span>
                          )}
                        </td>
                        <td className="py-2 pr-3">
                          <Funds b={b} />
                        </td>
                        <td className="py-2 pr-3">
                          <Vault b={b} />
                        </td>
                        <td className="py-2 pr-3">
                          <Residents b={b} />
                        </td>
                        <td className="py-2 pr-3">
                          <Loans b={b} />
                        </td>
                        <td className="py-2 pr-3 max-w-[220px]">
                          <Rates b={b} />
                        </td>
                        <td className="py-2 max-w-[240px]">
                          <LastPass b={b} />
                        </td>
                      </tr>
                      {open && (
                        <tr className="border-b border-white/[0.07] last:border-b-0">
                          <td colSpan={8} className="pb-3 pl-6 pr-2">
                            <BankDetail {...detailProps(b)} />
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Cards — below xl */}
          <ul className="xl:hidden grid grid-cols-1 md:grid-cols-2 gap-3">
            {visible.map((b) => {
              const open = expanded.has(b.region_id);
              return (
                <li
                  key={b.region_id}
                  className={`bg-site-bg rounded-card border border-white/[0.07] p-3 flex flex-col gap-3 text-sm min-w-0 ${
                    open ? 'md:col-span-2' : ''
                  }`}
                >
                  <div className="flex items-start gap-2">
                    <button
                      type="button"
                      onClick={() => toggle(b.region_id)}
                      aria-expanded={open}
                      className="flex items-start gap-2 text-left flex-1 min-w-0"
                    >
                      {open ? (
                        <ChevronDown size={16} className="text-gold shrink-0 mt-0.5" />
                      ) : (
                        <ChevronRight size={16} className="text-gold shrink-0 mt-0.5" />
                      )}
                      <BankTitle b={b} />
                    </button>
                    {canSettings && (
                      <Switch
                        checked={b.enabled}
                        disabled={flagBusy !== null}
                        onChange={(next) => onSwitch(b, next)}
                        label={b.enabled ? 'Закрыть банк' : 'Открыть банк'}
                      />
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <span className="flex flex-col gap-0.5 min-w-0">
                      <span className="text-white/40 text-xs">Свои средства</span>
                      <Funds b={b} />
                    </span>
                    <span className="flex flex-col gap-0.5 min-w-0">
                      <span className="text-white/40 text-xs">Хранилище вкладов</span>
                      <Vault b={b} />
                    </span>
                    <span className="flex flex-col gap-0.5 min-w-0">
                      <span className="text-white/40 text-xs">Жители</span>
                      <Residents b={b} />
                    </span>
                    <span className="flex flex-col gap-0.5 min-w-0">
                      <span className="text-white/40 text-xs">Займы игроков</span>
                      <Loans b={b} />
                    </span>
                  </div>
                  <span className="flex flex-col gap-0.5">
                    <span className="text-white/40 text-xs">Ставки</span>
                    <Rates b={b} />
                  </span>
                  <span className="flex flex-col gap-0.5">
                    <span className="text-white/40 text-xs">Последний пересчёт</span>
                    <LastPass b={b} />
                  </span>
                  {open && (
                    <div className="border-t border-white/10 pt-3">
                      <BankDetail {...detailProps(b)} />
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </div>
      )}

      <Debtors
        debtors={debtors}
        error={debtorsError}
        format={format}
        onWriteOff={canSettings ? (d) => setWriteOff(debtorTarget(d)) : null}
      />

      {closeConfirm && (
        <ConfirmDialog
          title="Закрыть банк"
          message={`Банк региона «${regionTitle(closeConfirm)}» перестанет принимать вклады, выдавать займы и платить проценты по вкладам. Снятие, переводы, погашение и взыскание займов продолжат работать, жители постепенно заберут свои вклады.`}
          confirmLabel="Закрыть банк"
          danger
          onCancel={() => setCloseConfirm(null)}
          onConfirm={() => {
            const regionId = closeConfirm.region_id;
            setCloseConfirm(null);
            setFlag(regionId, false);
          }}
        />
      )}

      {capital && (
        <CapitalDialog
          bank={capital.bank}
          direction={capital.direction}
          format={format}
          onClose={() => setCapital(null)}
          onDone={() => {
            setCapital(null);
            refreshAll();
            onMoneyChanged();
          }}
        />
      )}

      {writeOff && (
        <WriteOffDialog
          target={writeOff}
          format={format}
          onClose={() => setWriteOff(null)}
          onDone={() => {
            setWriteOff(null);
            refreshAll();
          }}
        />
      )}
    </div>
  );
};

export default EconomyBanks;
