/**
 * FEAT-154 — the four adapters of §3.7.
 *
 * Each turns one of the four data sources into `PassportData`. They are pure
 * functions: no requests, no store access, no side effects. Whatever the source
 * cannot supply is left `undefined`, and the component prints «—».
 *
 * ⚠️ **Kit rule (12d / D17).** `fromCharacterPublic` reads the FROZEN
 * `granted_kit` snapshot and never calls the resolver. `fromWizardDraft` is the
 * only adapter fed by `/starter-kits/resolve`, because at that moment nothing
 * has been granted. Item and skill *names / icons* are always resolved live
 * from the frozen ids (D19) and arrive through `PassportExtras`.
 */

import type { ItemBulk, SkillBulk } from '../../../api/bulk';
import type { CharacterListItem, CharacterPublic, GrantedKit } from '../../../api/charactersPublic';
import type { OriginCountry } from '../../../api/origins';
import { computeDerivedStats } from './derived';
import type {
  PassportData,
  PassportExtras,
  PassportKit,
  PassportModerationRequest,
  PassportOrigin,
  PassportStatus,
  PassportStats,
  PassportTenure,
  PassportWizardDraft,
  ResolvedItem,
  ResolvedSkill,
} from './types';

// ── helpers ─────────────────────────────────────────────────────────────────

const toMap = <T extends { id: number }>(
  source: readonly T[] | ReadonlyMap<number, T> | null | undefined,
): ReadonlyMap<number, T> => {
  if (!source) return new Map<number, T>();
  if (source instanceof Map) return source;
  return new Map((source as readonly T[]).map((row) => [row.id, row]));
};

/** Trims and collapses empty strings to `undefined` so «—» is printed. */
const text = (value: string | null | undefined): string | undefined => {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
};

const toNumber = (value: number | string | null | undefined): number | undefined => {
  if (value === null || value === undefined || value === '') return undefined;
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
};

const toStatus = (value: string | null | undefined): PassportStatus | undefined =>
  value === 'pending' || value === 'approved' || value === 'rejected' ? value : undefined;

const toPassportOrigin = (origin: OriginCountry | null | undefined): PassportOrigin | undefined =>
  origin
    ? {
        name: origin.name,
        emblemUrl: origin.emblem_url,
        archiveSlug: origin.archive_slug,
      }
    : undefined;

const resolveOrigin = (
  originId: number | null | undefined,
  extras: PassportExtras | undefined,
): OriginCountry | undefined => {
  if (!originId) return undefined;
  return toMap(extras?.origins).get(originId);
};

/**
 * Rule 11 — a country outside the subrace's `typical_origin_ids` is a «редкий
 * выбор». Returns `undefined` (no badge) when the caller did not supply the
 * list: unknown must not look like "rare".
 */
const resolveOriginIsTypical = (
  originId: number | null | undefined,
  typicalOriginIds: readonly number[] | null | undefined,
): boolean | undefined => {
  if (!originId || !typicalOriginIds || typicalOriginIds.length === 0) return undefined;
  return typicalOriginIds.includes(originId);
};

const toTenure = (
  year: number | null | undefined,
  segment: number | null | undefined,
): PassportTenure | undefined =>
  typeof year === 'number' && Number.isFinite(year)
    ? { year, segment: typeof segment === 'number' ? segment : null }
    : undefined;

const toStats = (stats: PassportStats | null | undefined): PassportStats | undefined =>
  stats && Object.keys(stats).length > 0 ? stats : undefined;

/**
 * Turns the id-only kit record into printable lines by joining it against the
 * bulk lookups. An id the backend no longer knows still renders — as
 * «Предмет #{id}» — so a deleted item cannot blank out a historical record.
 */
