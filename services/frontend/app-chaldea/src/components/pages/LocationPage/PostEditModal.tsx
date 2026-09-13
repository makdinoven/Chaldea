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
  DEFAULT_GATE_COST,
  FALLBACK_GATE_STYLE,
  MIN_POST_LENGTH,
  stripHtmlTags,
  requiredSymbolsForGates,
  type GateOptions,
  type PostGate,
} from './gateConstants';

export interface PostEditModalProps {
  /** The post being edited — supplies the initial text and its locked gates. */
  post: Post;
  /**
   * Targets available on this location, keyed by `action_type` — the menu for
   * **new** intents only. Existing gates are never edited through it.
   */
  gateOptions?: GateOptions;
  /**
   * Whether this player may file a gate request at all: the server demands the
   * post's character still be standing in the post's location
   * (403 «Чтобы добавить намерение, нужно находиться в этой локации»). When
   * `false` the picker is replaced by that explanation instead of offering a
   * choice that is guaranteed to fail.
   */
  canAddGates?: boolean;
  /**
   * Persists the new text and any newly requested gates. **Must reject with an
   * `Error` whose `message` is a ready-to-show Russian string** — that message
   * is rendered inline and the editor keeps the player's text. Resolving means
   * the server returned 200.
   */
  onSave: (postId: number, content: string, gates: PostGate[]) => Promise<void>;
  /** Closes the modal. Called only on an explicit user action or after a 200. */
  onClose: () => void;
}

/**
 * Post editor for FEAT-159 (Phase A text editing + Phase B gate requests).
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
 * (400 / 403 / 404 / 409 / 5xx / network) renders the server's Russian `detail`
 * in the inline error area with the text untouched. A feature whose whole
 * purpose is recovering from a mistake must not invent a new way to lose text.
 *
 * Gates come in three kinds here and they are visually different on purpose:
 *
 * - **already declared** (`post.gates`) — locked, ticked, non-interactive. A
 *   declared intent can be neither changed nor removed (section 3.6); the chip
 *   must not read as "disabled, maybe clickable later";
 * - **awaiting moderation** (`post.pending_gates`) — an earlier edit already
 *   filed a request. Also locked, marked «на рассмотрении», and it blocks a
 *   second request (the server answers 409);
 * - **newly ticked** — selectable, and explicitly labelled as taking effect
 *   only after an administrator approves it. The player must understand that
 *   *before* saving, not from a surprise afterwards.
 *
 * All three cost symbols, and the counter charges for all three together —
 * the client mirror of the merged budget the server recomputes in
 * `crud.edit_post`.
 */
