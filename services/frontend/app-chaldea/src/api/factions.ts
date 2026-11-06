import axios from 'axios';
import type { EconOperation } from '../types/economy';

/**
 * FEAT-205 — factions (character-service, contract features/FEAT-205 §3.10).
 *
 * Player side: catalog, private view (profile tab), journal, public memberships
 * (passport), join / apply / cancel / leave. Admin side: faction CRUD, ranks,
 * entry conditions, hostility pairs, applications, members, character card,
 * reward deliveries, settings.
 *
 * Secrecy is enforced by the server: secret factions come without member
 * counts, never appear in public lists, and a secret faction is never named in
 * a player-facing condition text (its `params` are null). Fame / infamy
 * conditions arrive as tier names only — never numbers.
 */

const BASE = '/characters';

/* ── Shared ─────────────────────────────────────────────────────────────── */

export type FactionConditionType =
  | 'region_reputation'
  | 'fame'
  | 'infamy'
  | 'level'
  | 'class'
  | 'subclass'
  | 'race'
  | 'quest'
  | 'not_in_faction';

export const FACTION_CONDITION_TYPES: FactionConditionType[] = [
  'region_reputation',
  'fame',
  'infamy',
  'level',
  'class',
  'subclass',
  'race',
  'quest',
  'not_in_faction',
];

export const FACTION_CONDITION_LABEL: Record<FactionConditionType, string> = {
  region_reputation: 'Репутация в крае',
  fame: 'Слава',
  infamy: 'Слухи (дурная слава)',
  level: 'Уровень',
  class: 'Класс',
  subclass: 'Подкласс',
  race: 'Раса',
  quest: 'Выполненное задание',
  not_in_faction: 'Не состоит во фракции',
};

/** Loose param bag: each condition type carries its own keys (see §3.4). */
export type FactionConditionParams = Record<string, unknown>;

/** A player-facing condition with its ✓/✗ (`met` is null without a character). */
export interface FactionConditionView {
  type: FactionConditionType | string;
  text: string;
  met: boolean | null;
  /** Null for a condition that names a secret faction. */
  params?: FactionConditionParams | null;
}

/** Next-rank requirement: points / level / quest. */
export interface FactionRankRequirement {
  type: 'points' | 'level' | 'quest' | string;
  text: string;
  met: boolean;
}

export type FactionMemberStatus = 'active' | 'left' | 'expelled';
export type FactionApplicationStatus = 'pending' | 'approved' | 'rejected' | 'cancelled';
export type FactionMyStatus = 'none' | FactionMemberStatus | 'pending';

export const FACTION_MEMBER_STATUS_LABEL: Record<FactionMemberStatus, string> = {
  active: 'Состоит',
  left: 'Вышел',
  expelled: 'Исключён',
};

export const FACTION_APPLICATION_STATUS_LABEL: Record<FactionApplicationStatus, string> = {
  pending: 'На рассмотрении',
  approved: 'Одобрена',
  rejected: 'Отклонена',
  cancelled: 'Отозвана',
};

/* ── Wealth (FEAT-206) ──────────────────────────────────────────────────── */

/** Players only ever see the word, never the number (admin sees numbers). */
export type FactionWealthState = 'thriving' | 'stable' | 'struggling' | 'destitute';

export interface FactionWealth {
  state: FactionWealthState | string;
  label: string;
}

/** Text colour per wealth level (design tokens). */
export const FACTION_WEALTH_CLASS: Record<string, string> = {
  thriving: 'text-stat-energy',
  stable: 'text-gold-light',
  struggling: 'text-white/70',
  destitute: 'text-site-red',
};

/* ── Catalog ────────────────────────────────────────────────────────────── */

export interface FactionLeader {
  id: number;
  name: string | null;
  avatar: string | null;
}

export interface FactionRankBrief {
  id: number;
  name: string;
  sort_order: number;
  /** FEAT-207: the passive this rank gives (null — none). */
  passive?: FactionPassiveBrief | null;
}

export interface FactionMyState {
  status: FactionMyStatus;
  rank_name: string | null;
  rejoin_in_seconds: number | null;
  application_id: number | null;
  reapply_in_seconds: number | null;
}

export interface FactionCatalogItem {
  id: number;
  name: string;
  description: string | null;
  emblem_url: string | null;
  hq_location: { id: number; name: string | null } | null;
  leaders: FactionLeader[];
  is_invite_only: boolean;
  is_secret: boolean;
  /** Null for a secret faction. */
  member_count: number | null;
  /** Null for a secret faction or when unlimited. */
  member_limit: number | null;
  ranks: FactionRankBrief[];
  conditions: FactionConditionView[];
  my: FactionMyState | null;
  can_join: boolean;
  join_block_reason: string | null;
  /** FEAT-206: null for a secret faction (unless the character is an active member) or without a template. */
  wealth?: FactionWealth | null;
  /** FEAT-207: regions where the faction is outlawed (not membership data). */
  outlaw_regions?: FactionOutlawRegion[];
}

/* ── Private view (profile tab) ─────────────────────────────────────────── */

export interface FactionMembership {
  membership_id: number;
  faction: { id: number; name: string; emblem_url: string | null; is_secret: boolean };
  status: FactionMemberStatus;
  points: number;
  rank: { id: number; name: string } | null;
  rank_title: { id: number; name: string } | null;
  next_rank: { id: number; name: string; conditions: FactionRankRequirement[] } | null;
  warning: { reasons: string[]; remaining_seconds: number | null } | null;
  joined_at: string | null;
  rejoin_in_seconds: number | null;
  /** FEAT-206: active memberships only. */
  wealth?: FactionWealth | null;
  /** FEAT-206: what the faction still owes the character (marks), any status. */
  debt?: number;
  /** FEAT-206: active memberships only. */
  donation?: FactionDonationInfo | null;
  /** FEAT-207: passives of all ranks up to the held one (active memberships only). */
  passives?: FactionPassiveView[];
  /** FEAT-207: regions where this faction is outlawed (active memberships only). */
  outlaw_regions?: FactionOutlawRegion[];
}

