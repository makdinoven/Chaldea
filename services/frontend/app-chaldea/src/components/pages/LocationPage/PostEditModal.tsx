import { useMemo, useState } from 'react';
import { motion } from 'motion/react';
import WysiwygEditor from '../../CommonComponents/WysiwygEditor/WysiwygEditor';
import ConfirmDialog from './ConfirmDialog';
import { Post } from './types';
import {
  GATE_COST,
  GATE_LABEL,
  GATE_STYLE,
  GATE_ORDER,
  MIN_POST_LENGTH,
  stripHtmlTags,
  requiredSymbolsForGates,
  type PostGate,
} from './gateConstants';

export interface PostEditModalProps {
  /** The post being edited — supplies the initial text and its locked gates. */
  post: Post;
  /**
   * Persists the new text. **Must reject with an `Error` whose `message` is a
   * ready-to-show Russian string** — that message is rendered inline and the
   * editor keeps the player's text. Resolving means the server returned 200.
   */
  onSave: (postId: number, content: string) => Promise<void>;
  /** Closes the modal. Called only on an explicit user action or after a 200. */
  onClose: () => void;
}

/**
 * Post editor for FEAT-159 (Phase A).
 *
 * **Deliberately NOT an `editMode` prop on `PostCreateForm`.** That form is
 * wired end-to-end into the FEAT-156 draft system (`usePostDraft`, autosave,
 * the drafts tab). Running an edit session through it would autosave the edited
 * text over the location's *live* draft and destroy whatever the player had
 * been writing — precisely the text-destruction bug FEAT-156 exists to prevent.
 * There is therefore **no draft wiring here at all**, by design.
 *
 * The second invariant is the same one, stated for failures: **no code path
 * that is not a confirmed success may unmount the editor.** Every rejection
 * (403 / 404 / 409 / 5xx / network) renders the server's Russian `detail` in
 * the inline error area with the text untouched. A feature whose whole purpose
 * is recovering from a mistake must not invent a new way to lose text.
 *
 * Phase A edits text only. The post's existing gates are shown as locked,
 * non-interactive chips: a declared intent can be neither changed nor removed
 * (section 3.6), and it still costs its symbols, so the counter charges for
 * them. Adding new gates is Phase B (T12).
 */
