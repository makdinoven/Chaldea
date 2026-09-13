import { useCallback, useEffect, useState } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import { listDrafts, getDraftById, deleteDraftById } from '../../../api/postDrafts';
import type { PostDraftListItem } from '../../../types/postDrafts';
import ConfirmDialog from './ConfirmDialog';

export interface DraftsPanelProps {
  /** Owner of the history. Only this character's texts are listed. */
  characterId: number;
  /**
   * Location the post form is currently editing. It is what lets the panel
   * recognise the one row that is also mirrored in `localStorage` — the live
   * draft — so deleting it can drop that mirror too. `null` when unknown.
   */
  currentLocationId?: number | null;
  /** Called with the full HTML content of the chosen text (fetched via D2). */
  onInsert: (content: string) => void;
  /** Closes the panel and returns the user to the «Пост» tab. */
  onClose: () => void;
  /**
   * «Очистить черновик» (T23) — hard-deletes this location's live draft on the
   * server together with the browser mirror and the input field. Omitted when
   * drafts are disabled (NPC mode / no character), which hides the button.
   * Must not reject: it reports its own failure through the form's banner.
   */
  onClearCurrentDraft?: () => Promise<void>;
  /** There is something to clear right now (field non-empty or a draft saved). */
  canClearCurrentDraft?: boolean;
  /**
   * The row just deleted here (D6) was this location's live draft. The parent
   * has to drop the `localStorage` mirror as well, or restore-on-mount would
   * resurrect a text the player deleted.
   */
  onCurrentDraftDeleted?: () => void;
}

/** Russian date + time of a history row, e.g. «13 сент. 2026, 14:30». */
const formatDraftDate = (iso: string): string => {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const sameYear = date.getFullYear() === new Date().getFullYear();
  return date.toLocaleString('ru-RU', {
    day: 'numeric',
    month: 'short',
    ...(sameYear ? {} : { year: 'numeric' }),
    hour: '2-digit',
    minute: '2-digit',
  });
};

/**
 * Body of the «Черновики» tab (FEAT-156, T12).
 *
 * Shows the character's last ≤10 saved texts — both unfinished drafts and
 * already-posted ones. The list itself carries no `content` (see 3.3), so
 * «Вставить» fetches the full text via D2 before handing it to the parent.
 *
 * Every failure is surfaced in Russian: the load error replaces the list with
 * a red bordered block and a «Повторить» button (deliberately unmistakable
 * next to the quiet, borderless empty state), and per-row failures show both
 * a toast and a persistent inline banner. Nothing is ever swallowed — an
 * invisible failure here would read as «мои черновики пропали».
 */