export interface FactionDonationInfo {
  enabled: boolean;
  marks_per_point: number;
  daily_cap: number;
  points_today: number;
  marks_today: number;
  resets_in_seconds: number;
  /** FEAT-207: item donations accepted (the faction economy ticks). */
  items_enabled?: boolean;
  items_disabled_reason?: string | null;
}

export interface FactionDonateResult {
  points_delta: number;
  points_after: number;
  points_today: number;
  daily_cap: number;
  marks_today: number;
  rank_ups: number;
  new_balance: number;
}

export const FACTION_DONATION_MAX = 1_000_000;

/** Points a donation would add today (§3.4: fractions carry within the UTC day, capped). */
export const donationPointsPreview = (info: FactionDonationInfo, marks: number): number => {
  if (!info.marks_per_point || marks <= 0) return 0;
  const total = Math.min(info.daily_cap, Math.floor((info.marks_today + marks) / info.marks_per_point));
  return Math.max(0, total - info.points_today);
};

/* ── Quartermaster (FEAT-206) ───────────────────────────────────────────── */

export type QuartermasterProbeState = 'none' | 'silent' | 'open';

export const QM_SILENT_TEXT = 'Этот человек с вами не разговаривает';
export const QM_QUANTITY_MAX = 99;

export interface QuartermasterItem {
  qm_item_id: number;
  item: { id: number; name: string; image: string | null; item_type: string | null; item_rarity: string | null };
  price: number;
  final_price: number;
  stock: number;
  min_rank: { id: number; name: string } | null;
  locked_reason: string | null;
}

export interface QuartermasterView {
  npc: { id: number; name: string };
  faction: { id: number; name: string; emblem_url: string | null };
  member: boolean;
  rank: { id: number; name: string; discount_pct: number } | null;
  balance: number;
  items: QuartermasterItem[];
}

export interface QuartermasterBuyResult {
  purchase_id: number;
  delivered: boolean;
  price_total: number;
  new_balance: number;
  message: string;
}

export interface FactionApplicationBrief {
  id: number;
  faction_id: number;
  faction_name: string | null;
  status: FactionApplicationStatus;
  created_at: string | null;
  reject_reason: string | null;
}

export interface FactionPlayerSettings {
  rejoin_cooldown_days: number;
  leave_burn_pct: number;
  warning_days: number;
}

export interface FactionPrivateView {
  memberships: FactionMembership[];
  applications: FactionApplicationBrief[];
  settings: FactionPlayerSettings;
  /** FEAT-207: sum of all active passives over every faction. */
  passive_total?: FactionModifiers;
}

export interface FactionHistoryItem {
  id: number;
  faction_id: number;
  faction_name: string | null;
  event_type: string;
  text: string;
  points_delta: number | null;
  points_after: number | null;
  created_at: string;
}

export interface FactionHistoryPage {
  items: FactionHistoryItem[];
  total: number;
  page: number;
  page_size: number;
}

/** Backend cap for `page_size`. */
export const FACTION_PAGE_MAX = 50;

export interface FactionPublicMembership {
  faction_id: number;
  name: string;
  emblem_url: string | null;
  rank_name: string | null;
}

export interface FactionJoinResult {
  membership_id: number;
  rank_name: string | null;
  notices_text: string[];
}

export interface FactionLeaveResult {
  points_after: number;
  rejoin_in_seconds: number | null;
}

/* ── Player calls ───────────────────────────────────────────────────────── */

export const fetchFactionCatalog = async (characterId?: number | null): Promise<FactionCatalogItem[]> => {
  const params = characterId ? { character_id: characterId } : undefined;
  const { data } = await axios.get<FactionCatalogItem[]>(`${BASE}/factions/catalog`, { params });
  return data;
};

export const fetchFactionPublic = async (factionId: number): Promise<FactionCatalogItem> => {
  const { data } = await axios.get<FactionCatalogItem>(`${BASE}/factions/${factionId}/public`);
  return data;
};

export const fetchMyFactions = async (characterId: number): Promise<FactionPrivateView> => {
  const { data } = await axios.get<FactionPrivateView>(`${BASE}/${characterId}/factions`);
  return data;
};

export const fetchFactionHistory = async (
  characterId: number,
  page: number,
  pageSize: number,
): Promise<FactionHistoryPage> => {
  const { data } = await axios.get<FactionHistoryPage>(`${BASE}/${characterId}/factions/history`, {
    params: { page, page_size: Math.min(pageSize, FACTION_PAGE_MAX) },
  });
  return data;
};

export const fetchPublicFactions = async (characterId: number): Promise<FactionPublicMembership[]> => {
  const { data } = await axios.get<FactionPublicMembership[]>(`${BASE}/${characterId}/factions/public`);
  return data;
};

export const joinFaction = async (characterId: number, factionId: number): Promise<FactionJoinResult> => {
  const { data } = await axios.post<FactionJoinResult>(`${BASE}/${characterId}/factions/${factionId}/join`);
  return data;
};

export const applyToFaction = async (
  characterId: number,
  factionId: number,
  message: string | null,
): Promise<{ application_id: number }> => {
  const { data } = await axios.post<{ application_id: number }>(
    `${BASE}/${characterId}/factions/${factionId}/apply`,
    { message },
  );
  return data;
};

export const cancelFactionApplication = async (characterId: number, applicationId: number): Promise<void> => {
  await axios.delete(`${BASE}/${characterId}/factions/applications/${applicationId}`);
};

export const leaveFaction = async (characterId: number, factionId: number): Promise<FactionLeaveResult> => {
  const { data } = await axios.post<FactionLeaveResult>(`${BASE}/${characterId}/factions/${factionId}/leave`);
  return data;
};

export const donateToFaction = async (
  characterId: number,
  factionId: number,
  amount: number,
  requestId: string,
): Promise<FactionDonateResult> =>
  (
    await axios.post<FactionDonateResult>(`${BASE}/${characterId}/factions/${factionId}/donate`, {
      amount,
      request_id: requestId,
    })
  ).data;

