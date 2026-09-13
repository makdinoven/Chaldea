import { useCallback, useEffect, useRef, useState } from 'react';
import { apiErrorMessage } from '../api/errors';
import {
  deleteActiveDraft,
  getActiveDraft,
  saveDraft,
} from '../api/postDrafts';
// FEAT-161: the zone-tolerant parse this hook used to hand-roll now lives in
// one shared place. `serverDateMs` keeps the same contract: 0 when the value is
// absent or unparseable, so the local mirror wins the newer-of-the-two race.
import { serverDateMs } from '../utils/serverDate';

/**
 * FEAT-156 (task T11) — autosave of an RP post draft, per section 3.5 of the
 * feature file.
 *
 * This hook exists because a player lost two hours of writing: a 400 from
 * `move_and_post` wiped the editor. Therefore the single rule that overrides
 * everything else here is **the text must survive**, and the second rule is
 * **typing must never be blocked**. Concretely:
 *
 * - Nothing in this module throws into render. Every network call is
 *   fire-and-forget and catches its own failure; failures become
 *   `saveState: 'error'` + a Russian `error` string, never a rejected promise
 *   reaching the component (CLAUDE.md — Frontend Error Display).
 * - The `localStorage` mirror is written **synchronously on every keystroke**,
 *   before any debouncing. It is the real safety net: it works while the draft
 *   API is down, and it survives a tab close. Every read and write is wrapped
 *   in try/catch — a private window or blocked site data must degrade to
 *   "no local mirror", never to a broken editor.
 * - The server copy is the shared one; on mount the **newer of the two by
 *   timestamp** wins, and if the local copy wins it is pushed up on the next
 *   tick.
 *
 * Content is stored and returned verbatim as the TipTap HTML the editor
 * produces — exactly what `posts.content` already holds. The hook never
 * renders it and never passes it to `dangerouslySetInnerHTML`; it is fed back
 * into the same sanitising editor it came from.
 */

// ── tuning constants (section 3.5 — no magic numbers) ──────────────────────

/** Quiet period after the last keystroke before a save is attempted. */
const AUTOSAVE_DEBOUNCE_MS = 2500;

/**
 * Hard ceiling on how long continuous typing may postpone a save. Without it
 * the trailing-edge debounce would never fire for a fast writer.
 */
const AUTOSAVE_MAX_WAIT_MS = 15000;

/** Mirrors the backend cap (`MAX_DRAFT_LENGTH`) so a doomed 400 is not sent. */
const MAX_DRAFT_LENGTH = 100000;

/** `chaldea:post-draft:{characterId}:{locationId}`. */
const LOCAL_DRAFT_KEY_PREFIX = 'chaldea:post-draft:';

// ── messages (all user-facing text is Russian) ─────────────────────────────

const SAVE_ERROR_FALLBACK = 'Не удалось сохранить черновик.';
const LOAD_ERROR_FALLBACK = 'Не удалось загрузить черновик с сервера.';
const CLEAR_ERROR_FALLBACK = 'Не удалось удалить черновик на сервере.';
const ARCHIVE_ERROR_FALLBACK = 'Не удалось убрать текст в черновики на сервере.';
const TOO_LONG_ERROR = `Черновик слишком длинный — максимум ${MAX_DRAFT_LENGTH} символов.`;

// ── public types ───────────────────────────────────────────────────────────

/**
 * `idle` — nothing to save / nothing saved yet in this session.
 * `saving` — a request is in flight (never blocks the editor).
 * `saved` — the server holds the current text.
 * `error` — the last **save** attempt failed; the text is still safe locally.
 */
export type PostDraftSaveState = 'idle' | 'saving' | 'saved' | 'error';

