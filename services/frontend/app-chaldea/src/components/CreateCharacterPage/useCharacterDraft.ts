import { useEffect, useRef } from 'react';
import type { StartingPoint } from '../../api/startingPoints';
import type { PersonaForm } from './types';

/**
 * FEAT-154 (task #19, rule 35) — autosave of the «Регистрация Скитальца» draft.
 *
 * ⚠️ **The draft never leaves the browser (risk R9).** It carries the long free
 * text the player wrote, and the feature deliberately stores that text
 * unsanitised (§3.2). The safety of that decision rests on a *rendering*
 * invariant which this module must not break: every restored value is fed back
 * into a controlled `<input>` / `<textarea>` or rendered through
 * `whitespace-pre-wrap` by `CharacterPassport`. **Nothing here is ever passed
 * to `dangerouslySetInnerHTML`, and the draft is never sent anywhere.**
 *
 * The stored blob is untrusted input all the same — anything can put a string
 * under a `localStorage` key — so `parseDraft` rebuilds the shape field by
 * field and coerces every value instead of trusting `JSON.parse`.
 *
 * The key is versioned: an incompatible shape change bumps `DRAFT_VERSION` and
 * older drafts are simply never read again.
 */

const DRAFT_VERSION = 1;
const DRAFT_KEY = `chaldea:character-draft:v${DRAFT_VERSION}`;

/** How long the player may keep typing before a write is flushed. */
const AUTOSAVE_DEBOUNCE_MS = 500;

/** A draft older than this is stale enough that restoring it would confuse. */
const DRAFT_TTL_MS = 30 * 24 * 60 * 60 * 1000; // 30 days

export interface CharacterDraft {
  /** Guards against restoring one player's draft into another player's session. */
  userId: number | null;
  savedAt: number;
  currentIndex: number;
  prologueSeen: boolean;
  selectedRaceId: number;
  selectedSubraceId: number | null;
  selectedOriginId: number | null;
  selectedClassId: number | null;
  selectedClassName: string;
  startLocation: StartingPoint | null;
  persona: PersonaForm;
}

/** Everything the page owns, minus the two fields the hook stamps itself. */
export type DraftSnapshot = Omit<CharacterDraft, 'userId' | 'savedAt'>;

// ── coercion helpers ───────────────────────────────────────────────────────
// Everything read back is treated as `unknown`; a malformed field degrades to
// its empty value instead of throwing and losing the whole draft.

const asString = (value: unknown): string => (typeof value === 'string' ? value : '');

const asStringOrNull = (value: unknown): string | null =>
  typeof value === 'string' ? value : null;

const asNumberOrNull = (value: unknown): number | null =>
  typeof value === 'number' && Number.isFinite(value) ? value : null;

const asNumber = (value: unknown, fallback: number): number =>
  typeof value === 'number' && Number.isFinite(value) ? value : fallback;

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};

const parsePersona = (raw: unknown): PersonaForm => {
  const source = asRecord(raw);
  return {
    biography: asString(source.biography),
    personality: asString(source.personality),
    appearance: asString(source.appearance),
    name: asString(source.name),
    age: asString(source.age),
    height: asString(source.height),
    weight: asString(source.weight),
    sex: asString(source.sex),
    avatarUrl: asStringOrNull(source.avatarUrl),
    skitaltsySinceYear: asNumberOrNull(source.skitaltsySinceYear),
    skitaltsySinceSegment: asNumberOrNull(source.skitaltsySinceSegment),
  };
};

const parseStartLocation = (raw: unknown): StartingPoint | null => {
  const source = asRecord(raw);
  const id = asNumberOrNull(source.id);
  if (id === null) return null;
  return {
    id,
    name: asString(source.name),
    image_url: asStringOrNull(source.image_url),
    starting_blurb: asStringOrNull(source.starting_blurb),
    district_name: asStringOrNull(source.district_name),
    region_name: asStringOrNull(source.region_name),
    country_name: asStringOrNull(source.country_name),
    sort_order: asNumber(source.sort_order, 0),
    // FEAT-155 — a draft only remembers WHICH point was picked; whether it is
    // recommended is re-derived from the origin on the next load.
    is_recommended: false,
  };
};

const parseDraft = (raw: string): CharacterDraft | null => {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  const source = asRecord(parsed);
  if (Object.keys(source).length === 0) return null;
  return {
    userId: asNumberOrNull(source.userId),
    savedAt: asNumber(source.savedAt, 0),
    currentIndex: asNumber(source.currentIndex, 0),
    prologueSeen: source.prologueSeen === true,
    selectedRaceId: asNumber(source.selectedRaceId, 0),
    selectedSubraceId: asNumberOrNull(source.selectedSubraceId),
    selectedOriginId: asNumberOrNull(source.selectedOriginId),
    selectedClassId: asNumberOrNull(source.selectedClassId),
    selectedClassName: asString(source.selectedClassName),
    startLocation: parseStartLocation(source.startLocation),
    persona: parsePersona(source.persona),
  };
};

/** A draft with nothing in it is not worth restoring — or announcing. */
export const isDraftMeaningful = (draft: CharacterDraft): boolean => {
  const { persona } = draft;
  return Boolean(
    persona.name.trim() ||
      persona.appearance.trim() ||
      persona.biography.trim() ||
      persona.personality.trim() ||
      persona.avatarUrl ||
      persona.skitaltsySinceYear !== null ||
      draft.selectedOriginId !== null ||
      draft.selectedClassId !== null ||
      draft.startLocation !== null ||
      draft.currentIndex > 0,
  );
};

/**
 * Reads the stored draft, or `null` when there is none, it belongs to another
 * player, it is past its TTL, or storage is unavailable.
 */
export const readCharacterDraft = (userId: number | null): CharacterDraft | null => {
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(DRAFT_KEY);
  } catch {
    // Private mode / storage disabled — the wizard simply works without a draft.
    return null;
  }
  if (!raw) return null;

  const draft = parseDraft(raw);
  if (!draft) return null;
  if (draft.userId !== null && userId !== null && draft.userId !== userId) return null;
  if (draft.savedAt > 0 && Date.now() - draft.savedAt > DRAFT_TTL_MS) return null;
  return draft;
};

/**
 * Drops the draft. Called on a successful submit — the application is filed,
 * keeping a copy of it in the browser would only re-open a finished form — and
 * from the «Начать заново» control.
 */
export const clearCharacterDraft = (): void => {
  try {
    window.localStorage.removeItem(DRAFT_KEY);
  } catch {
    // A draft we cannot delete is one we could not have written either.
  }
};

/**
 * Debounced autosave. `enabled` stays `false` until the page has had its one
 * chance to restore, so the blank initial state can never overwrite a stored
 * draft on mount.
 */
export const useCharacterDraftAutosave = (
  snapshot: DraftSnapshot,
  userId: number | null,
  enabled: boolean,
): void => {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!enabled) return undefined;

    const timer = setTimeout(() => {
      try {
        const payload: CharacterDraft = { ...snapshot, userId, savedAt: Date.now() };
        window.localStorage.setItem(DRAFT_KEY, JSON.stringify(payload));
      } catch {
        // Quota exceeded or storage disabled. Autosave is a convenience, not a
        // contract — failing to save must never interrupt the application.
      }
    }, AUTOSAVE_DEBOUNCE_MS);
    timerRef.current = timer;

    return () => clearTimeout(timer);
  }, [snapshot, userId, enabled]);
};