export const probeQuartermaster = async (npcId: number, characterId: number): Promise<QuartermasterProbeState> =>
  (
    await axios.get<{ state: QuartermasterProbeState }>(`${BASE}/factions/quartermaster/npc/${npcId}/probe`, {
      params: { character_id: characterId },
    })
  ).data.state;

export const fetchQuartermaster = async (npcId: number, characterId: number): Promise<QuartermasterView> =>
  (
    await axios.get<QuartermasterView>(`${BASE}/factions/quartermaster/npc/${npcId}`, {
      params: { character_id: characterId },
    })
  ).data;

export const buyFromQuartermaster = async (
  npcId: number,
  body: { character_id: number; qm_item_id: number; quantity: number; request_id: string },
): Promise<QuartermasterBuyResult> =>
  (await axios.post<QuartermasterBuyResult>(`${BASE}/factions/quartermaster/npc/${npcId}/buy`, body)).data;

/** Seconds from the server → a Date to count down to (taken at fetch time). */
export const secondsToDate = (seconds: number | null | undefined): Date | null =>
  seconds && seconds > 0 ? new Date(Date.now() + seconds * 1000) : null;

/* ── Admin ──────────────────────────────────────────────────────────────── */

export const FACTION_LIMITS = {
  nameMax: 100,
  descriptionMax: 5000,
  leadersMax: 5,
  memberLimitMax: 100_000,
  rankPointsMax: 10_000_000,
  rankLevelMax: 1000,
  rankXpMax: 10_000_000,
  rankItemsMax: 10,
  itemQtyMax: 999,
  conditionsMax: 20,
  adminDeltaMax: 100_000,
  reasonMin: 3,
  reasonMax: 500,
  questPointsMax: 10_000,
  questRewardsMax: 5,
} as const;

export interface FactionAdminListItem {
  id: number;
  name: string;
  emblem_url: string | null;
  is_active: boolean;
  is_secret: boolean;
  is_invite_only: boolean;
  member_limit: number | null;
  sort_order: number;
  member_count: number;
  pending_applications: number;
  rank_count: number;
  condition_count: number;
}

export interface FactionRankItem {
  item_id: number;
  quantity: number;
}

export interface FactionRankAdmin {
  id: number;
  faction_id: number;
  name: string;
  description: string | null;
  sort_order: number;
  min_points: number;
  min_level: number;
  required_quest_id: number | null;
  reward_xp: number;
  reward_title_id: number | null;
  reward_items: FactionRankItem[];
  reward_house_location_id: number | null;
  reward_plot_location_id: number | null;
  /** FEAT-206: marks paid from the treasury on grant (or owed). */
  reward_marks?: number;
  /** FEAT-206: quartermaster discount for holders of this rank, %. */
  qm_discount_pct?: number;
  /** FEAT-207: rank passive (battle modifiers while the rank — or a higher one — is held). */
  passive_name?: string | null;
  passive_description?: string | null;
  passive_modifiers?: FactionModifiers | null;
}

export interface FactionConditionAdmin {
  type: FactionConditionType;
  params: FactionConditionParams;
  text: string;
}

export interface FactionHostility {
  id: number;
  faction_a_id: number;
  faction_a_name: string | null;
  faction_b_id: number;
  faction_b_name: string | null;
  irreconcilable: boolean;
  created_at: string | null;
}

export interface FactionAdminDetail {
  id: number;
  name: string;
  description: string | null;
  emblem_url: string | null;
  hq_location_id: number | null;
  hq_location_name: string | null;
  leader_npc_ids: number[];
  leaders: FactionLeader[];
  member_limit: number | null;
  is_invite_only: boolean;
  is_secret: boolean;
  is_active: boolean;
  sort_order: number;
  created_at: string | null;
  updated_at: string | null;
  member_count: number;
  ranks: FactionRankAdmin[];
  conditions: FactionConditionAdmin[];
  hostilities: FactionHostility[];
}

export interface FactionInput {
  name: string;
  description: string | null;
  emblem_url: string | null;
  hq_location_id: number | null;
  leader_npc_ids: number[] | null;
  member_limit: number | null;
  is_invite_only: boolean;
  is_secret: boolean;
  is_active: boolean;
  sort_order: number;
}

export interface FactionRankInput {
  name: string;
  description: string | null;
  min_points: number;
  min_level: number;
  required_quest_id: number | null;
  reward_xp: number;
  reward_title_id: number | null;
  reward_items: FactionRankItem[] | null;
  reward_house_location_id: number | null;
  reward_plot_location_id: number | null;
  reward_marks?: number;
  qm_discount_pct?: number;
  /* FEAT-207 */
  passive_name?: string | null;
  passive_description?: string | null;
  passive_modifiers?: FactionModifiers | null;
}

export interface FactionConditionInput {
  type: FactionConditionType;
  params: FactionConditionParams;
}

export interface FactionHostilityInput {
  faction_a_id: number;
  faction_b_id: number;
  irreconcilable: boolean;
}

export interface FactionAdminCharacterBrief {
  id: number;
  name: string | null;
  level: number | null;
  avatar: string | null;
}

export interface FactionApplicationAdmin {
  id: number;
  status: FactionApplicationStatus;
  message: string | null;
  created_at: string | null;
  decided_at: string | null;
  decided_by_user_id: number | null;
  reject_reason: string | null;
  faction: { id: number; name: string | null };
  character: FactionAdminCharacterBrief & { class_id: number | null; class_name: string | null };
  conditions: { type: string; text: string; met: boolean | null }[];
}

export interface FactionPage<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface FactionMemberAdmin {
  membership_id: number;
  faction_id: number;
  character: FactionAdminCharacterBrief;
  status: FactionMemberStatus;
  points: number;
  rank: { id: number; name: string | null } | null;
  warning: { at: string | null; reasons: string[]; remaining_seconds: number | null } | null;
  joined_at: string | null;
  left_at: string | null;
  rejoin_after: string | null;
  /** Only in the admin character card. */
  faction?: { id: number; name: string | null; is_secret: boolean; is_active: boolean };
}