const DraftsPanel = ({
  characterId,
  currentLocationId = null,
  onInsert,
  onClose,
  onClearCurrentDraft,
  canClearCurrentDraft = false,
  onCurrentDraftDeleted,
}: DraftsPanelProps) => {
  const [drafts, setDrafts] = useState<PostDraftListItem[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [insertingId, setInsertingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [pendingDelete, setPendingDelete] = useState<PostDraftListItem | null>(null);
  const [confirmClearOpen, setConfirmClearOpen] = useState(false);
  const [clearing, setClearing] = useState(false);

  const loadDrafts = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const items = await listDrafts(characterId);
      setDrafts(items);
    } catch {
      setDrafts([]);
      setLoadError('Не удалось загрузить сохранённые тексты. Они не потеряны — попробуйте ещё раз.');
    } finally {
      setLoading(false);
    }
  }, [characterId]);

  useEffect(() => {
    void loadDrafts();
  }, [loadDrafts]);

  const handleInsert = async (draft: PostDraftListItem) => {
    setInsertingId(draft.id);
    setActionError(null);
    try {
      const full = await getDraftById(draft.id);
      onInsert(full.content);
    } catch {
      const message = 'Не удалось загрузить текст черновика. Попробуйте ещё раз.';
      setActionError(message);
      toast.error(message);
    } finally {
      setInsertingId(null);
    }
  };

  /**
   * The row that the post form is currently autosaving into. It is the only one
   * with a `localStorage` mirror, so it is the only one whose deletion needs
   * the parent to clean up after it.
   */
  const isCurrentLiveDraft = (draft: PostDraftListItem): boolean =>
    draft.is_active && currentLocationId !== null && draft.location_id === currentLocationId;

  const handleConfirmDelete = async () => {
    const draft = pendingDelete;
    if (!draft) return;
    setPendingDelete(null);
    setDeletingId(draft.id);
    setActionError(null);
    try {
      await deleteDraftById(draft.id);
      setDrafts((prev) => prev.filter((item) => item.id !== draft.id));
      // D6 removed the server row; the browser mirror of the live draft would
      // otherwise hand the deleted text back on the next visit.
      if (isCurrentLiveDraft(draft)) onCurrentDraftDeleted?.();
      toast.success('Текст удалён');
    } catch {
      const message = 'Не удалось удалить текст. Попробуйте ещё раз.';
      setActionError(message);
      toast.error(message);
    } finally {
      setDeletingId(null);
    }
  };

  /**
   * «Очистить черновик» (T23). Destructive on purpose and worded as such — it
   * is the one action here that really does destroy a text, which is why it
   * keeps the `danger` styling it had in the post form.
   */
  const handleConfirmClear = async () => {
    if (!onClearCurrentDraft) return;
    setConfirmClearOpen(false);
    setClearing(true);
    setActionError(null);
    try {
      await onClearCurrentDraft();
    } finally {
      setClearing(false);
      // The live row is gone (or the parent surfaced the failure) — either way
      // the list on screen must stop claiming otherwise.
      void loadDrafts();
    }
  };

  const hasLiveDraftHere = drafts.some(
    (draft) => draft.is_active && currentLocationId !== null && draft.location_id === currentLocationId,
  );
  const showClearButton = !!onClearCurrentDraft && (canClearCurrentDraft || hasLiveDraftHere);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, ease: 'easeOut' }}
      className="w-full min-w-0"
    >
      <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
        <span className="text-white/50 text-[11px] sm:text-xs">
          Последние 10 текстов этого персонажа
        </span>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
          {showClearButton && (
            <button
              type="button"
              disabled={clearing}
              className="px-3 py-1 rounded-[10px] border border-white/[0.15] text-white/70 text-[11px] sm:text-xs font-medium
                         hover:border-site-red hover:text-site-red transition-colors duration-200 ease-site
                         disabled:opacity-50 disabled:cursor-not-allowed"
              onClick={() => setConfirmClearOpen(true)}
            >
              {clearing ? 'Очищаем…' : 'Очистить черновик'}
            </button>
          )}
          <button
            type="button"
            className="text-white/60 hover:text-site-blue transition-colors duration-200 ease-site text-[11px] sm:text-xs"
            onClick={onClose}
          >
            Вернуться к посту
          </button>
        </div>
      </div>

      {actionError && (
        <div className="mb-3 rounded-card border border-site-red/60 bg-site-red/10 px-3 py-2 text-site-red text-xs break-words">
          {actionError}
        </div>
      )}

      {loading && (
        <div className="py-8 text-center text-white/50 text-sm">Загружаем сохранённые тексты…</div>
      )}

      {!loading && loadError && (
        <div className="rounded-card border border-site-red/60 bg-site-red/10 p-4 flex flex-col items-start gap-3">
          <p className="text-site-red text-sm break-words">{loadError}</p>
          <button type="button" className="btn-blue !py-1.5 !px-4 !text-xs" onClick={() => void loadDrafts()}>
            Повторить
          </button>
        </div>
      )}

      {!loading && !loadError && drafts.length === 0 && (
        <div className="py-8 text-center text-white/40 text-sm">Сохранённых текстов пока нет</div>
      )}

      {!loading && !loadError && drafts.length > 0 && (
        <ul className="gold-scrollbar overflow-y-auto max-h-[55vh] pr-1 flex flex-col gap-2">
          {drafts.map((draft) => {
            const busy = insertingId === draft.id || deletingId === draft.id;
            return (
              <li
                key={draft.id}
                className="rounded-card border border-white/10 bg-white/[0.03] p-3 min-w-0"
              >
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mb-1.5 min-w-0">
                  <span className="gold-text text-xs font-medium uppercase break-words min-w-0">
                    {draft.location_name || 'Неизвестная локация'}
                  </span>
                  <span className="text-white/40 text-[11px]">{formatDraftDate(draft.updated_at)}</span>
                  <span
                    className={`chip-outline rounded-full px-2 py-0.5 text-[10px] font-medium ${
                      draft.is_sent ? 'text-stat-energy' : 'text-site-blue'
                    }`}
                  >
                    {draft.is_sent ? 'Отправлен' : 'Черновик'}
                  </span>
                </div>

                <p className="text-white/70 text-xs sm:text-sm line-clamp-2 break-words mb-2">
                  {draft.preview || 'Пустой текст'}
                </p>

                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-white/30 text-[11px]">{draft.char_count} симв.</span>
                  <div className="flex flex-col sm:flex-row gap-2 w-full sm:w-auto">
                    <button
                      type="button"
                      disabled={busy}
                      className="btn-blue !py-1.5 !px-4 !text-xs disabled:opacity-50 disabled:cursor-not-allowed"
                      onClick={() => void handleInsert(draft)}
                    >
                      {insertingId === draft.id ? 'Загрузка…' : 'Вставить'}
                    </button>
                    <button
                      type="button"
                      disabled={busy}
                      className="px-4 py-1.5 text-xs text-white/60 hover:text-site-red transition-colors duration-200 ease-site disabled:opacity-50 disabled:cursor-not-allowed"
                      onClick={() => setPendingDelete(draft)}
                    >
                      {deletingId === draft.id ? 'Удаляем…' : 'Удалить'}
                    </button>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {confirmClearOpen && (
        <ConfirmDialog
          title="Очистить черновик?"
          message="Текущий черновик этой локации будет удалён с сервера и из этого браузера."
          confirmLabel="Очистить"
          cancelLabel="Отмена"
          danger
          onConfirm={() => void handleConfirmClear()}
          onCancel={() => setConfirmClearOpen(false)}
        />
      )}

      {pendingDelete && (
        <ConfirmDialog
          title="Удалить текст?"
          message="Текст будет удалён без возможности восстановления."
          confirmLabel="Удалить"
          cancelLabel="Отмена"
          danger
          onConfirm={() => void handleConfirmDelete()}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </motion.div>
  );
};

export default DraftsPanel;
