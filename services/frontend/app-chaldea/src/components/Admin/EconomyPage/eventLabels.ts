/**
 * FEAT-187 — labels and bounds of region events (feature file 3.4 / 3.8). The bounds mirror the backend validator
 * `schemas.EventEffectIn` so the builder blocks a bad value before the server answers 422.
 */
import type {
  EconEventEffect,
  EconEventEffectType,
  EconEventKind,
  EconEventOrigin,
  EconEventScope,
  EconEventStatus,
  EconEventTrigger,
} from '../../../types/economy';
import { YEAR_SEGMENTS, SEGMENT_LABELS } from '../../../utils/gameTime';
import { parseServerDate } from '../../../utils/serverDate';
import { formatDecimal } from './economyLabels';

/** Which numeric field an effect type carries. */
export type EffectValueField = 'mult' | 'share' | 'delta' | 'pct';

export interface EffectSpec {
  label: string;
  /** Short explanation under the type select. */
  help: string;
  /** Takes a list of goods groups. */
  groups: boolean;
  /** Numeric field, if any (merchants_halt / bank_panic have none). */
  field: EffectValueField | null;
  /** Bounds in API units (share / pct as 0..1 fractions). */
  min: number;
  max: number;
  /** Value of a newly added row. */
  initial: number;
  /** Applied once per event (at the first recount after the start) rather than every recount. */
  oneShot: boolean;
}

export const EFFECT_SPECS: Record<EconEventEffectType, EffectSpec> = {
  production: {
    label: 'Производство',
    help: 'Множитель производства выбранных групп, каждый пересчёт.',
    groups: true, field: 'mult', min: 0, max: 5, initial: 0.7, oneShot: false,
  },
  consumption: {
    label: 'Потребление',
    help: 'Множитель потребления (спроса) выбранных групп, каждый пересчёт.',
    groups: true, field: 'mult', min: 0, max: 5, initial: 1.3, oneShot: false,
  },
  labor: {
    label: 'Больные жители',
    help: 'Меньше работников: множитель производства всех групп, потребление не меняется.',
    groups: false, field: 'mult', min: 0, max: 1.5, initial: 0.8, oneShot: false,
  },
  price: {
    label: 'Цены',
    help: 'Множитель цены выбранных групп после расчёта (в пределах мин./макс. цены).',
    groups: true, field: 'mult', min: 0.2, max: 5, initial: 1.15, oneShot: false,
  },
  tax_income: {
    label: 'Доход казны',
    help: 'Множитель налога с жителей, каждый пересчёт.',
    groups: false, field: 'mult', min: 0, max: 5, initial: 0.8, oneShot: false,
  },
  stability: {
    label: 'Стабильность',
    help: 'Прибавка или убавка стабильности (0–100) за каждый пересчёт.',
    groups: false, field: 'delta', min: -10, max: 10, initial: -1, oneShot: false,
  },
  prosperity: {
    label: 'Достаток',
    help: 'Прибавка или убавка достатка (0–100) за каждый пересчёт.',
    groups: false, field: 'delta', min: -10, max: 10, initial: -1, oneShot: false,
  },
  merchants_halt: {
    label: 'Торговцы не докупают',
    help: 'Живые торговцы не пополняют склад у жителей; жители у них по-прежнему покупают.',
    groups: false, field: null, min: 0, max: 0, initial: 0, oneShot: false,
  },
  bank_panic: {
    label: 'Банковская паника',
    help: 'Жители забирают вклады из банка региона (насколько хватит денег банка). Вклады игроков не трогаются.',
    groups: false, field: null, min: 0, max: 0, initial: 0, oneShot: false,
  },
  loan_boom: {
    label: 'Бум займов',
    help: 'Жители берут больше займов в банке региона: множитель их доли займов.',
    groups: false, field: 'mult', min: 1, max: 5, initial: 1.5, oneShot: false,
  },
  stock_loss: {
    label: 'Потеря запасов',
    help: 'Разово: доля запасов выбранных групп пропадает со складов региона.',
    groups: true, field: 'share', min: 0, max: 0.9, initial: 0.1, oneShot: true,
  },
  treasury_expense: {
    label: 'Расход казны',
    help: 'Разово: доля положительного остатка казны уходит жителям «на восстановление» (проводка в журнале).',
    groups: false, field: 'share', min: 0, max: 0.9, initial: 0.1, oneShot: true,
  },
  population: {
    label: 'Население',
    help: 'Разово и навсегда: лорное население меняется на указанный процент (не ниже 1 жителя расчёта).',
    groups: false, field: 'pct', min: -0.5, max: 0.5, initial: -0.01, oneShot: true,
  },
};

export const EFFECT_TYPES = Object.keys(EFFECT_SPECS) as EconEventEffectType[];

