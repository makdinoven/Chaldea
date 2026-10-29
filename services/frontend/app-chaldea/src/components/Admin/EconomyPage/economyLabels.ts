import type { EconAccountKind, EconLegType } from '../../../types/economy';

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
};

export const accountKindLabel = (kind: string | null | undefined): string =>
  (kind && ACCOUNT_KIND_LABELS[kind as EconAccountKind]) || 'Счёт';

export const LEG_TYPE_LABELS: Record<EconLegType, string> = {
  main: 'основная',
  refund: 'возврат',
  commission: 'комиссия',
  tax: 'налог',
};

/** Account kinds an admin emission may target (backend rule). */
export const EMISSION_KINDS: EconAccountKind[] = ['region_treasury', 'country_treasury', 'world_treasury'];

/** Account kinds an admin adjustment may target (everything except source and auction accounts). */
export const ADJUST_KINDS: EconAccountKind[] = [
  'character',
  'region_treasury',
  'country_treasury',
  'world_treasury',
];

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
