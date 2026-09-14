import { useCallback, useEffect, useMemo, useState } from 'react';
import { motion } from 'motion/react';
import axios from 'axios';
import { diffWords, type ChangeObject } from 'diff';
import { BASE_URL } from '../../../api/api';
import { formatServerDateTime } from '../../../utils/serverDate';
import { htmlToPlainText, isFormattingOnlyChange } from '../../../utils/postText';
import type { PostVersionEntry, PostVersionHistory } from './types';

/**
 * FEAT-160 (T8): what a post used to say, and who changed it.
 *
 * ## Why a word diff of the TEXT and not of the HTML
 *
 * Architecture decision 3.1. The dispute this modal settles is «ты написал не
 * так» — a dispute about *what a character said*. A character diff of TipTap
 * HTML answers a different question badly: wrapping one word in `<em>` rewrites
 * the surrounding string and the whole passage comes back red-and-green.
 *
 * A text-only diff has the opposite failure — an edit that only recolours a
 * word would render as an empty diff and read as «ничего не менялось», which is
 * untrue. So the modal shows three things, in this order of prominence:
 *
 * 1. the word diff of the plain text (the headline);
 * 2. when the plain text is identical but the HTML is not — a banner saying so
 *    in words, instead of a blank panel;
 * 3. an always-available collapsed panel with the word diff of the **raw HTML,
 *    rendered as escaped source text**.
 *
 * ## Why nothing here renders post HTML
 *
 * Every run of the diff is inserted as a React text node, and the markup panel
 * is the same thing in a `whitespace-pre-wrap` monospace box — React escapes it,
 * so a tag reads as a tag. There is deliberately **no `dangerouslySetInnerHTML`
 * in this file**, and therefore no new sanitiser call site: the project's single
 * post policy (`utils/sanitizePostHtml.ts`) stays limited to the two surfaces
 * that genuinely must render markup. Merged diff output — trusted diff markup
 * spliced into untrusted player markup — is exactly the mixture an allow-list
 * sanitiser reasons about worst, which is also why HTML-tree diff libraries were
 * rejected in 3.1.
 *
 * ## Self-contained on purpose
 *
 * It takes a `postId` and fetches its own data, because it is opened from two
 * unrelated places: the post kebab in the location feed (T8) and the moderation
 * queue (T9). Neither has the history loaded, and neither should have to.
 */

/**
 * jsdiff is O(ND): fast for an ordinary edit, degenerate when the two texts
 * share almost nothing. Past this edit distance `diffWords` gives up and
 * returns `undefined` — the modal then shows both versions whole instead of
 * freezing the tab (section 1 edge case: 20 000 characters).
 */
const DIFF_MAX_EDIT_LENGTH = 20000;

/**
 * **Without this, `diffWords` is a CHARACTER diff for Russian text.**
 *
 * jsdiff's default tokenizer splits on a hardcoded Latin word-character class
 * (`node_modules/diff/libesm/diff/word.js` — ASCII, Latin-1 Supplement, Latin
 * Extended A/B, IPA). Cyrillic is not in it, so every Cyrillic letter falls into
 * the "single non-word character" branch and becomes its own token. Verified on
 * a real post: «непринужденно улыбался» -> «нервно усмехался» came back as
 * `не[-п]р[-и][+в]н[-ужденн]о у[-лыб][+смех]ался` — precisely the unreadable
 * red-and-green wall that architecture decision 3.1 rejects, in the one language
 * this game is written in.
 *
 * jsdiff's own answer is `intlSegmenter`, which it documents for exactly this
 * case. With `ru` word granularity the same edit becomes two clean runs:
 * `[-непринужденно улыбался][+нервно усмехался]`.
 *
 * Built once, not per diff: constructing an `Intl.Segmenter` is not free and the
 * modal recomputes on every version switch. `null` on an engine without
 * `Intl.Segmenter` (or without ICU word data) — `diffWords` then falls back to
 * its own tokenizer, which is noisier for Cyrillic but still correct, and the
 * modal must not crash over a missing optimisation.
 */
/**
 * Structurally what jsdiff asks of the segmenter (it checks
 * `resolvedOptions().granularity`). Declared locally because `tsconfig.app.json`
 * targets `lib: ES2020`, where `Intl.Segmenter` has no typings yet — widening
 * the project's `lib` for one modal would be a far bigger change than this.
 */
type WordSegmenter = { resolvedOptions(): { granularity: string } };
type WordSegmenterCtor = new (
  locale: string,
  options: { granularity: 'word' },
) => WordSegmenter;

const WORD_SEGMENTER: WordSegmenter | null = (() => {
  try {
    const ctor = (Intl as unknown as { Segmenter?: WordSegmenterCtor }).Segmenter;
    if (typeof ctor !== 'function') return null;
    return new ctor('ru', { granularity: 'word' });
  } catch {
    return null;
  }
})();