const buildKit = (
  source:
    | {
        items?: { item_id: number; quantity: number }[] | null;
        skills?: { skill_id: number }[] | null;
        currency_amount?: number | null;
        resolved_from?: PassportKit['resolvedFrom'];
      }
    | null
    | undefined,
  extras: PassportExtras | undefined,
): PassportKit | undefined => {
  if (!source) return undefined;

  const itemsById = toMap<ItemBulk>(extras?.items);
  const skillsById = toMap<SkillBulk>(extras?.skills);

  const items: ResolvedItem[] = (source.items ?? []).map((line) => {
    const resolved = itemsById.get(line.item_id);
    return {
      id: line.item_id,
      name: resolved?.name ?? `Предмет #${line.item_id}`,
      quantity: line.quantity,
      imageUrl: resolved?.image_url ?? null,
      rarity: resolved?.rarity ?? null,
    };
  });

  const skills: ResolvedSkill[] = (source.skills ?? []).map((line) => {
    const resolved = skillsById.get(line.skill_id);
    return {
      id: line.skill_id,
      name: resolved?.name ?? `Навык #${line.skill_id}`,
      iconUrl: resolved?.icon_url ?? null,
    };
  });

  return {
    items,
    skills,
    currency: source.currency_amount ?? 0,
    resolvedFrom: source.resolved_from ?? null,
  };
};

// ── 1. Wizard step «Контракт» ───────────────────────────────────────────────

/**
 * The passport as it is previewed inside the creation wizard. Nothing has been
 * approved yet, so there is no character id (→ «Мегалинк будет присвоен»), no
 * registration date, and the kit is the LIVE resolver preview.
 */
export const fromWizardDraft = (draft: PassportWizardDraft): PassportData => ({
  name: draft.name,
  characterId: null,
  avatarUrl: draft.avatarUrl ?? null,
  // A brand-new Скиталец always starts at УР 1 (rule 24) — not a guess, a rule.
  level: 1,

  raceName: text(draft.race?.name),
  subraceName: text(draft.subrace?.name),
  subraceImage: draft.subrace?.image ?? null,
  className: text(draft.gameClass?.name),

  origin: toPassportOrigin(draft.origin),
  originIsTypical: resolveOriginIsTypical(draft.origin?.id, draft.subrace?.typicalOriginIds),

  stats: toStats(draft.stats),
  // Nothing has been assessed yet — no record, no reconstruction caption.
  statsIsSnapshot: null,
  derived: draft.stats ? computeDerivedStats(draft.stats) : undefined,

  starterKit: draft.kitPreview ?? undefined,
  // `null` = nothing granted yet, so the kit block reads «будет выдан».
  starterKitIsSnapshot: null,

  startLocation: draft.startLocation ?? undefined,

  registeredAt: null,
  skitaltsySince: toTenure(draft.skitaltsySinceYear, draft.skitaltsySinceSegment),

  sex: draft.sex ?? undefined,
  age: toNumber(draft.age),
  height: text(draft.height),
  weight: text(draft.weight),

  appearance: text(draft.appearance),
  biography: text(draft.biography),
  personality: text(draft.personality),
  background: text(draft.background),
});

// ── 2. Character profile page / list detail modal ───────────────────────────

/**
 * `GET /characters/{id}/public`. The kit comes from the frozen snapshot on the
 * character row — the resolver is never consulted here (rule 12d), so editing
 * a starter kit in the admin cannot rewrite an existing passport.
 *
 * The stat block reads `starting_attributes` off the same row for the same
 * reason (FEAT-155): it is the assessment made at recruitment, not the
 * character's current build. `extras.stats` is deliberately ignored here so no
 * call site can push a live build into a public passport.
 */
export const fromCharacterPublic = (
  character: CharacterPublic,
  extras?: PassportExtras,
): PassportData => {
  const origin = resolveOrigin(character.origin_id, extras);
  const grantedKit: GrantedKit | null = character.granted_kit;
  const startingStats = toStats(character.starting_attributes);

  return {
    name: character.name,
    characterId: character.id,
    avatarUrl: character.avatar,
    level: character.level,

    raceName: text(character.race_name),
    subraceName: text(character.subrace_name),
    subraceImage: character.subrace_image,
    className: text(character.class_name),

    origin: toPassportOrigin(origin),
    originIsTypical: resolveOriginIsTypical(character.origin_id, extras?.typicalOriginIds),

    stats: startingStats,
    // `false` = reconstructed from the subrace preset (pre-FEAT-155 character).
    statsIsSnapshot: startingStats ? character.starting_attributes_is_snapshot : null,
    derived: startingStats ? computeDerivedStats(startingStats) : undefined,

    starterKit: buildKit(grantedKit, extras),
    // `false` = reconstructed for a pre-feature character (D18).
    starterKitIsSnapshot: grantedKit ? character.granted_kit_is_snapshot : null,

    startLocation:
      character.current_location_id && extras?.startLocationName
        ? { id: character.current_location_id, name: extras.startLocationName }
        : undefined,

    registeredAt: character.registered_at,
    skitaltsySince: toTenure(
      character.skitaltsy_since_year,
      character.skitaltsy_since_segment,
    ),

    sex: character.sex,
    age: toNumber(character.age),
    height: text(character.height),
    weight: text(character.weight),

    appearance: text(character.appearance),
    biography: text(character.biography),
    personality: text(character.personality),
    background: text(character.background),

    isNpc: character.is_npc,
  };
};

