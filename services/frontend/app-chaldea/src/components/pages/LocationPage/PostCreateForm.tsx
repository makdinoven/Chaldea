import { useState, useRef, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Edit3 } from 'react-feather';
import toast from 'react-hot-toast';
import WysiwygEditor from '../../CommonComponents/WysiwygEditor/WysiwygEditor';
import SpellCheckPanel from '../../CommonComponents/SpellCheckPanel/SpellCheckPanel';
import { useSpellCheck } from '../../../hooks/useSpellCheck';
import { replaceWordInHtml } from '../../../api/spellcheck';
import { NpcInLocation } from './types';

const MIN_POST_LENGTH = 300;
// FEAT-145 v2: symbol cost per gate target.
const GATE_COST: Record<string, number> = {
  combat: 200,
  npc_dialogue: 500,
  gathering: 500,
  dungeon: 500,
};
const GATE_LABEL: Record<string, string> = {
  combat: 'Нападение на мобов',
  npc_dialogue: 'Диалог с НПС',
  gathering: 'Сбор',
  dungeon: 'Вход в подземелье',
};
const GATE_ORDER = ['combat', 'npc_dialogue', 'gathering', 'dungeon'] as const;

export interface GateOption {
  id: number;
  name: string;
}
export type GateOptions = Partial<Record<string, GateOption[]>>;

export interface PostGate {
  action_type: string;
  targets: number[];
}

interface PostCreateFormProps {
  onSubmit: (content: string, gates?: PostGate[]) => Promise<void>;
  onSubmitAsNpc?: (npcId: number, content: string) => Promise<void>;
  disabled?: boolean;
  isStaff?: boolean;
  npcs?: NpcInLocation[];
  // Available gate targets on this location, keyed by action_type.
  gateOptions?: GateOptions;
}

const stripHtmlTags = (html: string) => html.replace(/<[^>]*>/g, '').trim();

const isContentEmpty = (html: string) => stripHtmlTags(html).length === 0;