export interface UsePostDraftResult {
  /** Text restored on mount (newer of server vs local). `''` when there is none. */
  initialContent: string;
  /** True while the restore is in flight. Consumers seed the editor once it flips to false. */
  loading: boolean;
  saveState: PostDraftSaveState;
  /** Epoch ms of the last successful server save, for the «· HH:MM» indicator. */
  lastSavedAt: number | null;
  /**
   * Russian message for the last failure — of a **load** or a **save**. It is
   * deliberately independent of `saveState` (a failed *load* must not read as
   * «Черновик не сохранён»); render it whenever it is non-null.
   */
  error: string | null;
  /** Feed every editor change through this. Mirrors locally, then debounces. */
  scheduleSave: (content: string) => void;
  /** «Очистить черновик» — drops the local mirror and the live server row. */
  clearDraft: () => Promise<void>;
  /**
   * «Очистить поле» / insert-from-history — frees the live slot but keeps the
   * text in the «Черновики» history (section 3.13). Drops the local mirror too,
   * otherwise the retired text would be handed straight back to the editor on
   * the next visit.
   *
   * Never rejects. Resolves to **`true` when the live slot is known to be
   * free** and `false` when the server refused — callers that are about to
   * write something else into that slot (the draft insert) MUST check it, or
   * the new text would overwrite the old row instead of starting a new one.
   * On `false` the local bookkeeping is rolled back, so a failed archive leaves
   * the player exactly where they were.
   */
  archiveDraft: () => Promise<boolean>;
  /**
   * Local-only reset for a live row that is already gone on the server: a post
   * was accepted (`move_and_post` archives it), or the row was deleted by id
   * from the «Черновики» panel. Drops the mirror — without it the
   * newer-of-server-vs-local restore would resurrect a text the player deleted.
   */
  forgetLocalDraft: () => void;
  /** Call after a post was accepted. Alias of `forgetLocalDraft`, kept for readability at the call site. */
  markSent: () => void;
  /** «Повторить» — re-attempt the last failed save. */
  retry: () => void;
}

// ── helpers ────────────────────────────────────────────────────────────────

const localKey = (characterId: number, locationId: number): string =>
  `${LOCAL_DRAFT_KEY_PREFIX}${characterId}:${locationId}`;

/** TipTap emits `<p></p>` for an empty document — strip markup before judging. */
const isContentEmpty = (html: string): boolean =>
  !html
    .replace(/<[^>]*>/g, '')
    .replace(/&nbsp;/g, ' ')
    .trim();

const isUsableId = (value: number | null | undefined): value is number =>
  typeof value === 'number' && Number.isFinite(value) && value > 0;

interface LocalMirror {
  content: string;
  savedAt: number;
}

/**
 * Anything can put a string under a `localStorage` key, so the blob is treated
 * as untrusted: the shape is rebuilt field by field instead of trusting
 * `JSON.parse`, and any failure degrades to "no mirror".
 */
const readLocalMirror = (key: string): LocalMirror | null => {
  let raw: string | null = null;
  try {
    raw = window.localStorage.getItem(key);
  } catch {
    // Private window / site data blocked — the hook works without a mirror.
    return null;
  }
  if (!raw) return null;

  try {
    const parsed: unknown = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null;
    const source = parsed as Record<string, unknown>;
    const content = typeof source.content === 'string' ? source.content : '';
    const savedAt =
      typeof source.savedAt === 'number' && Number.isFinite(source.savedAt)
        ? source.savedAt
        : 0;
    if (!content) return null;
    return { content, savedAt };
  } catch {
    return null;
  }
};

const writeLocalMirror = (key: string, content: string): void => {
  try {
    const payload: LocalMirror = { content, savedAt: Date.now() };
    window.localStorage.setItem(key, JSON.stringify(payload));
  } catch {
    // Quota exceeded or storage disabled. The mirror is a safety net, not a
    // contract — failing to write it must never interrupt the writer.
  }
};

const removeLocalMirror = (key: string): void => {
  try {
    window.localStorage.removeItem(key);
  } catch {
    // A mirror we cannot delete is one we could not have written either.
  }
};

// ── the hook ───────────────────────────────────────────────────────────────

/**
 * @param characterId the player's active character; a missing id disables the hook
 * @param locationId  the location whose draft slot is being edited
 * @param enabled     `false` disables everything (NPC mode — see section 3.2)
 */