export type FactionDeliveryKind = 'xp' | 'title' | 'item' | 'voucher';
export type FactionDeliveryStatus = 'pending' | 'sending' | 'done' | 'failed';

export const FACTION_DELIVERY_KIND_LABEL: Record<FactionDeliveryKind, string> = {
  xp: 'Опыт',
  title: 'Титул',
  item: 'Предмет',
  voucher: 'Право на дом',
};

export const FACTION_DELIVERY_STATUS_LABEL: Record<FactionDeliveryStatus, string> = {
  pending: 'Ожидает',
  sending: 'Выдаётся',
  done: 'Выдано',
  failed: 'Ошибка',
};

export interface FactionDelivery {
  id: number;
  grant_id: number;
  rank_name: string | null;
  kind: FactionDeliveryKind;
  payload: Record<string, unknown>;
  status: FactionDeliveryStatus;
  attempts: number;
  next_attempt_at: string | null;
  last_error: string | null;
  updated_at: string | null;
}

export interface FactionAdminCharacter {
  character: { id: number; name: string; level: number; is_npc: boolean };
  memberships: FactionMemberAdmin[];
  grants: {
    id: number;
    faction_id: number;
    faction_name: string | null;
    rank_id: number;
    rank_name: string | null;
    granted_at: string | null;
  }[];
  deliveries: FactionDelivery[];
  history: FactionHistoryItem[];
  /** FEAT-206 */
  debts?: FactionDebtAdmin[];
  qm_purchases?: FactionQmPurchase[];
}

export interface FactionSettings {
  warning_days: number;
  rejoin_cooldown_days: number;
  leave_burn_pct: number;
  hostile_penalty_pct: number;
  reapply_cooldown_hours: number;
  /* FEAT-206 economy settings */
  donation_marks_per_point: number;
  donation_points_daily_cap: number;
  econ_purse_share_pct: number;
  econ_treasury_share_pct: number;
  members_leave_pct: number;
  members_grow_pct: number;
  qm_take_share_pct: number;
  econ_enabled: boolean;
  /* FEAT-207 territory / kills / outlaw settings */
  kill_points_daily_cap: number;
  pvp_kill_repeat_hours: number;
  outlaw_check_cooldown_hours: number;
  econ_item_sale_share_pct: number;
}

export type FactionNumericSettingKey = Exclude<keyof FactionSettings, 'econ_enabled'>;

export interface FactionSettingField {
  key: FactionNumericSettingKey;
  label: string;
  min: number;
  max: number;
}

/** FEAT-206 — bounds of `faction_econ.ECON_SETTINGS_BOUNDS`. */
export const FACTION_ECON_SETTINGS_FIELDS: FactionSettingField[] = [
  { key: 'donation_marks_per_point', label: 'Марок за одно очко пожертвования', min: 1, max: 10000 },
  { key: 'donation_points_daily_cap', label: 'Очков за пожертвования в день (0 — не даются)', min: 0, max: 100000 },
  { key: 'econ_purse_share_pct', label: 'Доля кошелька жителей края на все фракции за пересчёт, %', min: 0, max: 20 },
  { key: 'econ_treasury_share_pct', label: 'Доля казны края на все фракции за пересчёт, %', min: 0, max: 20 },
  { key: 'members_leave_pct', label: 'Уход участников без жалованья за пересчёт, %', min: 0, max: 50 },
  { key: 'members_grow_pct', label: 'Приток участников при богатой казне за пересчёт, %', min: 0, max: 10 },
  { key: 'qm_take_share_pct', label: 'Доля запаса группы товаров края на закупку интенданта, %', min: 0, max: 50 },
];

/** FEAT-207 §3.2 bounds. */
export const FACTION_TERRITORY_SETTINGS_FIELDS: FactionSettingField[] = [
  { key: 'kill_points_daily_cap', label: 'Очков за победы над врагами в день (0 — не даются)', min: 0, max: 100000 },
  { key: 'pvp_kill_repeat_hours', label: 'Часов до повторных очков за того же противника', min: 0, max: 720 },
  { key: 'outlaw_check_cooldown_hours', label: 'Часов между правонарушениями «членство» в одном крае', min: 1, max: 720 },
  { key: 'econ_item_sale_share_pct', label: 'Доля кошелька края штаба на продажу пожертвованных предметов за пересчёт, %', min: 0, max: 20 },
];

export const FACTION_SETTINGS_FIELDS: FactionSettingField[] = [
  { key: 'warning_days', label: 'Дней до исключения после предупреждения', min: 0, max: 60 },
  { key: 'rejoin_cooldown_days', label: 'Дней до повторного вступления', min: 0, max: 365 },
  { key: 'leave_burn_pct', label: 'Сгорает очков при выходе, %', min: 0, max: 100 },
  { key: 'hostile_penalty_pct', label: 'Штраф враждебной фракции, %', min: 0, max: 100 },
  { key: 'reapply_cooldown_hours', label: 'Часов до повторной заявки', min: 0, max: 720 },
];

const ADMIN = `${BASE}/admin/factions`;

export const adminListFactions = async (): Promise<FactionAdminListItem[]> =>
  (await axios.get<FactionAdminListItem[]>(ADMIN)).data;

export const adminGetFaction = async (factionId: number): Promise<FactionAdminDetail> =>
  (await axios.get<FactionAdminDetail>(`${ADMIN}/${factionId}`)).data;

export const adminCreateFaction = async (body: FactionInput): Promise<FactionAdminDetail> =>
  (await axios.post<FactionAdminDetail>(ADMIN, body)).data;

export const adminUpdateFaction = async (factionId: number, body: FactionInput): Promise<FactionAdminDetail> =>
  (await axios.put<FactionAdminDetail>(`${ADMIN}/${factionId}`, body)).data;

export const adminDeleteFaction = async (factionId: number): Promise<void> => {
  await axios.delete(`${ADMIN}/${factionId}`);
};