const PostCreateForm = ({ onSubmit, onSubmitAsNpc, disabled, isStaff, npcs = [], gateOptions = {} }: PostCreateFormProps) => {
  const [content, setContent] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [editorKey, setEditorKey] = useState(0);
  const [npcMode, setNpcMode] = useState(false);
  const [selectedNpcId, setSelectedNpcId] = useState<number | null>(null);
  // FEAT-145 v2: multiple intent gates — action_type → chosen target ids.
  const [selectedGates, setSelectedGates] = useState<Record<string, number[]>>({});
  const formRef = useRef<HTMLDivElement>(null);
  const spellCheck = useSpellCheck();

  const charCount = useMemo(() => stripHtmlTags(content).length, [content]);
  const activeGates: PostGate[] = GATE_ORDER
    .filter((t) => (selectedGates[t]?.length ?? 0) > 0)
    .map((t) => ({ action_type: t, targets: selectedGates[t] }));
  const requiredSymbols = Math.max(
    MIN_POST_LENGTH,
    activeGates.reduce((sum, g) => sum + GATE_COST[g.action_type] * g.targets.length, 0),
  );
  const meetsMinLength = charCount >= requiredSymbols;
  const xpPreview = charCount >= MIN_POST_LENGTH ? Math.round(charCount / 100) : 0;

  const toggleGateTarget = (actionType: string, id: number) => {
    setSelectedGates((prev) => {
      const cur = prev[actionType] ?? [];
      const next = cur.includes(id) ? cur.filter((t) => t !== id) : [...cur, id];
      return { ...prev, [actionType]: next };
    });
  };

  useEffect(() => {
    if (!isEditorOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (formRef.current && !formRef.current.contains(e.target as Node)) {
        if (isContentEmpty(content)) {
          setIsEditorOpen(false);
          setNpcMode(false);
          setSelectedNpcId(null);
        }
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isEditorOpen, content]);

  const handleSubmit = async () => {
    if (isContentEmpty(content) || submitting) return;

    if (npcMode) {
      if (!selectedNpcId || !onSubmitAsNpc) return;
      setSubmitting(true);
      try {
        await onSubmitAsNpc(selectedNpcId, content);
        setContent('');
        setEditorKey((k) => k + 1);
        setIsEditorOpen(false);
        setNpcMode(false);
        setSelectedNpcId(null);
      } finally {
        setSubmitting(false);
      }
      return;
    }

    if (!meetsMinLength) {
      toast.error(`Для выбранных действий нужно минимум ${requiredSymbols} символов (сейчас: ${charCount})`);
      return;
    }

    setSubmitting(true);
    try {
      await onSubmit(content, activeGates);
      setContent('');
      setEditorKey((k) => k + 1);
      setIsEditorOpen(false);
      setSelectedGates({});
    } finally {
      setSubmitting(false);
    }
  };

  const handleSpellCheck = async () => {
    const plainText = stripHtmlTags(content);
    if (!plainText) return;
    try {
      await spellCheck.runCheck(plainText);
    } catch {
      toast.error('Сервис проверки правописания недоступен');
    }
  };

  const handleApplySuggestion = (errorIndex: number, suggestion: string) => {
    const error = spellCheck.errors[errorIndex];
    if (!error) return;
    const updated = replaceWordInHtml(content, error.pos, error.len, suggestion);
    setContent(updated);
    setEditorKey((k) => k + 1);
    spellCheck.dismissError(errorIndex);
  };

  const resetForm = () => {
    setIsEditorOpen(false);
    setContent('');
    setEditorKey((k) => k + 1);
    setNpcMode(false);
    setSelectedNpcId(null);
    setSelectedGates({});
    spellCheck.reset();
  };

  const selectedNpc = npcs.find((n) => n.id === selectedNpcId);

  const isSubmitDisabled = npcMode
    ? submitting || isContentEmpty(content) || !selectedNpcId
    : submitting || isContentEmpty(content) || !meetsMinLength;

  return (
    <div ref={formRef}>
      <AnimatePresence mode="wait">
        {!isEditorOpen ? (
          <motion.div
            key="toggle-placeholder"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            className="bg-black/60 px-4 py-3 flex items-center gap-3 cursor-pointer hover:bg-black/70 transition-colors rounded-card"
            onClick={() => !disabled && setIsEditorOpen(true)}
          >
            <Edit3 size={16} className="text-white/30 flex-shrink-0" />
            <span className="text-white/30 text-sm select-none">Написать пост...</span>
          </motion.div>
        ) : (
          <motion.div
            key="editor-form"
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="bg-black/60 p-5 flex flex-col gap-3 rounded-card"
          >
            {/* NPC mode toggle for staff */}
            {isStaff && npcs.length > 0 && (
              <div className="flex flex-col gap-2">
                <label className="flex items-center gap-2 cursor-pointer text-sm text-white/70">
                  <input
                    type="checkbox"
                    checked={npcMode}
                    onChange={(e) => {
                      setNpcMode(e.target.checked);
                      if (!e.target.checked) setSelectedNpcId(null);
                    }}
                    className="accent-gold w-4 h-4"
                  />
                  Написать от НПС
                </label>

                {npcMode && (
                  <select
                    value={selectedNpcId ?? ''}
                    onChange={(e) => setSelectedNpcId(e.target.value ? Number(e.target.value) : null)}
                    className="bg-black/60 border border-white/20 text-white text-sm rounded px-3 py-2
                               focus:border-gold focus:outline-none transition-colors"
                  >
                    <option value="">Выберите НПС...</option>
                    {npcs.map((npc) => (
                      <option key={npc.id} value={npc.id}>
                        {npc.name} {npc.npc_role ? `(${npc.npc_role})` : ''} — ур. {npc.level}
                      </option>
                    ))}
                  </select>
                )}

                {npcMode && selectedNpc && (
                  <div className="flex items-center gap-2 text-xs text-white/50">
                    {selectedNpc.avatar && (
                      <img
                        src={selectedNpc.avatar}
                        alt={selectedNpc.name}
                        className="w-6 h-6 rounded-full object-cover"
                      />
                    )}
                    <span>Пост будет от: <span className="text-gold">{selectedNpc.name}</span></span>
                  </div>
                )}
              </div>
            )}

            {/* FEAT-145 v2: declare intent gates — pick targets per action. Each
                selected target adds to the required post length. */}
            {!npcMode && GATE_ORDER.some((t) => (gateOptions[t]?.length ?? 0) > 0) && (
              <div className="flex flex-col gap-2">
                <span className="text-sm text-white/70">
                  Действия в этом посту (по желанию):
                </span>
                {GATE_ORDER.map((at) => {
                  const opts = gateOptions[at] ?? [];
                  if (opts.length === 0) return null;
                  const sel = selectedGates[at] ?? [];
                  return (
                    <div key={at} className="bg-white/[0.03] rounded-lg p-3 flex flex-col gap-1.5">
                      <span className="text-white/80 text-xs font-medium">
                        {GATE_LABEL[at]}{' '}
                        <span className="text-white/40">· {GATE_COST[at]} симв./цель</span>
                      </span>
                      <div className="flex flex-wrap gap-2">
                        {opts.map((o) => {
                          const on = sel.includes(o.id);
                          return (
                            <button
                              key={o.id}
                              type="button"
                              onClick={() => toggleGateTarget(at, o.id)}
                              className={`text-xs px-2.5 py-1 rounded-full border transition ${
                                on
                                  ? 'border-gold bg-gold/20 text-gold'
                                  : 'border-white/20 text-white/70 hover:bg-white/5'
                              }`}
                            >
                              {o.name}
                            </button>
                          );
                        })}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            <WysiwygEditor
              key={editorKey}
              content={content}
              onChange={setContent}
              enableArchiveLinks
            />

            {/* Spell-check panel */}
            <SpellCheckPanel
              errors={spellCheck.errors}
              loading={spellCheck.loading}
              checked={spellCheck.checked}
              onApplySuggestion={handleApplySuggestion}
              onDismissError={spellCheck.dismissError}
            />

            {/* Character counter + XP preview (only in non-NPC mode) */}
            {!npcMode && (
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs sm:text-sm">
                <span className={meetsMinLength ? 'text-stat-energy' : 'text-site-red'}>
                  {charCount} / {requiredSymbols} символов
                </span>
                <span className="text-white/50">
                  {meetsMinLength
                    ? `~${xpPreview} XP`
                    : `Минимум ${requiredSymbols} символов`}
                </span>
              </div>
            )}

            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
              {/* Min length hint on mobile when submit is blocked */}
              {!npcMode && !meetsMinLength && charCount > 0 && (
                <span className="text-xs text-site-red sm:hidden">
                  Ещё {requiredSymbols - charCount} символов до минимума
                </span>
              )}
              <div className="flex flex-wrap justify-end gap-3 sm:ml-auto">
                <button
                  type="button"
                  className="btn-line !py-2 !px-6 !text-sm disabled:opacity-30 disabled:cursor-not-allowed"
                  onClick={handleSpellCheck}
                  disabled={isContentEmpty(content) || spellCheck.loading}
                >
                  {spellCheck.loading ? 'Проверяю...' : 'Проверить правописание'}
                </button>
                <button
                  className="btn-line !py-2 !px-6 !text-sm"
                  onClick={resetForm}
                >
                  Отмена
                </button>
                <button
                  className="btn-blue !py-2 !px-6 !text-sm disabled:opacity-50 disabled:cursor-not-allowed"
                  onClick={handleSubmit}
                  disabled={isSubmitDisabled}
                  title={!npcMode && !meetsMinLength ? `Минимум ${MIN_POST_LENGTH} символов` : undefined}
                >
                  {submitting ? 'Отправка...' : npcMode ? 'Опубликовать от НПС' : 'Опубликовать'}
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default PostCreateForm;