export interface PostVersionHistoryModalProps {
  /** The post whose history to load. The modal fetches it itself. */
  postId: number;
  /** Closes the modal. */
  onClose: () => void;
}

type DiffRuns = ChangeObject<string>[];

/** `undefined` = the diff overflowed `DIFF_MAX_EDIT_LENGTH` and was abandoned. */
const computeDiff = (before: string, after: string): DiffRuns | undefined =>
  diffWords(before, after, {
    maxEditLength: DIFF_MAX_EDIT_LENGTH,
    // `as never` only bridges the missing ES2020 typing above — at runtime this
    // is a genuine `Intl.Segmenter`, which is what jsdiff validates.
    ...(WORD_SEGMENTER ? { intlSegmenter: WORD_SEGMENTER as never } : {}),
  });

/** Who made this version. A missing name must never render as a blank. */
const authorLabel = (entry: PostVersionEntry | null): string => {
  if (!entry) return '—';
  if (entry.author_username) return entry.author_username;
  if (entry.author_user_id !== null && entry.author_user_id !== undefined) {
    return `Пользователь #${entry.author_user_id}`;
  }
  return 'автор поста';
};

/**
 * When this version became the post's text. `null` is a real, meaningful value
 * here — the post was edited before the history existed, so the moment the
 * earliest surviving wording was written is unknowable (3.6).
 */
const timeLabel = (entry: PostVersionEntry | null): string => {
  if (!entry) return '—';
  if (!entry.created_at) return 'время неизвестно';
  return formatServerDateTime(entry.created_at);
};

const errorMessage = (error: unknown): string => {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status;
    if (status === 401) return 'Сессия истекла. Войдите заново.';
    if (status === 403) return 'Недостаточно прав для просмотра истории правок.';
    if (status === 404) return 'Пост не найден — возможно, его уже удалили.';
    if (status && status >= 500) return 'Сервер недоступен. Попробуйте позже.';
    if (!error.response) return 'Нет связи с сервером. Проверьте подключение.';
  }
  return 'Не удалось загрузить историю правок. Попробуйте позже.';
};

/** One coloured run of the word diff. Always a text node, never markup. */
const DiffRun = ({ part }: { part: ChangeObject<string> }) => {
  if (part.added) {
    return (
      <span className="bg-stat-energy/15 text-stat-energy rounded-[3px] px-0.5">
        {part.value}
      </span>
    );
  }
  if (part.removed) {
    return (
      <span className="bg-site-red/15 text-site-red line-through rounded-[3px] px-0.5">
        {part.value}
      </span>
    );
  }
  return <span className="text-white/70">{part.value}</span>;
};

interface DiffPaneProps {
  runs: DiffRuns | undefined;
  before: string;
  after: string;
  /** Wording differs between the text pane and the markup pane. */
  oversizeNotice: string;
  beforeCaption: string;
  afterCaption: string;
  /** Renders the fallback bodies in a monospace box (markup panel). */
  mono?: boolean;
}

/**
 * Renders a word diff, or — when jsdiff gave up — both versions whole. The
 * fallback is not an error state: it is the honest answer when the texts are
 * too far apart to align, and the admin can still read both.
 */
const DiffPane = ({
  runs,
  before,
  after,
  oversizeNotice,
  beforeCaption,
  afterCaption,
  mono = false,
}: DiffPaneProps) => {
  const bodyCls = mono
    ? 'font-mono text-[11px] leading-relaxed whitespace-pre-wrap break-all'
    : 'text-[13px] sm:text-sm leading-relaxed whitespace-pre-wrap break-words';

  if (runs === undefined) {
    return (
      <div className="flex flex-col gap-2.5">
        <p className="text-gold/80 text-[11px] leading-relaxed break-words">
          {oversizeNotice}
        </p>
        <div className="flex flex-col gap-1">
          <span className="text-white/35 text-[10.5px] uppercase tracking-[0.06em]">
            {beforeCaption}
          </span>
          <div className={`${bodyCls} text-white/60 bg-black/25 rounded-card p-2.5`}>
            {before || '(пусто)'}
          </div>
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-white/35 text-[10.5px] uppercase tracking-[0.06em]">
            {afterCaption}
          </span>
          <div className={`${bodyCls} text-white/60 bg-black/25 rounded-card p-2.5`}>
            {after || '(пусто)'}
          </div>
        </div>
      </div>
    );
  }

  if (runs.length === 0) {
    return <p className="text-white/40 text-xs">Обе версии пусты.</p>;
  }

  return (
    <div className={`${bodyCls} bg-black/25 rounded-card p-2.5 sm:p-3`}>
      {runs.map((part, index) => (
        <DiffRun key={index} part={part} />
      ))}
    </div>
  );
};

