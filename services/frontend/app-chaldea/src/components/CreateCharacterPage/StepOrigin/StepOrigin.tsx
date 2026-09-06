import { useEffect, useMemo, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { Link } from 'react-router-dom';
import { AnimatePresence, motion } from 'motion/react';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  fetchOriginsThunk,
  selectOrigins,
  selectOriginsError,
  selectOriginsLoading,
} from '../../../redux/slices/originsSlice';
import { fetchArticleBySlug } from '../../../api/archive';
import { htmlExcerpt } from '../../../utils/htmlExcerpt';
import type { SubraceData } from '../types';

/**
 * FEAT-154 (task #17) — step 2, «Родина» (rules 8-11).
 *
 * The origin is a registry entity, not a free-text field: a country with an
 * emblem, a short dossier, its stance towards the Скитальцы and — where the
 * Архив has one — a lore article behind a hover preview. Countries that are not
 * typical for the chosen subrace stay selectable and are simply marked «редкий
 * выбор» (rule 11).
 *
 * The dossier is rendered on parchment because it IS an in-world document — an
 * extract from the Архив (DESIGN-SYSTEM §16). The rare-choice marker is
 * therefore `lore-badge-warn`, the ink twin of `chip-outline`.
 *
 * FEAT-155 (rules 10-11): the «На карте мира» / «За пределами карты» markers are
 * gone together with `is_playable` — the distinction meant nothing to the
 * player. «Характерная родина» stays: that one is the subrace mechanic, and it
 * is now the only reason a country carries a caption at all.
 */

/** How much of the article is pulled into the dossier before «Читать дальше». */
const ARCHIVE_EXCERPT_LIMIT = 1000;

/**
 * The excerpt of an Архив article, as shown inside the dossier.
 * `unavailable` = no article / 404 / network failure → the dossier silently
 * falls back to the origin's own short summary.
 */
type ArchiveExcerpt =
  | { status: 'ready'; text: string; truncated: boolean; coverUrl: string | null }
  | { status: 'unavailable' };

/**
 * Module-level cache: one request per slug for the whole session, so switching
 * back and forth between countries never refetches the same article.
 */
const excerptCache = new Map<string, ArchiveExcerpt>();

interface StepOriginProps {
  selectedOriginId: number | null;
  onSelectOrigin: (originId: number) => void;
  /** The subrace picked on step 1 — supplies `typical_origin_ids` (rule 11). */
  selectedSubrace: SubraceData | null;
}

