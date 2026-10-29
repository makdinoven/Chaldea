import type { EconAccountKind, EconLegType, EconMerchantReason } from '../../../types/economy';
import { COMPACT_MONEY_FROM, compactNumber } from '../../../utils/compactNumber';

/** Russian labels of ledger operation types (econ_core.OP_TYPES). */
export const OP_TYPE_LABELS: Record<string, string> = {
  genesis: 'Начальная эмиссия',
  admin_emission: 'Эмиссия (админ)',
  admin_adjust: 'Корректировка (админ)',
  starter_kit: 'Стартовый набор',
  battle_reward: 'Награда за бой',
  battle_pass_reward: 'Награда боевого пропуска',
  dungeon_reward: 'Награда подземелья',
  dungeon_expense: 'Расходы в подземелье',
  teleport: 'Телепорт',
  trade: 'Обмен',
  auction_bid: 'Ставка на аукционе',
  auction_refund: 'Возврат ставки',
  auction_buyout: 'Выкуп на аукционе',
  auction_settlement: 'Завершение торгов',
  auction_claim: 'Получение из хранилища',
  npc_shop_buy: 'Покупка у НПС',
  npc_shop_buy_refund: 'Возврат покупки у НПС',
  npc_shop_sell: 'Продажа НПС',
  quest_reward: 'Награда за задание',
  house_purchase: 'Покупка дома',
  house_build: 'Строительство дома',
  house_tax: 'Налог на дом',
  house_resale: 'Перепродажа дома',
  character_deleted: 'Удаление персонажа',
  treasury_closed: 'Закрытие казны',
  region_tick: 'Пересчёт региона',
  merchant_trade: 'Торговля с жителями',
  bank_deposit: 'Вклад в банк',
  bank_withdraw: 'Снятие со вклада',
  bank_transfer: 'Банковский перевод',
  bank_tick: 'Банк: проценты и жители',
  bank_capital: 'Капитал банка',
  loan_issue: 'Выдача займа',
  loan_repay: 'Погашение займа',
  loan_collect: 'Взыскание долга',
};

export const opTypeLabel = (opType: string): string => OP_TYPE_LABELS[opType] ?? opType;

export const ACCOUNT_KIND_LABELS: Record<EconAccountKind, string> = {
  character: 'Персонаж',
  region_treasury: 'Казна региона',
  country_treasury: 'Казна страны',
  world_treasury: 'Казна Скитальцев',
  auction_escrow: 'Ставки аукциона',
  auction_storage: 'Хранилище аукциона',
  emission: 'Эмиссия',
  adjustment: 'Корректировки',
  population_purse: 'Кошелёк жителей',
  bank: 'Банк региона',
  bank_deposits: 'Вклады игроков',
};

export const accountKindLabel = (kind: string | null | undefined): string =>
  (kind && ACCOUNT_KIND_LABELS[kind as EconAccountKind]) || 'Счёт';

/** Region-owned accounts that are named after their region (prefixed with the kind in lists). */
const REGION_PREFIXED_KINDS: ReadonlySet<string> = new Set<EconAccountKind>(['population_purse', 'bank', 'bank_deposits']);

/**
 * Display name of an account. A population purse and the two bank accounts carry their region's name, so they
 * are prefixed («Кошелёк жителей — Эльмирия», «Банк региона — Эльмирия») to tell them apart from the region
 * treasury with the same name.
 */
export const accountDisplayName = (account: {
  kind: string | null | undefined;
  name: string | null;
  account_id: number;
}): string => {
  const base = account.name ?? `#${account.account_id}`;
  return account.kind && REGION_PREFIXED_KINDS.has(account.kind)
    ? `${ACCOUNT_KIND_LABELS[account.kind as EconAccountKind]} — ${base}`
    : base;
};

export const LEG_TYPE_LABELS: Record<EconLegType, string> = {
  main: 'основная',
  refund: 'возврат',
  commission: 'комиссия',
  tax: 'налог',
  trade_tax: 'налог с выручки',
  interest: 'проценты',
};

/** Account kinds an admin emission may target (backend rule). */
export const EMISSION_KINDS: EconAccountKind[] = [
  'region_treasury',
  'population_purse',
  'country_treasury',
  'world_treasury',
];

/** Account kinds an admin adjustment may target (everything except source and auction accounts). */
export const ADJUST_KINDS: EconAccountKind[] = [
  'character',
  'region_treasury',
  'population_purse',
  'country_treasury',
  'world_treasury',
];

/** Every account kind, for «all kinds» pickers (journal filter). */
export const ALL_ACCOUNT_KINDS: EconAccountKind[] = [
  'character',
  'region_treasury',
  'population_purse',
  'country_treasury',
  'world_treasury',
  'auction_escrow',
  'auction_storage',
  'emission',
  'adjustment',
  'bank',
  'bank_deposits',
];

/** Op type the journal hides by default: one per simulated region every 6 hours. */
export const REGION_TICK_OP = 'region_tick';

/** «0,1234» → «12,3 %»: tax rates and other shares. */
export const formatPercent = (share: number, digits = 1): string =>
  `${(share * 100).toLocaleString('ru-RU', { maximumFractionDigits: digits })}%`;

/** Plain decimal with a Russian separator: stocks, multipliers. */
export const formatDecimal = (n: number, digits = 2): string =>
  n.toLocaleString('ru-RU', { maximumFractionDigits: digits });

/** Goods quantities (stocks, norms, flows): one decimal, compact from 100 000 («1.2 м»). */
export const formatQty = (n: number): string =>
  Math.abs(n) >= COMPACT_MONEY_FROM ? compactNumber(n) : formatDecimal(n, 1);

/** «12.03.2026, 14:05» in the viewer's time zone; the server sends naive UTC timestamps. */
export const formatDateTime = (iso: string): string => {
  const hasZone = /(Z|[+-]\d{2}:?\d{2})$/.test(iso);
  const d = new Date(hasZone ? iso : `${iso}Z`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};

/** Why an NPC merchant is not living (FEAT-183, `econ_core.merchant_status`) — shared by the shop editor and «Торговцы». */
export const MERCHANT_REASON_LABELS: Record<EconMerchantReason, string> = {
  not_npc: 'персонаж не является НПС',
  dead: 'НПС мёртв — лавка закрыта',
  no_location: 'НПС не стоит ни в одной локации',
  dungeon: 'НПС находится в подземелье',
  no_region: 'локация НПС не относится ни к одному региону',
  not_simulated: 'экономика региона не моделируется',
};

export const merchantReasonText = (reason: string | null | undefined): string =>
  (reason && MERCHANT_REASON_LABELS[reason as EconMerchantReason]) || 'причина неизвестна';

/** Skip reasons of «Пополнить кассы торговцев» (merchant reasons + the fund's own). */
const MERCHANT_FUND_SKIP_LABELS: Record<string, string> = {
  at_target: 'касса уже не меньше нормы',
  no_target: 'норма кассы равна нулю (нет рыночных товаров)',
  not_merchant: 'не торговец',
  region_filtered: 'не в выбранных регионах',
};

export const merchantFundSkipText = (reason: string): string =>
  MERCHANT_FUND_SKIP_LABELS[reason] ?? merchantReasonText(reason);