const PostEditModal = ({
  post,
  gateOptions = {},
  canAddGates = false,
  onSave,
  onClose,
}: PostEditModalProps) => {
  const [content, setContent] = useState(post.content);
  const [saving, setSaving] = useState(false);
  /** Russian, user-visible. Never cleared by anything but a new attempt. */
  const [error, setError] = useState<string | null>(null);
  const [confirmCancelOpen, setConfirmCancelOpen] = useState(false);
  /** Newly requested intents: action_type → chosen target ids. */
  const [selectedGates, setSelectedGates] = useState<Record<string, number[]>>({});

  const charCount = useMemo(() => stripHtmlTags(content).length, [content]);

  /** `{action_type: count}` → a sorted, displayable list. */
  const toEntries = (map: Record<string, number> | undefined) =>
    Object.entries(map ?? {})
      .filter(([, count]) => (count ?? 0) > 0)
      .sort(
        (a, b) =>
          (GATE_ORDER as readonly string[]).indexOf(a[0]) -
          (GATE_ORDER as readonly string[]).indexOf(b[0]),
      );

  /** Gates the post already owns — locked, ticked, and still paid for. */
  const lockedEntries = useMemo(() => toEntries(post.gates), [post.gates]);
  /** Gates from an earlier edit that a moderator has not ruled on yet. */
  const pendingEntries = useMemo(() => toEntries(post.pending_gates), [post.pending_gates]);
  const hasPendingRequest = pendingEntries.length > 0;

  const newGates: PostGate[] = useMemo(
    () =>
      Object.entries(selectedGates)
        .filter(([, ids]) => ids.length > 0)
        .map(([action_type, targets]) => ({ action_type, targets })),
    [selectedGates],
  );
  const hasNewGates = newGates.length > 0;

  /**
   * The merged gate set the server will charge for: existing rows of **every**
   * status + the gates inside a pending request + the ones being ticked now
   * (`crud.edit_post`, section 3.6). Counts are summed per `action_type`
   * because that is what the server's `merge_gate_lists` union amounts to here
   * — the wire carries only counts for the first two sources, and a target that
   * appeared in two of them is rejected outright (400 «Гейт на эту цель уже
   * есть в посте») rather than merged.
   *
   * The target ids are irrelevant to the cost, so synthetic ones are used: the
   * real ids of a locked gate are not on the wire, and mixing them with the
   * picked ids could collide and silently under-count.
   */
  const mergedGates: PostGate[] = useMemo(() => {
    const totals: Record<string, number> = {};
    const add = (at: string, n: number) => {
      totals[at] = (totals[at] ?? 0) + n;
    };
    lockedEntries.forEach(([at, count]) => add(at, count));
    pendingEntries.forEach(([at, count]) => add(at, count));
    newGates.forEach((g) => add(g.action_type, g.targets.length));
    return Object.entries(totals).map(([action_type, count]) => ({
      action_type,
      targets: Array.from({ length: count }, (_, i) => i),
    }));
  }, [lockedEntries, pendingEntries, newGates]);

  const requiredSymbols = requiredSymbolsForGates(mergedGates);
  const meetsMinLength = charCount >= requiredSymbols;
  const progressPct = Math.min(100, Math.round((charCount / requiredSymbols) * 100));
  const isDirty = content !== post.content;
  const canSubmit = isDirty || hasNewGates;

  /** Which action types still have something to pick on this location. */
  const pickableTypes = useMemo(
    () => GATE_ORDER.filter((at) => (gateOptions[at]?.length ?? 0) > 0),
    [gateOptions],
  );
  const showGatePicker = canAddGates && !hasPendingRequest && pickableTypes.length > 0;

  const gateCost = (actionType: string) => GATE_COST[actionType] ?? DEFAULT_GATE_COST;
  const gateStyle = (actionType: string) => GATE_STYLE[actionType] ?? FALLBACK_GATE_STYLE;
  const gateLabel = (actionType: string) => GATE_LABEL[actionType] ?? actionType;

  const toggleGateTarget = (actionType: string, id: number) => {
    setSelectedGates((prev) => {
      const cur = prev[actionType] ?? [];
      const next = cur.includes(id) ? cur.filter((t) => t !== id) : [...cur, id];
      return { ...prev, [actionType]: next };
    });
  };

  const handleSave = async () => {
    if (saving) return;
    if (!meetsMinLength) {
      setError(
        `Для всех действий этого поста нужно минимум ${requiredSymbols} символов (сейчас: ${charCount}).`,
      );
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await onSave(post.post_id, content, newGates);
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
    if (isDirty || hasNewGates) {
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
          {(lockedEntries.length > 0 || pendingEntries.length > 0) && (
            <div className="flex flex-col gap-2">
              <span className="text-white/40 text-[10.5px] uppercase tracking-[0.06em]">
                Объявленные намерения
              </span>
              <div className="flex flex-wrap gap-1.5">
                {lockedEntries.map(([at, count]) => {
                  const style = gateStyle(at);
                  return (
                    <span
                      key={`locked-${at}`}
                      role="checkbox"
                      aria-checked="true"
                      aria-disabled="true"
                      aria-label={`${gateLabel(at)} — намерение уже объявлено и не может быть изменено`}
                      title="Уже объявленное намерение нельзя изменить или снять"
                      className={`flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-0.5 rounded-full border
                                  cursor-not-allowed select-none break-words ${style.activeCls}`}
                    >
                      <span aria-hidden="true">🔒</span>
                      <span aria-hidden="true">✓</span>
                      {style.icon} {gateLabel(at)}
                      {count > 1 ? ` ×${count}` : ''}
                      <span className="text-white/40">· {gateCost(at) * count} симв.</span>
                    </span>
                  );
                })}
                {pendingEntries.map(([at, count]) => (
                  <span
                    key={`pending-${at}`}
                    aria-label={`${gateLabel(at)} — заявка на намерение на рассмотрении`}
                    title="Заявка на это намерение уже отправлена и ждёт решения администратора"
                    className="flex items-center gap-1.5 text-[11px] font-medium px-2.5 py-0.5 rounded-full
                               border border-dashed border-gold/40 bg-gold/[0.06] text-gold/90
                               cursor-not-allowed select-none break-words"
                  >
                    <span aria-hidden="true">⏳</span>
                    {gateStyle(at).icon} {gateLabel(at)}
                    {count > 1 ? ` ×${count}` : ''}
                    <span className="text-white/40">· на рассмотрении · {gateCost(at) * count} симв.</span>
                  </span>
                ))}
              </div>
              <span className="text-white/35 text-[11px] break-words">
                Намерения нельзя изменить или снять при редактировании, и они по-прежнему
                оплачиваются длиной текста.
              </span>
            </div>
          )}

          {/* Phase B: add an intent forgotten at publication. It does NOT fire —
              it files a moderation request, and the player is told so here,
              before saving, not after. */}
          {showGatePicker && (
            <div className="flex flex-col gap-2.5 p-3 sm:p-3.5 rounded-card bg-white/[0.02] border border-white/[0.06]">
              <span className="text-xs font-medium text-white/70 break-words">
                Добавить забытое намерение{' '}
                <span className="text-white/40 font-normal">— увеличивает минимум символов</span>
              </span>
              <p className="text-gold/80 text-[11px] leading-relaxed break-words">
                Новое намерение <b>не сработает сразу</b>: оно уходит заявкой в модерацию и
                появится после одобрения администратором. До решения механика остаётся
                недоступной.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                {pickableTypes.map((at) => {
                  const opts = gateOptions[at] ?? [];
                  const sel = selectedGates[at] ?? [];
                  return (
                    <div
                      key={at}
                      className="flex flex-col gap-2 p-2.5 rounded-[10px] bg-white/[0.02] border border-white/[0.05]"
                    >
                      <span className="text-[11.5px] text-white/80 flex items-center gap-1.5 flex-wrap">
                        {gateStyle(at).icon} {gateLabel(at)}{' '}
                        <span className="text-white/35">· {gateCost(at)} симв./цель</span>
                      </span>
                      <div className="flex flex-wrap gap-1.5">
                        {opts.map((o) => {
                          const on = sel.includes(o.id);
                          return (
                            <button
                              key={o.id}
                              type="button"
                              aria-pressed={on}
                              onClick={() => toggleGateTarget(at, o.id)}
                              disabled={saving}
                              className={`text-[11.5px] px-3 py-1 rounded-full border transition-all duration-200 ease-site
                                          disabled:opacity-40 disabled:cursor-not-allowed break-words ${
                                            on
                                              ? gateStyle(at).activeCls
                                              : 'border-white/[0.16] text-white/60 hover:bg-white/5 hover:text-white/80'
                                          }`}
                            >
                              {on ? '✓ ' : ''}
                              {o.name}
                            </button>
                          );
                        })}
                      </div>
                      {sel.length > 0 && (
                        <span className="text-gold/70 text-[10.5px] break-words">
                          Появится после одобрения администратором
                        </span>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Why the picker is absent — never a silently missing control. */}
          {!showGatePicker && hasPendingRequest && (
            <p className="text-white/45 text-[11px] leading-relaxed break-words">
              По этому посту уже есть заявка на намерение — она на рассмотрении. Добавить ещё
              одно можно будет после решения администратора.
            </p>
          )}
          {!showGatePicker && !hasPendingRequest && !canAddGates && (
            <p className="text-white/45 text-[11px] leading-relaxed break-words">
              Добавить забытое намерение можно, только находясь в локации этого поста.
            </p>
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
              disabled={saving || !meetsMinLength || !canSubmit}
              title={
                !canSubmit
                  ? 'Текст не изменён'
                  : !meetsMinLength
                    ? `Минимум ${Math.max(MIN_POST_LENGTH, requiredSymbols)} символов`
                    : undefined
              }
            >
              {saving
                ? 'Сохраняем…'
                : hasNewGates
                  ? 'Сохранить и отправить заявку'
                  : 'Сохранить'}
            </button>
          </div>
        </motion.div>
      </div>

      {confirmCancelOpen && (
        <ConfirmDialog
          title="Отменить редактирование?"
          message={
            hasNewGates
              ? 'Внесённые правки не будут сохранены, а заявка на новое намерение не будет отправлена.'
              : 'Внесённые правки не будут сохранены, а исходный текст поста останется прежним.'
          }
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