export const usePostDraft = (
  characterId: number | null | undefined,
  locationId: number | null | undefined,
  enabled: boolean = true,
): UsePostDraftResult => {
  const active = enabled && isUsableId(characterId) && isUsableId(locationId);

  const [initialContent, setInitialContent] = useState('');
  const [loading, setLoading] = useState(active);
  const [saveState, setSaveState] = useState<PostDraftSaveState>('idle');
  const [lastSavedAt, setLastSavedAt] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  /** Latest content handed to `scheduleSave`. */
  const pendingRef = useRef('');
  /** Content the server is known to hold — the skip-if-unchanged baseline. */
  const lastSavedRef = useRef('');
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const maxWaitTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** Out-of-order responses must not move `lastSavedRef` backwards. */
  const saveSeqRef = useRef(0);
  const mountedRef = useRef(true);

  /**
   * Current props, readable from stable callbacks. `scheduleSave` keeps a
   * `[]` dependency list on purpose — it is called from the editor's
   * `onUpdate` on every keystroke, and a changing identity there would churn
   * the consumer's effects.
   */
  const ctxRef = useRef({ characterId, locationId, active });
  ctxRef.current = { characterId, locationId, active };

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  const cancelTimers = useCallback(() => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = null;
    }
    if (maxWaitTimerRef.current) {
      clearTimeout(maxWaitTimerRef.current);
      maxWaitTimerRef.current = null;
    }
  }, []);

  /** True when a request would be pointless (unchanged, or empty→empty). */
  const shouldSkip = useCallback((content: string): boolean => {
    if (content === lastSavedRef.current) return true;
    return isContentEmpty(content) && isContentEmpty(lastSavedRef.current);
  }, []);

  /**
   * The one place that talks to D4. Always fire-and-forget: it resolves even
   * when the request failed, so no caller can produce an unhandled rejection.
   */
  const persist = useCallback(
    async (charId: number, locId: number, content: string): Promise<void> => {
      /** State belongs to the pair currently mounted, not to a stale one. */
      const isCurrent = (): boolean =>
        mountedRef.current &&
        ctxRef.current.characterId === charId &&
        ctxRef.current.locationId === locId;

      if (content.length > MAX_DRAFT_LENGTH) {
        // The server would answer 400; the local mirror already holds the text.
        if (isCurrent()) {
          setSaveState('error');
          setError(TOO_LONG_ERROR);
        }
        return;
      }

      const seq = (saveSeqRef.current += 1);
      if (isCurrent()) setSaveState('saving');

      try {
        await saveDraft(locId, { character_id: charId, content });
        if (seq !== saveSeqRef.current) return; // a newer save superseded this one
        if (!isCurrent()) return;
        lastSavedRef.current = content;
        setLastSavedAt(Date.now());
        setSaveState('saved');
        setError(null);
      } catch (err) {
        if (seq !== saveSeqRef.current) return;
        if (!isCurrent()) return;
        // `lastSavedRef` is deliberately NOT advanced: the next tick (or
        // `retry()`) will try the same text again. The mirror already has it.
        setSaveState('error');
        setError(apiErrorMessage(err, SAVE_ERROR_FALLBACK));
      }
    },
    [],
  );

  /** Runs the pending save now, cancelling both timers. */
  const flush = useCallback(
    (charId: number, locId: number, force: boolean = false) => {
      cancelTimers();
      const content = pendingRef.current;
      if (!force && shouldSkip(content)) return;
      void persist(charId, locId, content);
    },
    [cancelTimers, persist, shouldSkip],
  );

  const scheduleSave = useCallback(
    (content: string) => {
      pendingRef.current = content;

      const { characterId: charId, locationId: locId, active: isActive } = ctxRef.current;

      // The synchronous mirror comes first and happens even while a restore is
      // still in flight — it is the part that must not depend on the network.
      if (isUsableId(charId) && isUsableId(locId)) {
        if (isContentEmpty(content)) {
          removeLocalMirror(localKey(charId, locId));
        } else {
          writeLocalMirror(localKey(charId, locId), content);
        }
      }

      if (!isActive || !isUsableId(charId) || !isUsableId(locId)) return;

      if (shouldSkip(content)) {
        // Typed back to what the server already has — drop the pending save.
        cancelTimers();
        return;
      }

      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
      debounceTimerRef.current = setTimeout(() => {
        debounceTimerRef.current = null;
        flush(charId, locId);
      }, AUTOSAVE_DEBOUNCE_MS);

      // Started only once per burst, so continuous typing still gets a save
      // every AUTOSAVE_MAX_WAIT_MS instead of never.
      if (!maxWaitTimerRef.current) {
        maxWaitTimerRef.current = setTimeout(() => {
          maxWaitTimerRef.current = null;
          flush(charId, locId);
        }, AUTOSAVE_MAX_WAIT_MS);
      }
    },
    [cancelTimers, flush, shouldSkip],
  );

  // ── restore on mount / on (character, location) change ───────────────────
  useEffect(() => {
    cancelTimers();
    pendingRef.current = '';
    lastSavedRef.current = '';
    setLastSavedAt(null);
    setError(null);
    setSaveState('idle');

    if (!active || !isUsableId(characterId) || !isUsableId(locationId)) {
      setInitialContent('');
      setLoading(false);
      return undefined;
    }

    const charId = characterId;
    const locId = locationId;
    const key = localKey(charId, locId);
    let cancelled = false;

    setLoading(true);
    setInitialContent('');

    const restore = async () => {
      const local = readLocalMirror(key);
      let serverContent = '';
      let serverAt = 0;
      let loadFailed = false;

      try {
        const draft = await getActiveDraft(locId, charId);
        if (draft && typeof draft.content === 'string') {
          serverContent = draft.content;
          serverAt = serverDateMs(draft.updated_at);
        }
      } catch (err) {
        // The draft API being down must not stop the player from writing —
        // fall back to the local mirror and surface the reason.
        loadFailed = true;
        if (!cancelled && mountedRef.current) {
          setError(apiErrorMessage(err, LOAD_ERROR_FALLBACK));
        }
      }

      if (cancelled || !mountedRef.current) return;

      // The server copy is the baseline for skip-if-unchanged — but only when
      // it was actually read. After a failed load nothing is known to be
      // persisted, so the first tick re-uploads whatever the player has.
      lastSavedRef.current = loadFailed ? '' : serverContent;

      const localWins =
        !!local && !isContentEmpty(local.content) && local.savedAt > serverAt;
      const restored = localWins ? local.content : serverContent;

      pendingRef.current = restored;
      setInitialContent(restored);
      setLoading(false);

      if (!loadFailed && serverContent && !localWins) {
        setLastSavedAt(serverAt || null);
        setSaveState('saved');
      }

      // The local copy was newer (or the server never saw it) — push it up.
      if (restored && restored !== lastSavedRef.current) {
        scheduleSave(restored);
      }
    };

    void restore();

    const handleVisibility = () => {
      // A tab going away is the last safe moment to reach the network;
      // `sendBeacon` cannot carry the Authorization header the gateway wants.
      if (document.visibilityState === 'hidden') flush(charId, locId);
    };
    document.addEventListener('visibilitychange', handleVisibility);

    return () => {
      cancelled = true;
      document.removeEventListener('visibilitychange', handleVisibility);
      // Unmount / location change: flush whatever is pending for the pair we
      // are leaving. `persist` swallows its own errors, so this cannot produce
      // an unhandled rejection after the component is gone, and its state
      // updates are dropped by the `isCurrent()` guard.
      flush(charId, locId);
    };
  }, [characterId, locationId, active, cancelTimers, flush, scheduleSave]);

  // ── imperative API ───────────────────────────────────────────────────────

  const clearDraft = useCallback(async (): Promise<void> => {
    const { characterId: charId, locationId: locId } = ctxRef.current;
    cancelTimers();
    saveSeqRef.current += 1; // invalidate anything in flight
    pendingRef.current = '';
    lastSavedRef.current = '';

    if (isUsableId(charId) && isUsableId(locId)) {
      removeLocalMirror(localKey(charId, locId));
    }

    if (mountedRef.current) {
      setLastSavedAt(null);
      setSaveState('idle');
      setError(null);
    }

    if (!isUsableId(charId) || !isUsableId(locId)) return;

    try {
      await deleteActiveDraft(locId, charId);
    } catch (err) {
      // The local copy is already gone, so the text is not coming back either
      // way — but the player must still be told the server did not confirm.
      if (mountedRef.current) {
        setError(apiErrorMessage(err, CLEAR_ERROR_FALLBACK));
      }
    }
  }, [cancelTimers]);

  /**
   * «Очистить поле», and the preamble of an insert from «Черновики». Same local
   * bookkeeping as `forgetLocalDraft` — the mirror in particular **must** go, or
   * the newer-of-server-vs-local restore would resurrect the retired text and
   * undo the whole point of the change (section 3.13, condition 2). Cancelling
   * the timers and bumping `saveSeqRef` first also keeps a trailing debounced
   * save from hard-deleting the row we are about to retire.
   *
   * Returns whether the live slot is now genuinely free. On failure the server
   * still holds the untouched live row, so the local bookkeeping is put back
   * exactly as it was: nothing is lost, and the caller can abort whatever it
   * was going to write into that slot.
   */
  const archiveDraft = useCallback(async (): Promise<boolean> => {
    const { characterId: charId, locationId: locId } = ctxRef.current;
    const previousPending = pendingRef.current;
    const previousSaved = lastSavedRef.current;

    cancelTimers();
    saveSeqRef.current += 1; // invalidate anything in flight
    pendingRef.current = '';
    lastSavedRef.current = '';

    if (isUsableId(charId) && isUsableId(locId)) {
      removeLocalMirror(localKey(charId, locId));
    }

    if (mountedRef.current) {
      setLastSavedAt(null);
      setSaveState('idle');
      setError(null);
    }

    // No usable pair means there is no live slot on the server at all — it is
    // free by definition, and the caller may proceed.
    if (!isUsableId(charId) || !isUsableId(locId)) return true;

    try {
      await deleteActiveDraft(locId, charId, true);
      return true;
    } catch (err) {
      // The row is untouched on the server, so roll the local state back to
      // match it — including the mirror, which still describes real content.
      pendingRef.current = previousPending;
      lastSavedRef.current = previousSaved;
      if (previousPending && !isContentEmpty(previousPending)) {
        writeLocalMirror(localKey(charId, locId), previousPending);
      }
      if (mountedRef.current) {
        setError(apiErrorMessage(err, ARCHIVE_ERROR_FALLBACK));
      }
      return false;
    }
  }, [cancelTimers]);

  const forgetLocalDraft = useCallback(() => {
    // The live row is already gone server-side — `move_and_post` archives it
    // (section 3.3), or the panel deleted it by id (D6). Only local
    // bookkeeping is left to reset; the mirror above all, or a deleted text
    // would come back on the next visit.
    const { characterId: charId, locationId: locId } = ctxRef.current;
    cancelTimers();
    saveSeqRef.current += 1;
    pendingRef.current = '';
    lastSavedRef.current = '';
    if (isUsableId(charId) && isUsableId(locId)) {
      removeLocalMirror(localKey(charId, locId));
    }
    if (mountedRef.current) {
      setLastSavedAt(null);
      setSaveState('idle');
      setError(null);
    }
  }, [cancelTimers]);

  /** Same operation, named for the send path. */
  const markSent = forgetLocalDraft;

  const retry = useCallback(() => {
    const { characterId: charId, locationId: locId, active: isActive } = ctxRef.current;
    if (!isActive || !isUsableId(charId) || !isUsableId(locId)) return;
    setError(null);
    flush(charId, locId, true);
  }, [flush]);

  return {
    initialContent,
    loading,
    saveState,
    lastSavedAt,
    error,
    scheduleSave,
    clearDraft,
    archiveDraft,
    forgetLocalDraft,
    markSent,
    retry,
  };
};

export default usePostDraft;