const PostEditModal = ({ post, onSave, onClose }: PostEditModalProps) => {
  const [content, setContent] = useState(post.content);
  const [saving, setSaving] = useState(false);
  /** Russian, user-visible. Never cleared by anything but a new attempt. */
  const [error, setError] = useState<string | null>(null);
  const [confirmCancelOpen, setConfirmCancelOpen] = useState(false);

  const charCount = useMemo(() => stripHtmlTags(content).length, [content]);

  /**
   * The post's already-declared gates, as `{action_type: count}` from
   * `ClientPost.gates`. They are locked, but they are still paid for — the
   * server recomputes the budget over the post's entire gate set, so shortening
   * the text below their cost is rejected. The counter mirrors that rule.
   */
  const lockedGates: PostGate[] = useMemo(
    () =>
      GATE_ORDER.filter((at) => (post.gates?.[at] ?? 0) > 0).map((at) => ({
        action_type: at,
        // Only the count is on the wire in Phase A; the cost formula needs a
        // target list of the same length, and the ids are irrelevant to it.
        targets: Array.from({ length: post.gates?.[at] ?? 0 }, (_, i) => i),
      })),
    [post.gates],
  );
  /** Gate types the server knows nothing about here — shown, never priced. */
  const unknownGates = useMemo(
    () =>
      Object.entries(post.gates ?? {}).filter(
        ([at, count]) => (count ?? 0) > 0 && !(GATE_ORDER as readonly string[]).includes(at),
      ),
    [post.gates],
  );

  const requiredSymbols = requiredSymbolsForGates(lockedGates);
  const meetsMinLength = charCount >= requiredSymbols;
  const progressPct = Math.min(100, Math.round((charCount / requiredSymbols) * 100));
  const isDirty = content !== post.content;

  const handleSave = async () => {
    if (saving) return;
    if (!meetsMinLength) {
      setError(
        `Минимальная длина — ${requiredSymbols} символов (сейчас: ${charCount}).`,
      );
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave(post.post_id, content);
      // The ONLY path that closes the editor: a confirmed 200.
      onClose();
    } catch (err) {
      setError(
        err instanceof Error && err.message
          ? err.message
          : 'Не удалось сохранить изменения. Текст остался в редакторе — попробуйте ещё раз.',
      );
      setSaving(false);
    }
  };

  const requestClose = () => {
    if (saving) return;
    if (isDirty) {
      setConfirmCancelOpen(true);
      return;
    }
    onClose();
  };

  return (
    <>
      {/* The overlay is intentionally NOT click-to-close: a stray click must
          not throw away an edit in progress. Closing is «Отмена» or a 200. */}
      <div className="modal-overlay p-3 sm:p-4" role="presentation">
        <motion.div
          role="dialog"
          aria-modal="true"
          aria-label="Редактирование поста"
          initial={{ opacity: 0, scale: 0.97 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.2, ease: 'easeOut' }}
          className="modal-content gold-outline !w-[min(96vw,720px)] !max-w-[min(96vw,720px)]
                     !p-4 sm:!p-6 max-h-[92vh] overflow-y-auto gold-scrollbar
                     flex flex-col gap-4"
        >
          <div className="flex items-start justify-between gap-3">
            <h2 className="gold-text text-base sm:text-xl uppercase break-words">
              Редактирование поста
            </h2>
            <button
              type="button"
              onClick={requestClose}
              disabled={saving}
              aria-label="Закрыть"
              title="Закрыть"
              className="w-8 h-8 shrink-0 flex items-center justify-center rounded-[8px] text-white/40
                         hover:text-white transition-colors duration-200 ease-site
                         disabled:opacity-30 disabled:cursor-not-allowed"
            >
              <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Section-1 rule made visible: editing buys no XP. */}
          <p className="text-white/55 text-[11px] sm:text-xs leading-relaxed break-words">
            Опыт за пост не пересчитывается — он начислен при публикации. Правка не даёт
            дополнительного опыта, сколько бы текста вы ни добавили.
          </p>

          {/* Locked intent gates — declared once, never changed or removed. */}
          {(lockedGates.length > 0 || unknownGates.length > 0) && (
            <div className="flex flex-col gap-2">
              <span className="text-white/40 text-[10.5px] uppercase tracking-[0.06em]">
                Объявленные намерения
              </span>
              <div className="flex flex-wrap gap-1.5">
                {lockedGates.map((g) => {
                  const style = GATE_STYLE[g.action_type];
                  return (
                    <span
                      key={g.action_type}
                      title="Уже объявленное намерение нельзя изменить или снять"
                      className={`flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-0.5 rounded-full border
                                  opacity-70 cursor-not-allowed break-words ${style.activeCls}`}
                    >
                      {style.icon} {GATE_LABEL[g.action_type]}
                      {g.targets.length > 1 ? ` ×${g.targets.length}` : ''}
                      <span className="text-white/40">· {GATE_COST[g.action_type] * g.targets.length} симв.</span>
                    </span>
                  );
                })}
                {unknownGates.map(([at, count]) => (
                  <span
                    key={at}
                    title="Уже объявленное намерение нельзя изменить или снять"
                    className="flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-0.5 rounded-full
                               border border-gold/20 bg-gold/10 text-gold/90 opacity-70 cursor-not-allowed break-words"
                  >
                    {at}
                    {count > 1 ? ` ×${count}` : ''}
                  </span>
                ))}
              </div>
              <span className="text-white/35 text-[11px] break-words">
                Намерения нельзя изменить или снять при редактировании, и они по-прежнему
                оплачиваются длиной текста.
              </span>
            </div>
          )}

          <WysiwygEditor content={post.content} onChange={setContent} enableArchiveLinks />

          {/* Counter + progress — the client mirror of the server's rule. */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs sm:text-[12.5px]">
            <span className={`font-medium ${meetsMinLength ? 'text-stat-energy' : 'text-site-red'}`}>
              {charCount} / {requiredSymbols} символов
            </span>
            {!meetsMinLength && (
              <span className="text-site-red">
                Ещё {requiredSymbols - charCount} символов до минимума
              </span>
            )}
            <div className="flex-1 min-w-[100px] h-[5px] rounded-full bg-white/10 overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-200 ${
                  meetsMinLength ? 'bg-stat-energy' : 'bg-site-red/80'
                }`}
                style={{ width: `${progressPct}%` }}
              />
            </div>
          </div>

          {/* Inline error area. Rendering here — not as a toast — is the point:
              the message sits next to the text it is about, and the text stays. */}
          {error && (
            <div
              role="alert"
              className="rounded-card border border-site-red/60 bg-site-red/10 px-3 py-2 text-site-red text-xs break-words"
            >
              {error}
              <span className="block text-white/50 mt-1">
                Текст сохранён в редакторе — скопируйте его, если хотите закрыть окно.
              </span>
            </div>
          )}

          <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2.5 sm:gap-3">
            <button
              type="button"
              className="btn-line !text-xs !py-2 !px-5 disabled:opacity-30 disabled:cursor-not-allowed"
              onClick={requestClose}
              disabled={saving}
            >
              Отмена
            </button>
            <button
              type="button"
              className="btn-blue !py-2 !px-5 !text-xs disabled:opacity-40 disabled:cursor-not-allowed"
              onClick={handleSave}
              disabled={saving || !meetsMinLength || !isDirty}
              title={
                !isDirty
                  ? 'Текст не изменён'
                  : !meetsMinLength
                    ? `Минимум ${Math.max(MIN_POST_LENGTH, requiredSymbols)} символов`
                    : undefined
              }
            >
              {saving ? 'Сохраняем…' : 'Сохранить'}
            </button>
          </div>
        </motion.div>
      </div>

      {confirmCancelOpen && (
        <ConfirmDialog
          title="Отменить редактирование?"
          message="Внесённые правки не будут сохранены, а исходный текст поста останется прежним."
          confirmLabel="Отменить правки"
          cancelLabel="Продолжить"
          danger
          onConfirm={() => {
            setConfirmCancelOpen(false);
            onClose();
          }}
          onCancel={() => setConfirmCancelOpen(false)}
        />
      )}
    </>
  );
};

export default PostEditModal;