const PostVersionHistoryModal = ({ postId, onClose }: PostVersionHistoryModalProps) => {
  const [history, setHistory] = useState<PostVersionHistory | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  /**
   * Index into the ASCENDING `versions` array of the version being inspected.
   * The diff is always «предыдущая -> выбранная», so index 0 has no diff: it is
   * the earliest text that survives.
   */
  const [selected, setSelected] = useState(0);
  const [markupOpen, setMarkupOpen] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await axios.get<PostVersionHistory>(
        `${BASE_URL}/locations/posts/${postId}/versions`,
      );
      setHistory(data);
      // Newest pair preselected — the edit an admin almost always came for.
      setSelected(Math.max((data.versions?.length ?? 1) - 1, 0));
    } catch (err) {
      setError(errorMessage(err));
      setHistory(null);
    } finally {
      setLoading(false);
    }
  }, [postId]);

  useEffect(() => {
    void load();
  }, [load]);

  // Esc closes — the modal is read-only, there is nothing to lose.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const versions = history?.versions ?? [];
  const current = versions[selected] ?? null;
  const previous = selected > 0 ? (versions[selected - 1] ?? null) : null;

  const beforeHtml = previous?.content ?? '';
  const afterHtml = current?.content ?? '';

  // Keyed on the version pair, so switching versions never recomputes the rest
  // of the history and re-opening the same pair is free.
  const textDiff = useMemo(
    () =>
      previous
        ? computeDiff(htmlToPlainText(beforeHtml), htmlToPlainText(afterHtml))
        : undefined,
    [previous, beforeHtml, afterHtml],
  );

  const markupDiff = useMemo(
    () => (previous ? computeDiff(beforeHtml, afterHtml) : undefined),
    [previous, beforeHtml, afterHtml],
  );

  const formattingOnly = useMemo(
    () => (previous ? isFormattingOnlyChange(beforeHtml, afterHtml) : false),
    [previous, beforeHtml, afterHtml],
  );

  /**
   * Rows exist but the earliest one is not the post's original wording: the
   * post was edited before this feature shipped and that text is unrecoverable.
   * Saying nothing here would imply the first version IS the original.
   */
  const showLostOriginalBanner = history !== null && !history.original_available;

  /** Nothing to compare at all — edited in the dark, no rows were ever written. */
  const nothingToCompare =
    history !== null && versions.length <= 1 && !!history.post_edited_at;

  return (
    <div className="modal-overlay p-3 sm:p-4" role="presentation">
      <motion.div
        role="dialog"
        aria-modal="true"
        aria-label="История правок поста"
        initial={{ opacity: 0, scale: 0.97 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        className="modal-content gold-outline !w-[min(96vw,860px)] !max-w-[min(96vw,860px)]
                   !p-4 sm:!p-6 max-h-[92vh] overflow-y-auto gold-scrollbar
                   flex flex-col gap-4"
      >
        <div className="flex items-start justify-between gap-3">
          <h2 className="gold-text text-base sm:text-xl uppercase break-words">
            История правок
          </h2>
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть"
            title="Закрыть"
            className="w-8 h-8 shrink-0 flex items-center justify-center rounded-[8px] text-white/40
                       hover:text-white transition-colors duration-200 ease-site"
          >
            <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {loading && (
          <div className="flex items-center gap-2.5 text-white/50 text-xs py-6">
            <div className="w-4 h-4 border-2 border-gold/25 border-t-gold rounded-full animate-spin" />
            Загружаем историю правок…
          </div>
        )}

        {!loading && error && (
          <div className="flex flex-col items-start gap-2.5 py-4">
            <p className="text-site-red text-xs sm:text-sm break-words">{error}</p>
            <button type="button" onClick={() => void load()} className="btn-line text-xs px-4 py-1.5">
              Повторить
            </button>
          </div>
        )}

        {!loading && !error && history && (
          <>
            {showLostOriginalBanner && (
              <p className="text-gold/80 text-[11px] sm:text-xs leading-relaxed break-words
                            border border-gold-dark/30 bg-gold/[0.06] rounded-card p-2.5">
                Более ранние версии не сохранились: пост редактировали до появления истории
                правок.
              </p>
            )}

            {nothingToCompare ? (
              <p className="text-white/55 text-xs sm:text-sm leading-relaxed break-words">
                Пост редактировали до появления истории правок — сравнивать не с чем.
                Ниже показан текущий текст поста.
              </p>
            ) : versions.length <= 1 ? (
              <p className="text-white/55 text-xs sm:text-sm leading-relaxed break-words">
                Пост ни разу не редактировали — сохранена одна версия.
              </p>
            ) : null}

            <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 min-w-0">
              {/* Version list. Newest first — that is where an admin looks.
                  Below `sm` it collapses into a horizontal chip scroller so the
                  diff still gets the width at 360px. */}
              <div
                className="flex sm:flex-col gap-1.5 shrink-0 sm:w-[210px]
                           overflow-x-auto sm:overflow-x-visible sm:overflow-y-auto
                           sm:max-h-[52vh] gold-scrollbar pb-1 sm:pb-0"
                role="listbox"
                aria-label="Версии поста"
              >
                {[...versions].reverse().map((entry) => {
                  const index = versions.indexOf(entry);
                  const active = index === selected;
                  return (
                    <button
                      key={entry.version_no}
                      type="button"
                      role="option"
                      aria-selected={active}
                      onClick={() => setSelected(index)}
                      className={`shrink-0 sm:shrink text-left rounded-card border px-2.5 py-2
                                  transition-colors duration-200 ease-site min-w-[150px] sm:min-w-0
                                  ${
                                    active
                                      ? 'border-gold-dark/50 bg-gold/[0.08] text-white'
                                      : 'border-white/[0.07] bg-white/[0.02] text-white/60 hover:border-gold-dark/30 hover:text-white'
                                  }`}
                    >
                      <span className="flex items-center gap-1.5 flex-wrap text-[11.5px] font-medium">
                        Версия {entry.version_no}
                        {entry.is_current && (
                          <span className="text-gold text-[9px] font-bold uppercase tracking-[0.06em]
                                           bg-gold/15 px-1.5 py-0.5 rounded-full">
                            текущая
                          </span>
                        )}
                      </span>
                      <span className="block text-[10.5px] text-white/45 break-words">
                        {authorLabel(entry)}
                      </span>
                      <span className="block text-[10.5px] text-white/35 break-words">
                        {timeLabel(entry)}
                      </span>
                    </button>
                  );
                })}
              </div>

              {/* Diff pane */}
              <div className="flex flex-col gap-2.5 min-w-0 flex-1">
                {current && (
                  <p className="text-white/40 text-[11px] leading-relaxed break-words">
                    {previous ? (
                      <>
                        Сравнение: версия {previous.version_no} → версия {current.version_no}.
                        Правку сделал {authorLabel(current)}, {timeLabel(current)}.
                      </>
                    ) : (
                      <>
                        Версия {current.version_no} — самая ранняя из сохранённых, сравнивать
                        не с чем.
                      </>
                    )}
                  </p>
                )}

                {previous ? (
                  <>
                    {formattingOnly && (
                      <p className="text-gold/85 text-[11px] sm:text-xs leading-relaxed break-words
                                    border border-gold-dark/30 bg-gold/[0.06] rounded-card p-2.5">
                        Текст не изменился — правка коснулась только оформления.
                      </p>
                    )}

                    {!formattingOnly && (
                      <DiffPane
                        runs={textDiff}
                        before={htmlToPlainText(beforeHtml)}
                        after={htmlToPlainText(afterHtml)}
                        beforeCaption={`Версия ${previous.version_no}`}
                        afterCaption={`Версия ${current?.version_no ?? ''}`}
                        oversizeNotice="Правка слишком велика для пословного сравнения — версии показаны целиком."
                      />
                    )}

                    {/* Always available, collapsed by default: the raw markup
                        difference, as ESCAPED SOURCE TEXT. */}
                    <div className="flex flex-col gap-2">
                      <button
                        type="button"
                        onClick={() => setMarkupOpen((prev) => !prev)}
                        aria-expanded={markupOpen}
                        className="self-start text-site-blue text-[11px] hover:text-white
                                   transition-colors duration-200 ease-site break-words text-left"
                      >
                        {markupOpen ? 'Скрыть различия в разметке' : 'Показать различия в разметке'}
                      </button>
                      {markupOpen && (
                        <div className="flex flex-col gap-2">
                          <p className="text-white/35 text-[10.5px] leading-relaxed break-words">
                            Исходный HTML показан как текст и не выполняется.
                          </p>
                          <DiffPane
                            runs={markupDiff}
                            before={beforeHtml}
                            after={afterHtml}
                            beforeCaption={`Разметка версии ${previous.version_no}`}
                            afterCaption={`Разметка версии ${current?.version_no ?? ''}`}
                            oversizeNotice="Разметка слишком велика для пословного сравнения — версии показаны целиком."
                            mono
                          />
                        </div>
                      )}
                    </div>
                  </>
                ) : (
                  <div className="text-[13px] sm:text-sm leading-relaxed whitespace-pre-wrap
                                  break-words text-white/70 bg-black/25 rounded-card p-2.5 sm:p-3">
                    {htmlToPlainText(afterHtml) || '(пусто)'}
                  </div>
                )}
              </div>
            </div>
          </>
        )}

        <div className="flex justify-end">
          <button type="button" onClick={onClose} className="btn-line text-xs px-4 py-1.5">
            Закрыть
          </button>
        </div>
      </motion.div>
    </div>
  );
};

export default PostVersionHistoryModal;