// ── 3. Compact card in `/characters/list` ───────────────────────────────────

/**
 * One row of `GET /characters/list`. The row carries no kit, which is fine:
 * `variant='compact'` does not print one, so the grid renders with **zero**
 * per-card requests (rule 26).
 */
export const fromCharacterListItem = (
  row: CharacterListItem,
  extras?: PassportExtras,
): PassportData => {
  const origin = resolveOrigin(row.origin_id, extras);

  return {
    name: row.name,
    characterId: row.id,
    avatarUrl: row.avatar,
    level: row.level,

    raceName: text(row.race_name),
    subraceName: text(row.subrace_name),
    subraceImage: row.subrace_image,
    className: text(row.class_name),

    origin: toPassportOrigin(origin),
    originIsTypical: resolveOriginIsTypical(row.origin_id, extras?.typicalOriginIds),

    stats: toStats(extras?.stats),
    statsIsSnapshot: null,
    derived: extras?.stats ? computeDerivedStats(extras.stats) : undefined,

    // The list row has no `granted_kit`; the detail modal fetches the full
    // character and re-renders through `fromCharacterPublic`.
    starterKit: undefined,
    starterKitIsSnapshot: null,

    startLocation:
      row.current_location_id && extras?.startLocationName
        ? { id: row.current_location_id, name: extras.startLocationName }
        : undefined,

    registeredAt: row.registered_at,
    skitaltsySince: toTenure(row.skitaltsy_since_year, row.skitaltsy_since_segment),

    sex: row.sex,
    age: toNumber(row.age),
    height: text(row.height),
    weight: text(row.weight),

    appearance: text(row.appearance),
    biography: text(row.biography),
    personality: text(row.personality),
    background: text(row.background),

    isNpc: row.is_npc,
  };
};

// ── 4. Moderator screen / «мои заявки» ──────────────────────────────────────

/**
 * A pending, approved or rejected request. There is no character yet (unless
 * the request has already been approved), so the Megalink line usually reads
 * «будет присвоен при регистрации», and the status badge plus the rejection
 * reason (rule 28) are printed on the passport itself.
 *
 * A request stores no `granted_kit` either — the kit is decided at approval —
 * so the moderator sees the profile, not a promise of loot.
 */
export const fromModerationRequest = (
  request: PassportModerationRequest,
  extras?: PassportExtras,
): PassportData => {
  const origin = resolveOrigin(request.origin_id, extras);

  return {
    name: text(request.name) ?? 'Без имени',
    characterId: request.character_id ?? null,
    avatarUrl: request.avatar ?? null,
    level: 1,

    raceName: text(request.race_name),
    subraceName: text(request.subrace_name),
    className: text(request.class_name),

    origin: toPassportOrigin(origin),
    originIsTypical: resolveOriginIsTypical(request.origin_id, extras?.typicalOriginIds),

    stats: toStats(extras?.stats),
    statsIsSnapshot: null,
    derived: extras?.stats ? computeDerivedStats(extras.stats) : undefined,

    starterKit: undefined,
    starterKitIsSnapshot: null,

    startLocation:
      request.start_location_id && extras?.startLocationName
        ? { id: request.start_location_id, name: extras.startLocationName }
        : undefined,

    registeredAt: null,
    skitaltsySince: toTenure(
      request.skitaltsy_since_year,
      request.skitaltsy_since_segment,
    ),

    sex: request.sex ?? undefined,
    age: toNumber(request.age),
    height: text(request.height),
    weight: text(request.weight),

    appearance: text(request.appearance),
    biography: text(request.biography),
    personality: text(request.personality),
    background: text(request.background),

    status: toStatus(request.status),
    rejectionReason: text(request.rejection_reason),
  };
};