const StepOrigin = ({ selectedOriginId, onSelectOrigin, selectedSubrace }: StepOriginProps) => {
  const dispatch = useAppDispatch();
  const origins = useAppSelector(selectOrigins);
  const loading = useAppSelector(selectOriginsLoading);
  const error = useAppSelector(selectOriginsError);
  const notifiedErrorRef = useRef<string | null>(null);

  useEffect(() => {
    if (origins.length === 0) {
      dispatch(fetchOriginsThunk());
    }
  }, [dispatch, origins.length]);

  // The load failure must always reach the player, never only the console.
  useEffect(() => {
    if (error && notifiedErrorRef.current !== error) {
      notifiedErrorRef.current = error;
      toast.error(error);
    }
    if (!error) notifiedErrorRef.current = null;
  }, [error]);

  const typicalIds = useMemo(
    () => selectedSubrace?.typical_origin_ids ?? null,
    [selectedSubrace],
  );

  const typicalNames = useMemo(() => {
    if (!typicalIds || typicalIds.length === 0) return [];
    return origins.filter((origin) => typicalIds.includes(origin.id)).map((origin) => origin.name);
  }, [typicalIds, origins]);

  const selectedOrigin = origins.find((origin) => origin.id === selectedOriginId) ?? null;
  const archiveSlug = selectedOrigin?.archive_slug ?? null;

  const [excerpt, setExcerpt] = useState<ArchiveExcerpt | null>(null);
  const [excerptLoading, setExcerptLoading] = useState(false);

  /**
   * Pulls the article text for the selected country only. A failure here is not
   * worth a red toast on every click: the dossier already has a short summary,
   * so we fall back to it quietly (the cache also remembers the failure, so a
   * dead slug is not retried on every re-selection).
   */
  useEffect(() => {
    if (!archiveSlug) {
      setExcerpt(null);
      setExcerptLoading(false);
      return;
    }

    const cached = excerptCache.get(archiveSlug);
    if (cached) {
      setExcerpt(cached);
      setExcerptLoading(false);
      return;
    }

    let cancelled = false;
    setExcerpt(null);
    setExcerptLoading(true);

    fetchArticleBySlug(archiveSlug)
      .then((article) => {
        const { text, truncated } = htmlExcerpt(article.content ?? '', ARCHIVE_EXCERPT_LIMIT);
        const entry: ArchiveExcerpt = text
          ? {
              status: 'ready',
              text,
              truncated,
              coverUrl: article.cover_image_url || null,
            }
          : { status: 'unavailable' };
        excerptCache.set(archiveSlug, entry);
        if (!cancelled) setExcerpt(entry);
      })
      .catch(() => {
        const entry: ArchiveExcerpt = { status: 'unavailable' };
        excerptCache.set(archiveSlug, entry);
        if (!cancelled) setExcerpt(entry);
      })
      .finally(() => {
        if (!cancelled) setExcerptLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [archiveSlug]);

  const articleExcerpt = excerpt?.status === 'ready' ? excerpt : null;
  const coverUrl = articleExcerpt?.coverUrl ?? null;

  /** `null` = the subrace has no typical list, so nothing can be «rare». */
  const isRareChoice =
    selectedOrigin && typicalIds && typicalIds.length > 0
      ? !typicalIds.includes(selectedOrigin.id)
      : false;

  if (loading && origins.length === 0) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-10 h-10 border-4 border-white/30 border-t-white rounded-full animate-spin" />
      </div>
    );
  }

  if (error && origins.length === 0) {
    return (
      <div className="flex flex-col items-center gap-4 py-10 px-4">
        <p className="text-site-red text-center text-sm">{error}</p>
        <button type="button" className="btn-line" onClick={() => dispatch(fetchOriginsThunk())}>
          Повторить
        </button>
      </div>
    );
  }

  if (origins.length === 0) {
    return (
      <p className="text-white/60 text-sm text-center py-10">
        Справочник происхождений пуст. Обратитесь к администрации.
      </p>
    );
  }

  return (
    <div className="w-full flex flex-col gap-6 px-4 md:px-[60px]">
      <p className="field-hint max-w-[720px]">
        Родина не даёт бонусов к характеристикам — она определяет, как на вас смотрят и с
        чем вы выйдете в первый путь: стартовый набор подбирается под пару «класс ×
        происхождение».
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,320px)_1fr] gap-6">
        {/* Country list */}
        <div className="flex flex-col gap-2 lg:max-h-[560px] lg:overflow-y-auto gold-scrollbar pr-1">
          {origins.map((origin) => {
            const isSelected = origin.id === selectedOriginId;
            const isTypical = typicalIds && typicalIds.length > 0 && typicalIds.includes(origin.id);

            return (
              <motion.button
                key={origin.id}
                type="button"
                onClick={() => onSelectOrigin(origin.id)}
                aria-pressed={isSelected}
                layout
                animate={{
                  opacity: isSelected ? 1 : 0.45,
                  scale: isSelected ? 1 : 0.96,
                }}
                whileHover={!isSelected ? { opacity: 0.7, scale: 0.98 } : undefined}
                transition={{ duration: 0.25, ease: 'easeOut' }}
                className={`flex items-center gap-3 p-3 rounded-card text-left w-full shrink-0
                  origin-left transition-colors
                  ${isSelected ? '' : 'hover:bg-white/5'}`}
              >
                <span className="w-12 h-12 shrink-0 rounded-full overflow-hidden bg-white/10 flex items-center justify-center">
                  {origin.emblem_url ? (
                    <img
                      src={origin.emblem_url}
                      alt=""
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <span className="text-white/30 text-xs">—</span>
                  )}
                </span>

                <span className="flex flex-col min-w-0 gap-0.5">
                  <span
                    className={`text-sm sm:text-base font-medium truncate ${
                      isSelected ? 'gold-text' : 'text-white'
                    }`}
                  >
                    {origin.name}
                  </span>
                  {isTypical && (
                    <span className="text-white/40 text-[11px]">Характерная родина</span>
                  )}
                </span>
              </motion.button>
            );
          })}
        </div>

        {/* Dossier — an extract from the Архив, hence parchment */}
        <AnimatePresence mode="wait">
          {selectedOrigin ? (
            <motion.article
              key={selectedOrigin.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              transition={{ duration: 0.25, ease: 'easeOut' }}
              className="book-page rounded-card shadow-page p-5 sm:p-8 flex flex-col gap-4"
            >
              <div className="flex flex-wrap items-center gap-4">
                {selectedOrigin.emblem_url && (
                  <img
                    src={selectedOrigin.emblem_url}
                    alt={`Герб: ${selectedOrigin.name}`}
                    className="w-16 h-16 sm:w-20 sm:h-20 object-contain shrink-0"
                  />
                )}
                <div className="min-w-0 flex-1">
                  <h3 className="lore-heading text-xl sm:text-2xl">{selectedOrigin.name}</h3>
                  <p className="text-ink-muted text-xs uppercase tracking-[0.08em]">
                    Выписка из Архива Скитальцев
                  </p>
                </div>

                {/*
                  The article's own cover, pasted onto the sheet like a plate.
                  Rendered only when the article really carries one; on narrow
                  screens `flex-wrap` + `flex-1` on the title drops it to its own
                  row instead of squeezing a long country name.
                */}
                {coverUrl && (
                  <img
                    src={coverUrl}
                    alt={`Иллюстрация из статьи Архива: ${selectedOrigin.name}`}
                    loading="lazy"
                    className="w-20 h-14 sm:w-24 sm:h-[68px] object-cover shrink-0
                      rounded-card border border-ink-muted/40 bg-parchment-dark
                      shadow-[2px_3px_6px_rgba(0,0,0,.25)] rotate-[-1.5deg]"
                  />
                )}
              </div>

              <div className="flex flex-wrap gap-2">
                {isRareChoice && <span className="lore-badge lore-badge-warn">Редкий выбор</span>}
                {!isRareChoice && typicalIds && typicalIds.length > 0 && (
                  <span className="lore-badge lore-badge-ok">Характерная родина</span>
                )}
              </div>

              <div className="lore-divider" />

              {/*
                The body is the beginning of the real Архив article (plain text,
                never `dangerouslySetInnerHTML`). While it loads — and whenever
                it cannot be loaded — the origin's own short summary stays in
                place, so the sheet never flashes empty.
              */}
              <div className="flex flex-col gap-2">
                <p className="lore-body whitespace-pre-wrap">
                  {articleExcerpt
                    ? articleExcerpt.text
                    : selectedOrigin.summary || 'Об этой земле Архив пока молчит.'}
                </p>

                {excerptLoading && (
                  <span className="flex items-center gap-2 text-ink-muted text-xs">
                    <span className="w-3.5 h-3.5 border-2 border-ink-muted/30 border-t-ink-muted rounded-full animate-spin" />
                    Архив листает страницы…
                  </span>
                )}
              </div>

              <div className="flex flex-col gap-1">
                <span className="passport-field-label">Как здесь смотрят на Скитальцев</span>
                <p className="lore-body whitespace-pre-wrap">
                  {selectedOrigin.skitaltsy_attitude ||
                    'Отношение к Скитальцам в записях не отражено.'}
                </p>
              </div>

              {isRareChoice && typicalNames.length > 0 && (
                <p className="lore-body text-sm">
                  Для подрасы «{selectedSubrace?.name}» обычны:{' '}
                  {typicalNames.join(', ')}. Выбор разрешён — просто будьте готовы объяснять
                  своё происхождение чаще других.
                </p>
              )}

              {/*
                Nothing to «read further» when the whole article already fits on
                the sheet — the button appears only if the text was cut, or if
                the article could not be pulled in at all.
              */}
              {archiveSlug && (!articleExcerpt || articleExcerpt.truncated) && (
                <>
                  <div className="lore-divider" />
                  <Link
                    to={`/archive/${archiveSlug}`}
                    className="self-start inline-flex items-center gap-2 px-4 py-2 rounded-card
                      border border-ink-muted/50 bg-parchment-light/50 text-ink font-lore text-sm
                      hover:bg-parchment-dark transition-colors duration-200"
                  >
                    Читать дальше в статье
                    <span aria-hidden="true">→</span>
                  </Link>
                </>
              )}
            </motion.article>
          ) : (
            <motion.div
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="gray-bg rounded-card p-6 flex items-center justify-center"
            >
              <p className="text-white/50 text-sm text-center">
                Выберите родину — и Архив выдаст справку о ней.
              </p>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};

export default StepOrigin;
