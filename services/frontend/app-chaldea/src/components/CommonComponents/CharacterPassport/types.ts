/**
 * FEAT-154 — `CharacterPassport` contract (rules 25-27, §3.7).
 *
 * ONE component, FOUR call sites: the wizard's «Контракт» step, the character
 * profile page, the compact card in `/characters/list`, and the moderator's
 * request screen. The data for those four comes from four different endpoints,
 * so nothing here is required except `name` — the component renders «—» for
 * whatever it lacks and never fabricates a value.
 *
 * Free text (`appearance` / `biography` / `personality` / `background`) is
 * written by players and is ALWAYS rendered through `whitespace-pre-wrap`.
 * `dangerouslySetInnerHTML` must never appear in this folder (R9).
 */

import type { ItemBulk, SkillBulk } from '../../../api/bulk';
import type { OriginCountry } from '../../../api/origins';
import type { StarterKitResolvedFrom } from '../../../api/starterKits';

/** `full` = the two-page spread. `compact` = the grid card (no free text, no kit). */
/**
 * Who the sheet is drawn for. `'public'` hides the recruitment record (issued
 * kit, first posting); `'self'` shows it. See `CharacterPassport`'s `audience`.
 */
export type PassportAudience = 'self' | 'public';

export type PassportVariant = 'full' | 'compact';

/** Request lifecycle, shown only on the moderator / «мои заявки» call sites. */
export type PassportStatus = 'pending' | 'approved' | 'rejected';

/**
 * The ten preset stats. Kept as an open record (per §3.7) so a source that
 * carries extra keys does not have to be trimmed before it is passed in.
 */
export type PassportStats = Record<string, number>;

/** Preset keys in display order. A stat outside this list is not rendered. */
export const PASSPORT_STAT_ORDER = [
  'strength',
  'agility',
  'intelligence',
  'endurance',
  'health',
  'mana',
  'energy',
  'stamina',
  'charisma',
  'luck',
] as const;

/**
 * Values computed from the preset by `computeDerivedStats` (rule 6).
 * Mirrors `character-attributes-service/app/crud.py::compute_derived_stats`.
 */
export interface DerivedStats {
  maxHealth: number;
  maxMana: number;
  maxEnergy: number;
  maxStamina: number;
  dodge: number;
  criticalHitChance: number;
  criticalDamage: number;
  initiative: number;
}

/** One kit line, already resolved against `GET /inventory/items/bulk`. */
export interface ResolvedItem {
  id: number;
  name: string;
  quantity: number;
  imageUrl?: string | null;
  rarity?: string | null;
}

/** One kit skill, already resolved against `GET /skills/bulk`. */
export interface ResolvedSkill {
  id: number;
  name: string;
  iconUrl?: string | null;
}

/**
 * The kit **issued to this character**.
 *
 * For an existing character this is the FROZEN `characters.granted_kit`
 * snapshot (rule 12d / D17) — a later admin edit of the starter kit must never
 * rewrite it. Only the wizard adapter feeds the live `/starter-kits/resolve`
 * preview, because at that point nothing has been granted yet.
 * Names, icons and rarity are always resolved live from the frozen ids (D19).
 */
export interface PassportKit {
  items: ResolvedItem[];
  skills: ResolvedSkill[];
  currency: number;
  /** How the resolver arrived at the kit (N10). Informational only. */
  resolvedFrom?: StarterKitResolvedFrom | null;
}

/** Country of origin as printed on the passport (rules 8-10). */
export interface PassportOrigin {
  name: string;
  emblemUrl?: string | null;
  /** Slug of the Archive article, if the origin has one — renders as a link. */
  archiveSlug?: string | null;
}

/** In-world «в Скитальцах с» (rule 22, §3.5). Never a real-world date. */
export interface PassportTenure {
  year: number;
  /** Index 0..7 into `YEAR_SEGMENTS`. Omitted = the year alone. */
  segment?: number | null;
}

/**
 * Everything the passport can print. **`name` is the only required field.**
 */
export interface PassportData {
  name: string;

  /** `null` while the character does not exist yet → «будет присвоен» (D11). */
  characterId?: number | null;
  avatarUrl?: string | null;
  /** Rendered as «УР» — the in-world name for the character level. */
  level?: number | null;

  raceName?: string | null;
  subraceName?: string | null;
  subraceImage?: string | null;
  className?: string | null;

  origin?: PassportOrigin | null;
  /** `false` → «редкий выбор» badge (rule 11). `null` = unknown, no badge. */
  originIsTypical?: boolean | null;

  stats?: PassportStats | null;
  derived?: DerivedStats | null;