export const adminCreateRank = async (factionId: number, body: FactionRankInput): Promise<FactionRankAdmin> =>
  (await axios.post<FactionRankAdmin>(`${ADMIN}/${factionId}/ranks`, body)).data;

export const adminUpdateRank = async (rankId: number, body: FactionRankInput): Promise<FactionRankAdmin> =>
  (await axios.put<FactionRankAdmin>(`${ADMIN}/ranks/${rankId}`, body)).data;

export const adminDeleteRank = async (rankId: number): Promise<void> => {
  await axios.delete(`${ADMIN}/ranks/${rankId}`);
};

export const adminReorderRanks = async (factionId: number, rankIds: number[]): Promise<FactionRankAdmin[]> =>
  (await axios.put<FactionRankAdmin[]>(`${ADMIN}/${factionId}/ranks/order`, { rank_ids: rankIds })).data;

export const adminSetConditions = async (
  factionId: number,
  conditions: FactionConditionInput[],
): Promise<FactionConditionAdmin[]> =>
  (await axios.put<FactionConditionAdmin[]>(`${ADMIN}/${factionId}/conditions`, { conditions })).data;

export const adminListHostilities = async (): Promise<FactionHostility[]> =>
  (await axios.get<FactionHostility[]>(`${ADMIN}/hostilities`)).data;

export const adminCreateHostility = async (body: FactionHostilityInput): Promise<FactionHostility> =>
  (await axios.post<FactionHostility>(`${ADMIN}/hostilities`, body)).data;

export const adminUpdateHostility = async (hostilityId: number, body: FactionHostilityInput): Promise<FactionHostility> =>
  (await axios.put<FactionHostility>(`${ADMIN}/hostilities/${hostilityId}`, body)).data;

export const adminDeleteHostility = async (hostilityId: number): Promise<void> => {
  await axios.delete(`${ADMIN}/hostilities/${hostilityId}`);
};

export const adminListApplications = async (params: {
  status: FactionApplicationStatus | 'all';
  faction_id?: number | null;
  page: number;
  page_size: number;
}): Promise<FactionPage<FactionApplicationAdmin>> => {
  const query: Record<string, string | number> = { status: params.status, page: params.page, page_size: params.page_size };
  if (params.faction_id) query.faction_id = params.faction_id;
  return (await axios.get<FactionPage<FactionApplicationAdmin>>(`${ADMIN}/applications`, { params: query })).data;
};

export const adminApproveApplication = async (applicationId: number): Promise<unknown> =>
  (await axios.post(`${ADMIN}/applications/${applicationId}/approve`)).data;

export const adminRejectApplication = async (applicationId: number, reason: string | null): Promise<unknown> =>
  (await axios.post(`${ADMIN}/applications/${applicationId}/reject`, { reason })).data;

export const adminListMembers = async (
  factionId: number,
  params: { status: FactionMemberStatus | 'all'; q?: string; page: number; page_size: number },
): Promise<FactionPage<FactionMemberAdmin>> => {
  const query: Record<string, string | number> = { status: params.status, page: params.page, page_size: params.page_size };
  if (params.q && params.q.trim()) query.q = params.q.trim();
  return (await axios.get<FactionPage<FactionMemberAdmin>>(`${ADMIN}/${factionId}/members`, { params: query })).data;
};

export const adminMemberPoints = async (
  membershipId: number,
  delta: number,
  reason: string,
): Promise<{ membership_id: number; points_delta: number; points_after: number; rank_id: number | null }> =>
  (await axios.post(`${ADMIN}/members/${membershipId}/points`, { delta, reason })).data;

export const adminExpelMember = async (membershipId: number, reason: string): Promise<unknown> =>
  (await axios.post(`${ADMIN}/members/${membershipId}/expel`, { reason })).data;

export const adminFactionCharacter = async (characterId: number): Promise<FactionAdminCharacter> =>
  (await axios.get<FactionAdminCharacter>(`${ADMIN}/characters/${characterId}`)).data;

export const adminRetryDelivery = async (deliveryId: number): Promise<FactionAdminCharacter> =>
  (await axios.post<FactionAdminCharacter>(`${ADMIN}/deliveries/${deliveryId}/retry`)).data;

export const adminGetFactionSettings = async (): Promise<FactionSettings> =>
  (await axios.get<FactionSettings>(`${ADMIN}/settings`)).data;

export const adminPutFactionSettings = async (body: FactionSettings): Promise<FactionSettings> =>
  (await axios.put<FactionSettings>(`${ADMIN}/settings`, body)).data;

/* ── Admin: faction economy (FEAT-206) ──────────────────────────────────── */

export const FACTION_RANK_MARKS_MAX = 1_000_000;
export const FACTION_QM_DISCOUNT_MAX = 50;
export const FACTION_MEMBERS_MAX = 100_000;
export const FACTION_QM_PRICE_MAX = 10_000_000;
export const FACTION_QM_STOCK_MAX = 100_000;
export const FACTION_QUARTERMASTERS_MAX = 10;
export const FACTION_FILL_COMMENT_MIN = 3;
export const FACTION_FILL_COMMENT_MAX = 500;

export type FactionProfileKind = 'none' | 'members_purse' | 'income_share' | 'treasury_share';

export const FACTION_PROFILE_KINDS: FactionProfileKind[] = ['none', 'members_purse', 'income_share', 'treasury_share'];

export const FACTION_PROFILE_KIND_LABEL: Record<FactionProfileKind, string> = {
  none: 'Нет',
  members_purse: 'С участника — из кошелька жителей',
  income_share: 'Доля оборота рынка края',
  treasury_share: 'Доля казны края',
};

/** Params as stored (decimals arrive as strings). */
export type FactionEconParams = Record<string, string | number>;

export interface FactionEconParamSpec {
  key: string;
  label: string;
  kind: 'int' | 'dec' | 'kind';
  min?: number;
  max?: number;
  hint: string;
}