/** Max effects / chains per template (schemas 3.8). */
export const MAX_EFFECTS = 12;
export const MAX_CHAINS = 10;
export const MAX_EFFECT_GROUPS = 12;
/** «Все группы» marker in `groups`. */
export const ALL_GROUPS = '*';

/** Field units in the UI: share / pct are edited in percent. */
export const PERCENT_FIELDS: EffectValueField[] = ['share', 'pct'];

export const KIND_LABELS: Record<EconEventKind, string> = {
  bad: 'Кризис',
  good: 'Благоприятное',
};

export const TRIGGER_LABELS: Record<EconEventTrigger, string> = {
  random: 'Случайно',
  low_stability: 'При долгой низкой стабильности',
  manual: 'Только вручную',
};

export const SCOPE_LABELS: Record<EconEventScope, string> = {
  region: 'Регион',
  neighbours: 'Регион и соседи',
  country: 'Вся страна',
  world: 'Весь мир',
};

export const ORIGIN_LABELS: Record<EconEventOrigin, string> = {
  random: 'случайно',
  manual: 'вручную',
  spread: 'перекинулось',
  chain: 'цепочка',
  riot: 'бунт',
};

export const STATUS_LABELS: Record<EconEventStatus, string> = {
  active: 'Идёт',
  ended: 'Закончилось',
  cancelled: 'Отменено',
};

/** Calendar segments in year order (spring, beltane, …) — the season filter of a template. */
export const SEASON_CODES: string[] = YEAR_SEGMENTS.map((s) => s.name);
export const seasonLabel = (code: string): string => SEGMENT_LABELS[code] ?? code;

export const labelOf = <K extends string>(map: Record<K, string>, key: string): string =>
  (map as Record<string, string>)[key] ?? key;

/** Tailwind text colour of an event kind: crises red, good events green. */
export const kindTextClass = (kind: string): string => (kind === 'good' ? 'text-stat-energy' : 'text-site-red');
export const kindBadgeClass = (kind: string): string =>
  kind === 'good'
    ? 'border-stat-energy/40 bg-stat-energy/10 text-stat-energy'
    : 'border-site-red/50 bg-site-red/10 text-site-red';

const signed = (n: number, digits = 2): string => `${n > 0 ? '+' : n < 0 ? '−' : ''}${formatDecimal(Math.abs(n), digits)}`;

/** 0.25 → «25 %», −0.03 → «−3 %». */
const percentText = (share: number, withSign: boolean): string => {
  const value = Math.round(share * 10000) / 100;
  return `${withSign ? signed(value) : formatDecimal(value)} %`;
};

const groupsText = (groups: string[] | null | undefined, groupNames: Record<string, string>): string => {
  if (!groups || groups.length === 0) return '';
  if (groups.includes(ALL_GROUPS)) return 'все группы';
  return groups.map((g) => (groupNames[g] ?? g).toLowerCase()).join(', ');
};

/** «Производство: продовольствие ×0,5», «Стабильность −1,5 за пересчёт», «Население −3 % (разово)». */
export const describeEffect = (effect: EconEventEffect, groupNames: Record<string, string>): string => {
  const spec = EFFECT_SPECS[effect.type];
  if (!spec) return String(effect.type);
  const groups = spec.groups ? groupsText(effect.groups, groupNames) : '';
  const head = groups ? `${spec.label}: ${groups}` : spec.label;
  switch (spec.field) {
    case 'mult':
      return `${head} ×${formatDecimal(effect.mult ?? 1)}`;
    case 'delta':
      return `${head} ${signed(effect.delta ?? 0)} за пересчёт`;
    case 'share':
      return `${head} ${percentText(effect.share ?? 0, false)} (разово)`;
    case 'pct':
      return `${head} ${percentText(effect.pct ?? 0, true)} (разово)`;
    default:
      return head;
  }
};

const MS_HOUR = 3_600_000;
const HOURS_PER_DAY = 24;

/** «ещё 6 дн. 4 ч» / «ещё 5 ч» / «скоро закончится» — from `ends_at` vs now. */
export const remainingText = (endsAt: string, now: number = Date.now()): string => {
  const end = parseServerDate(endsAt);
  if (!end) return '';
  const hours = Math.floor((end.getTime() - now) / MS_HOUR);
  if (hours < 1) return 'скоро закончится';
  const days = Math.floor(hours / HOURS_PER_DAY);
  const rest = hours % HOURS_PER_DAY;
  if (days === 0) return `ещё ${rest} ч`;
  return rest > 0 ? `ещё ${days} дн. ${rest} ч` : `ещё ${days} дн.`;
};

/** «6–12 дн.» */
export const durationText = (minDays: number, maxDays: number): string =>
  minDays === maxDays ? `${formatDecimal(minDays)} дн.` : `${formatDecimal(minDays)}–${formatDecimal(maxDays)} дн.`;