  starterKit?: PassportKit | null;
  /**
   * `true` = frozen record of what was actually issued.
   * `false` = reconstructed for a pre-feature character (D18) — the passport
   * says so in a muted caption rather than passing it off as the original.
   * `null` / omitted = nothing granted yet (the wizard preview).
   */
  starterKitIsSnapshot?: boolean | null;

  startLocation?: { id: number; name: string } | null;

  /** System registration date (ISO). Set at approval, never player-supplied. */
  registeredAt?: string | null;
  skitaltsySince?: PassportTenure | null;

  sex?: string | null;
  age?: number | null;
  height?: string | null;
  weight?: string | null;

  appearance?: string | null;
  biography?: string | null;
  personality?: string | null;
  background?: string | null;

  /** Moderator / «мои заявки» only. */
  status?: PassportStatus | null;
  rejectionReason?: string | null;

  /** `GET /characters/{id}/public` also serves NPCs (N13). */
  isNpc?: boolean | null;
}

// ── Adapter inputs ──────────────────────────────────────────────────────────

/**
 * Side data the character endpoints do NOT carry, supplied by the call site.
 * Every field is optional — an adapter called with no extras still produces a
 * renderable passport, it just prints fewer rows.
 */
export interface PassportExtras {
  /** Origin registry (`GET /locations/origins`) used to resolve `origin_id`. */
  origins?: readonly OriginCountry[] | ReadonlyMap<number, OriginCountry> | null;
  /** `typical_origin_ids` of the character's subrace → drives the rare badge. */
  typicalOriginIds?: readonly number[] | null;
  /** Stats live in character-attributes-service, not on the character row. */
  stats?: PassportStats | null;
  /** Results of `GET /inventory/items/bulk` for the kit's frozen item ids. */
  items?: readonly ItemBulk[] | ReadonlyMap<number, ItemBulk> | null;
  /** Results of `GET /skills/bulk` for the kit's frozen skill ids. */
  skills?: readonly SkillBulk[] | ReadonlyMap<number, SkillBulk> | null;
  /** Name of `current_location_id` / `start_location_id`, resolved by the caller. */
  startLocationName?: string | null;
}

/**
 * What the wizard hands to `fromWizardDraft`. Deliberately shaped around what
 * the steps already hold (the selected entities, not raw ids), so step 5 does
 * not have to re-fetch anything it has already loaded.
 */
export interface PassportWizardDraft {
  name: string;
  avatarUrl?: string | null;

  race?: { id: number; name: string } | null;
  subrace?: {
    id: number;
    name: string;
    image?: string | null;
    /** From the subrace record — used for the «редкий выбор» badge (rule 11). */
    typicalOriginIds?: readonly number[] | null;
  } | null;
  gameClass?: { id: number; name: string } | null;

  /** The whole origin card, as picked on the «Родина» step. */
  origin?: OriginCountry | null;

  /** The subrace stat preset (always 100 points, rule 5). */
  stats?: PassportStats | null;

  /**
   * The LIVE `/starter-kits/resolve` preview for (class × origin) — the only
   * place a resolver result is allowed into the passport, because nothing has
   * been granted yet (rule 12d).
   */
  kitPreview?: PassportKit | null;

  startLocation?: { id: number; name: string } | null;

  skitaltsySinceYear?: number | null;
  skitaltsySinceSegment?: number | null;

  sex?: string | null;
  age?: number | string | null;
  height?: string | null;
  weight?: string | null;
  appearance?: string | null;
  biography?: string | null;
  personality?: string | null;
  background?: string | null;
}

/**
 * Structural shape of a request row on the moderator screen and on «мои
 * заявки». `MyCharacterRequest` satisfies it; so does the moderator's own
 * `RequestData` once it carries the FEAT-154 keys. Kept structural on purpose
 * so tasks #21 and #22 do not have to agree on one concrete interface.
 */
export interface PassportModerationRequest {
  id?: number | null;
  request_id?: number | null;
  status?: string | null;
  rejection_reason?: string | null;
  character_id?: number | null;

  name?: string | null;
  avatar?: string | null;
  race_name?: string | null;
  subrace_name?: string | null;
  class_name?: string | null;

  origin_id?: number | null;
  start_location_id?: number | null;

  sex?: string | null;
  age?: number | null;
  height?: string | null;
  weight?: string | null;

  appearance?: string | null;
  biography?: string | null;
  personality?: string | null;
  background?: string | null;

  skitaltsy_since_year?: number | null;
  skitaltsy_since_segment?: number | null;
  created_at?: string | null;
}