/** `faction_econ.PARAM_SPECS` (whitelist + bounds). */
export const FACTION_ECON_PARAM_SPECS: FactionEconParamSpec[] = [
  { key: 'start_members', label: 'Участников при заполнении', kind: 'int', min: 0, max: 100000, hint: 'ставит «Заполнить по шаблону»' },
  { key: 'norm_per_member', label: 'Норма казны на участника', kind: 'int', min: 1, max: 100000, hint: 'казна = норма → богатство 50, вдвое больше → 100' },
  { key: 'start_treasury_per_member', label: 'Стартовая казна на участника', kind: 'int', min: 0, max: 100000, hint: 'цель пополнения при «Заполнить по шаблону»' },
  { key: 'dues_per_member', label: 'Взнос участника за пересчёт', kind: 'dec', min: 0, max: 1000, hint: 'из кошелька жителей края штаба в казну' },
  { key: 'wage_per_member', label: 'Жалованье участника за пересчёт', kind: 'dec', min: 0, max: 1000, hint: 'из казны в кошелёк жителей' },
  { key: 'profile_kind', label: 'Источник дохода по профилю', kind: 'kind', hint: 'доход сверх взносов' },
  { key: 'profile_per_member', label: 'Доход по профилю на участника', kind: 'dec', min: 0, max: 1000, hint: 'для «с участника»' },
  { key: 'profile_rate', label: 'Доля дохода по профилю', kind: 'dec', min: 0, max: 0.2, hint: 'для долей оборота / казны края, 0…0,2' },
  { key: 'qm_budget_share', label: 'Доля бюджета закупок интенданта', kind: 'dec', min: 0, max: 1, hint: 'от казны сверх половины нормы, 0…1' },
];

export interface FactionEconomyAdmin {
  faction_id: number;
  template_code: string | null;
  template_name: string | null;
  overrides: FactionEconParams;
  params: FactionEconParams | null;
  econ_enabled: boolean;
  members_count: number;
  members_min: number;
  members_max: number;
  treasury: { account_id: number | null; balance: number };
  norm: number | null;
  wealth: number | null;
  wealth_label: string | null;
  hq: {
    location_id: number;
    location_name: string | null;
    region_id: number | null;
    region_name: string | null;
    simulated: boolean;
  } | null;
  ticking: boolean;
  not_ticking_reason: string | null;
  last: {
    tick_at: string | null;
    dues: number;
    profile: number;
    wages_due: number;
    wages_paid: number;
    restock: number;
    debts_paid: number;
    members_delta: number;
    /** FEAT-207: item sales of the last tick, marks. */
    item_sales?: number;
  };
  debts: { open_count: number; open_total: number };
  /** FEAT-207: donated items waiting for the tick sale. */
  item_stock?: FactionItemStockRow[];
  quartermasters: { npc_id: number; name: string | null; npc_role: string | null }[];
}

export interface FactionEconomyInput {
  template_code: string | null;
  overrides: FactionEconParams | null;
  econ_enabled: boolean;
  members_count: number;
  members_min: number;
  members_max: number;
}

export interface FactionEconHistoryRow {
  id: number;
  run_id: number;
  balance_before: number;
  balance_after: number;
  dues: number;
  profile: number;
  wages_due: number;
  wages_paid: number;
  restock_spent: number;
  restock_items: number;
  debts_paid: number;
  members_before: number;
  members_after: number;
  wealth: number;
  created_at: string;
  /* FEAT-207 */
  item_sales?: number;
  items_sold?: number;
}

export type FactionDebtStatus = 'open' | 'paid';

export const FACTION_DEBT_SOURCE_LABEL: Record<string, string> = {
  rank: 'Марки за звание',
  refund: 'Возврат за покупку',
};

export const FACTION_DEBT_STATUS_LABEL: Record<string, string> = {
  open: 'Не выплачен',
  paid: 'Выплачен',
};

export interface FactionDebtAdmin {
  id: number;
  faction_id: number;
  faction_name?: string | null;
  character: { id: number; name: string | null };
  source: string;
  amount: number;
  paid: number;
  status: FactionDebtStatus | string;
  created_at: string | null;
  paid_at: string | null;
}

export interface FactionEconTemplate {
  code: string;
  name: string;
  description: string | null;
  params: FactionEconParams;
  sort_order: number;
  updated_at: string | null;
  used_by: number;
}

export interface FactionEconTemplateInput {
  code?: string;
  name: string;
  description: string | null;
  params: FactionEconParams;
  sort_order: number;
}

export interface FactionQuartermasterAdmin {
  npc_id: number;
  name: string | null;
  npc_role: string | null;
  location_id: number | null;
  location_name: string | null;
  npc_status: string;
}

export interface FactionQmItemAdmin {
  id: number;
  faction_id: number;
  item_id: number;
  item: { id: number; name: string; image: string | null; item_type: string | null; item_rarity: string | null } | null;
  price: number;
  min_rank_id: number | null;
  min_rank_name: string | null;
  stock: number;
  restock_target: number;
  is_active: boolean;
  sort_order: number;
  off_market: boolean;
  group: string | null;
  updated_at: string | null;
}

export interface FactionQmItemInput {
  item_id: number;
  price: number;
  min_rank_id: number | null;
  stock: number;
  restock_target: number;
  is_active: boolean;
  sort_order: number;
}

export type FactionQmPurchaseStatus = 'pending' | 'sending' | 'done' | 'failed' | 'refunded';

export const FACTION_QM_PURCHASE_STATUS_LABEL: Record<string, string> = {
  pending: 'Ожидает выдачи',
  sending: 'Выдаётся',
  done: 'Выдано',
  failed: 'Ошибка выдачи',
  refunded: 'Деньги возвращены',
};

export interface FactionQmPurchase {
  id: number;
  faction_id: number;
  character: { id: number; name: string | null };
  item: { id: number; name: string | null; image?: string | null };
  qm_item_id: number | null;
  npc_id: number | null;
  quantity: number;
  price_total: number;
  status: FactionQmPurchaseStatus | string;
  attempts: number;
  next_attempt_at: string | null;
  last_error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

/** «uncertain: …» — the item may have been delivered; the admin checks the inventory first. */
export const qmErrorText = (error: string | null): string | null => {
  if (!error) return null;
  return error.startsWith('uncertain')
    ? 'неясно, дошёл ли предмет — проверьте инвентарь перед повтором или возвратом'
    : error;
};

export const adminFactionEconomy = async (factionId: number): Promise<FactionEconomyAdmin> =>
  (await axios.get<FactionEconomyAdmin>(`${ADMIN}/${factionId}/economy`)).data;

export const adminPutFactionEconomy = async (factionId: number, body: FactionEconomyInput): Promise<FactionEconomyAdmin> =>
  (await axios.put<FactionEconomyAdmin>(`${ADMIN}/${factionId}/economy`, body)).data;

export const adminFillFactionEconomy = async (
  factionId: number,
  body: { comment: string; set_members: boolean },
): Promise<{ members_count: number; emitted: number; balance: number }> =>
  (await axios.post<{ members_count: number; emitted: number; balance: number }>(`${ADMIN}/${factionId}/economy/fill`, body))
    .data;

export const adminFactionEconHistory = async (
  factionId: number,
  page: number,
  pageSize = 20,
): Promise<FactionPage<FactionEconHistoryRow>> =>
  (
    await axios.get<FactionPage<FactionEconHistoryRow>>(`${ADMIN}/${factionId}/economy/history`, {
      params: { page, page_size: pageSize },
    })
  ).data;

export const adminFactionEconOperations = async (
  factionId: number,
  page: number,
  pageSize = 20,
): Promise<FactionPage<EconOperation>> =>
  (
    await axios.get<FactionPage<EconOperation>>(`${ADMIN}/${factionId}/economy/operations`, {
      params: { page, page_size: pageSize },
    })
  ).data;

export const adminFactionDebts = async (
  factionId: number,
  status: FactionDebtStatus | 'all',
  page: number,
  pageSize = 20,
): Promise<FactionPage<FactionDebtAdmin>> =>
  (
    await axios.get<FactionPage<FactionDebtAdmin>>(`${ADMIN}/${factionId}/debts`, {
      params: { status, page, page_size: pageSize },
    })
  ).data;

export const adminListEconTemplates = async (): Promise<FactionEconTemplate[]> =>
  (await axios.get<FactionEconTemplate[]>(`${ADMIN}/econ-templates`)).data;

export const adminCreateEconTemplate = async (body: FactionEconTemplateInput): Promise<FactionEconTemplate> =>
  (await axios.post<FactionEconTemplate>(`${ADMIN}/econ-templates`, body)).data;

export const adminUpdateEconTemplate = async (code: string, body: FactionEconTemplateInput): Promise<FactionEconTemplate> =>
  (await axios.put<FactionEconTemplate>(`${ADMIN}/econ-templates/${encodeURIComponent(code)}`, body)).data;

export const adminDeleteEconTemplate = async (code: string): Promise<void> => {
  await axios.delete(`${ADMIN}/econ-templates/${encodeURIComponent(code)}`);
};

export const adminFactionQuartermasters = async (factionId: number): Promise<FactionQuartermasterAdmin[]> =>
  (await axios.get<FactionQuartermasterAdmin[]>(`${ADMIN}/${factionId}/quartermasters`)).data;

export const adminSetFactionQuartermasters = async (
  factionId: number,
  npcIds: number[],
): Promise<FactionQuartermasterAdmin[]> =>
  (await axios.put<FactionQuartermasterAdmin[]>(`${ADMIN}/${factionId}/quartermasters`, { npc_ids: npcIds })).data;

export const adminFactionQmItems = async (factionId: number): Promise<FactionQmItemAdmin[]> =>
  (await axios.get<FactionQmItemAdmin[]>(`${ADMIN}/${factionId}/qm-items`)).data;

export const adminCreateQmItem = async (factionId: number, body: FactionQmItemInput): Promise<FactionQmItemAdmin> =>
  (await axios.post<FactionQmItemAdmin>(`${ADMIN}/${factionId}/qm-items`, body)).data;

export const adminUpdateQmItem = async (qmItemId: number, body: FactionQmItemInput): Promise<FactionQmItemAdmin> =>
  (await axios.put<FactionQmItemAdmin>(`${ADMIN}/qm-items/${qmItemId}`, body)).data;

export const adminDeleteQmItem = async (qmItemId: number): Promise<void> => {
  await axios.delete(`${ADMIN}/qm-items/${qmItemId}`);
};

export const adminFactionQmPurchases = async (
  factionId: number,
  status: FactionQmPurchaseStatus | 'all',
  page: number,
  pageSize = 20,
): Promise<FactionPage<FactionQmPurchase>> =>
  (
    await axios.get<FactionPage<FactionQmPurchase>>(`${ADMIN}/${factionId}/qm-purchases`, {
      params: { status, page, page_size: pageSize },
    })
  ).data;

export const adminRetryQmPurchase = async (purchaseId: number): Promise<FactionQmPurchase> =>
  (await axios.post<FactionQmPurchase>(`${ADMIN}/qm-purchases/${purchaseId}/retry`)).data;

export const adminRefundQmPurchase = async (purchaseId: number): Promise<FactionQmPurchase> =>
  (await axios.post<FactionQmPurchase>(`${ADMIN}/qm-purchases/${purchaseId}/refund`)).data;

/* ── FEAT-207: territory, rank passives, enemies, outlaw regions, item donations ── */

/** Battle modifiers of a passive: `{key: int}` (keys — `FACTION_PASSIVE_KEYS`). */
export type FactionModifiers = Record<string, number>;

export const FACTION_PASSIVE_LIMITS = {
  nameMax: 100,
  descriptionMax: 500,
  keysMax: 10,
  valueMin: -100,
  valueMax: 100,
} as const;

export interface FactionPassiveBrief {
  name: string;
  description: string | null;
  modifiers: FactionModifiers;
}

export interface FactionPassiveView extends FactionPassiveBrief {
  rank_id: number;
  rank_name: string;
}

export interface FactionOutlawRegion {
  region_id: number;
  region_name: string | null;
  level_name: string | null;
}

/** Sum of several modifier maps (client-side total of one faction's passives); zero sums dropped. */
export const sumModifiers = (maps: FactionModifiers[]): FactionModifiers => {
  const out: FactionModifiers = {};
  for (const m of maps) {
    for (const [k, v] of Object.entries(m ?? {})) out[k] = (out[k] ?? 0) + Number(v || 0);
  }
  return Object.fromEntries(Object.entries(out).filter(([, v]) => v !== 0));
};

/* Item donations (player) */

export const FACTION_ITEM_DONATION_LINES_MAX = 20;
export const FACTION_ITEM_DONATION_QTY_MAX = 9999;

export interface FactionDonatableItem {
  item_id: number;
  name: string;
  image: string | null;
  item_rarity: string | null;
  quantity: number;
  /** Wholesale price in the HQ region now, marks per piece. */
  unit_value: number;
}

export interface FactionItemDonationOptions {
  enabled: boolean;
  reason: string | null;
  marks_per_point: number;
  daily_cap: number;
  points_today: number;
  marks_today: number;
  resets_in_seconds: number;
  items: FactionDonatableItem[];
}

export interface FactionItemDonateResult {
  points_delta: number;
  points_after: number;
  points_today: number;
  daily_cap: number;
  value_total: number;
  items_given: number;
  rank_ups: number;
}

export const fetchFactionItemDonation = async (
  characterId: number,
  factionId: number,
): Promise<FactionItemDonationOptions> =>
  (await axios.get<FactionItemDonationOptions>(`${BASE}/${characterId}/factions/${factionId}/donate-items`)).data;

export const donateItemsToFaction = async (
  characterId: number,
  factionId: number,
  items: { item_id: number; quantity: number }[],
  requestId: string,
): Promise<FactionItemDonateResult> =>
  (
    await axios.post<FactionItemDonateResult>(`${BASE}/${characterId}/factions/${factionId}/donate-items`, {
      items,
      request_id: requestId,
    })
  ).data;

/* Admin: access rules (closed locations / dungeons) */

export type FactionAccessKind = 'location' | 'dungeon';

export const FACTION_ACCESS_KIND_LABEL: Record<FactionAccessKind, string> = {
  location: 'Локация',
  dungeon: 'Подземелье',
};

export interface FactionAccessRule {
  faction_id: number;
  faction_name: string | null;
  min_rank_id: number | null;
  min_rank_name: string | null;
}

export interface FactionTerritoryRow {
  kind: FactionAccessKind;
  target_id: number;
  target_name: string | null;
  min_rank: { id: number; name: string } | null;
}

export const adminGetAccessRule = async (kind: FactionAccessKind, targetId: number): Promise<FactionAccessRule | null> =>
  (await axios.get<{ rule: FactionAccessRule | null }>(`${ADMIN}/access/${kind}/${targetId}`)).data.rule;

export const adminPutAccessRule = async (
  kind: FactionAccessKind,
  targetId: number,
  body: { faction_id: number; min_rank_id: number | null },
): Promise<unknown> => (await axios.put(`${ADMIN}/access/${kind}/${targetId}`, body)).data;

export const adminDeleteAccessRule = async (kind: FactionAccessKind, targetId: number): Promise<void> => {
  await axios.delete(`${ADMIN}/access/${kind}/${targetId}`);
};

export const adminFactionTerritory = async (factionId: number): Promise<FactionTerritoryRow[]> =>
  (await axios.get<FactionTerritoryRow[]>(`${ADMIN}/${factionId}/territory`)).data;

/* Admin: enemies (kill points) */

export type FactionEnemyKind = 'mob' | 'npc' | 'hostile';

export const FACTION_ENEMY_KINDS: FactionEnemyKind[] = ['mob', 'npc', 'hostile'];

export const FACTION_ENEMY_KIND_LABEL: Record<FactionEnemyKind, string> = {
  mob: 'Моб',
  npc: 'НПС',
  hostile: 'Участники враждебных фракций',
};

export const FACTION_ENEMIES_MAX = 50;
export const FACTION_ENEMY_POINTS_MAX = 10_000;
export const FACTION_KILL_CAP_MAX = 100_000;

export interface FactionEnemy {
  kind: FactionEnemyKind;
  ref_id: number | null;
  points: number;
  /** GET only: mob template / NPC name. */
  name?: string | null;
}

export interface FactionEnemiesData {
  enemies: FactionEnemy[];
  kill_points_daily_cap: number | null;
}

export const adminFactionEnemies = async (factionId: number): Promise<FactionEnemiesData> =>
  (await axios.get<FactionEnemiesData>(`${ADMIN}/${factionId}/enemies`)).data;

export const adminPutFactionEnemies = async (factionId: number, body: FactionEnemiesData): Promise<FactionEnemiesData> =>
  (await axios.put<FactionEnemiesData>(`${ADMIN}/${factionId}/enemies`, body)).data;

/* Admin: outlaw regions */

export const FACTION_OUTLAW_REGIONS_MAX = 50;

export interface FactionOutlawRegionAdmin {
  region_id: number;
  level_code: string;
  /** GET only. */
  region_name?: string | null;
  level_name?: string | null;
}

export const adminFactionOutlawRegions = async (factionId: number): Promise<{ regions: FactionOutlawRegionAdmin[] }> =>
  (await axios.get<{ regions: FactionOutlawRegionAdmin[] }>(`${ADMIN}/${factionId}/outlaw-regions`)).data;

export const adminPutFactionOutlawRegions = async (
  factionId: number,
  regions: { region_id: number; level_code: string }[],
): Promise<{ regions: FactionOutlawRegionAdmin[] }> =>
  (await axios.put<{ regions: FactionOutlawRegionAdmin[] }>(`${ADMIN}/${factionId}/outlaw-regions`, { regions })).data;

/* Admin: economy item stock */

export interface FactionItemStockRow {
  item_id: number;
  name: string | null;
  quantity: number;
  /** Wholesale price in the HQ region now; null — cannot be sold. */
  unit_value: number | null;
}
