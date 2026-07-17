import { useState, useRef, useEffect, useMemo } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Edit3 } from 'react-feather';
import toast from 'react-hot-toast';
import WysiwygEditor from '../../CommonComponents/WysiwygEditor/WysiwygEditor';
import SpellCheckPanel from '../../CommonComponents/SpellCheckPanel/SpellCheckPanel';
import { useSpellCheck } from '../../../hooks/useSpellCheck';
import { replaceWordInHtml } from '../../../api/spellcheck';
import { useAppSelector } from '../../../redux/store';
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
  gathering: 'Сбор ресурсов',
  dungeon: 'Вход в подземелье',
};
// FEAT-152: per-action visual accents for the gate grid (mock language).
const GATE_STYLE: Record<string, { icon: string; activeCls: string }> = {
  combat: { icon: '⚔', activeCls: 'border-stat-hp/40 bg-stat-hp/10 text-stat-hp' },
  npc_dialogue: { icon: '💬', activeCls: 'border-site-blue/40 bg-site-blue/10 text-site-blue' },
  gathering: { icon: '⛏', activeCls: 'border-stat-energy/40 bg-stat-energy/10 text-stat-energy' },
  dungeon: { icon: '🏰', activeCls: 'border-rarity-epic/40 bg-rarity-epic/10 text-rarity-epic' },
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
  /** Location name for the collapsed placeholder / «пишет из …» line (FEAT-152). */
  locationName?: string;
}

const stripHtmlTags = (html: string) => html.replace(/<[^>]*>/g, '').trim();

const isContentEmpty = (html: string) => stripHtmlTags(html).length === 0;

const PostCreateForm = ({ onSubmit, onSubmitAsNpc, disabled, isStaff, npcs = [], gateOptions = {}, locationName }: PostCreateFormProps) => {
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

  const character = useAppSelector((state) => state.user.character);

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
  const progressPct = Math.min(100, Math.round((charCount / requiredSymbols) * 100));

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

  // Author shown in the expanded header — the NPC in staff NPC-mode,
  // otherwise the player's character.
  const authorName = npcMode && selectedNpc ? selectedNpc.name : character?.name ?? null;
  const authorAvatar = npcMode && selectedNpc ? selectedNpc.avatar : character?.avatar ?? null;

  const renderAvatar = (sizeCls: string) => (
    <div className={`gold-outline relative ${sizeCls} rounded-full overflow-hidden bg-black/40 shrink-0`}>
      {authorAvatar ? (
        <img src={authorAvatar} alt={authorName ?? ''} className="w-full h-full object-cover" />
      ) : (
        <div className="w-full h-full flex items-center justify-center text-white/20">
          <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
          </svg>
        </div>
      )}
    </div>
  );

  // No overflow-hidden on the card — the editor's toolbar dropdowns must be
  // able to extend past the card edge.
  return (
    <div
      ref={formRef}
      className="bg-site-bg backdrop-blur-sm rounded-card border border-gold-dark/20 shadow-card"
    >
      <AnimatePresence mode="wait">
        {!isEditorOpen ? (
          /* Collapsed state — avatar + placeholder + «Написать пост» (mock) */
          <motion.button
            key="toggle-placeholder"
            type="button"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={() => !disabled && setIsEditorOpen(true)}
            className={`w-full flex items-center gap-3 sm:gap-3.5 px-4 py-3.5 sm:px-5 sm:py-4 rounded-card text-left transition-colors duration-200 ease-site ${
              disabled
                ? 'opacity-60 cursor-not-allowed'
                : 'hover:bg-white/[0.03] cursor-pointer'
            }`}
          >
            {renderAvatar('w-10 h-10 sm:w-11 sm:h-11')}
            <span className="flex-1 min-w-0 truncate text-white/40 text-sm">
              {character?.name && locationName
                ? `Опишите действия ${character.name} в «${locationName}»…`
                : 'Написать пост…'}
            </span>
            <span className="hidden sm:inline-flex items-center gap-2 btn-blue !py-2 !px-4 !text-xs pointer-events-none shrink-0">
              <Edit3 size={14} />
              Написать пост
            </span>
            <Edit3 size={16} className="sm:hidden text-white/40 shrink-0" />
          </motion.button>
        ) : (
          /* Expanded editor */
          <motion.div
            key="editor-form"
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="p-4 sm:p-5 flex flex-col gap-4"
          >
            {/* Author header: avatar + name + «пишет из …» */}
            <div className="flex items-center gap-3">
              {renderAvatar('w-10 h-10')}
              <div className="flex flex-col gap-0.5 min-w-0">
                <span className="text-white text-sm font-medium truncate">
                  {authorName ?? 'Ваш персонаж'}
                </span>
                {locationName && (
                  <span className="text-site-blue text-[11px] flex items-center gap-1 truncate">
                    <svg xmlns="http://www.w3.org/2000/svg" className="w-[11px] h-[11px] shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" />
                      <circle cx="12" cy="10" r="3" />
                    </svg>
                    пишет из «{locationName}»
                  </span>
                )}
              </div>
            </div>

            {/* NPC mode toggle for staff */}
            {isStaff && npcs.length > 0 && (
              <div className="flex flex-col gap-2 p-3 rounded-card bg-white/[0.02] border border-white/[0.06]">
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
                    className="bg-black/60 border border-white/20 text-white text-sm rounded-[10px] px-3 py-2
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
              </div>
            )}

            {/* FEAT-145 v2: declare intent gates — pick targets per action. Each
                selected target adds to the required post length. */}
            {!npcMode && GATE_ORDER.some((t) => (gateOptions[t]?.length ?? 0) > 0) && (
              <div className="flex flex-col gap-2.5 p-3.5 rounded-card bg-white/[0.02] border border-white/[0.06]">
                <span className="text-xs font-medium text-white/70">
                  Заявить действие в посту{' '}
                  <span className="text-white/40 font-normal">— по желанию, увеличивает минимум символов</span>
                </span>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
                  {GATE_ORDER.map((at) => {
                    const opts = gateOptions[at] ?? [];
                    if (opts.length === 0) return null;
                    const sel = selectedGates[at] ?? [];
                    return (
                      <div key={at} className="flex flex-col gap-2 p-2.5 rounded-[10px] bg-white/[0.02] border border-white/[0.05]">
                        <span className="text-[11.5px] text-white/80 flex items-center gap-1.5 flex-wrap">
                          {GATE_STYLE[at].icon} {GATE_LABEL[at]}{' '}
                          <span className="text-white/35">· {GATE_COST[at]} симв./цель</span>
                        </span>
                        <div className="flex flex-wrap gap-1.5">
                          {opts.map((o) => {
                            const on = sel.includes(o.id);
                            return (
                              <button
                                key={o.id}
                                type="button"
                                onClick={() => toggleGateTarget(at, o.id)}
                                className={`text-[11.5px] px-3 py-1 rounded-full border transition-all duration-200 ease-site ${
                                  on
                                    ? GATE_STYLE[at].activeCls
                                    : 'border-white/[0.16] text-white/60 hover:bg-white/5 hover:text-white/80'
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

            {/* Character counter + XP preview + progress bar (only in non-NPC mode) */}
            {!npcMode && (
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs sm:text-[12.5px]">
                <span className={`font-medium ${meetsMinLength ? 'text-stat-energy' : 'text-site-red'}`}>
                  {charCount} / {requiredSymbols} символов
                </span>
                <span className="text-white/50">
                  {meetsMinLength
                    ? `≈ ${xpPreview} XP за пост`
                    : `Минимум ${requiredSymbols} символов`}
                </span>
                <div className="flex-1 min-w-[120px] h-[5px] rounded-full bg-white/10 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-200 ${
                      meetsMinLength ? 'bg-stat-energy' : 'bg-site-red/80'
                    }`}
                    style={{ width: `${progressPct}%` }}
                  />
                </div>
              </div>
            )}

            {/* Actions: spell-check left, cancel / submit right (mock) */}
            <div className="flex flex-col sm:flex-row sm:items-center gap-2.5 sm:gap-3">
              {/* Min length hint on mobile when submit is blocked */}
              {!npcMode && !meetsMinLength && charCount > 0 && (
                <span className="text-xs text-site-red sm:hidden">
                  Ещё {requiredSymbols - charCount} символов до минимума
                </span>
              )}
              <button
                type="button"
                className="flex items-center justify-center gap-2 px-4 py-2 rounded-[10px] border border-white/[0.15] text-white/70 text-xs font-medium
                           hover:border-site-blue hover:text-site-blue transition-colors duration-200 ease-site
                           disabled:opacity-30 disabled:cursor-not-allowed"
                onClick={handleSpellCheck}
                disabled={isContentEmpty(content) || spellCheck.loading}
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 11l3 3L22 4" />
                  <path strokeLinecap="round" strokeLinejoin="round" d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
                </svg>
                {spellCheck.loading ? 'Проверяю...' : 'Проверить правописание'}
              </button>
              <div className="flex flex-wrap justify-end gap-2.5 sm:ml-auto">
                <button
                  type="button"
                  className="px-5 py-2 rounded-[10px] border border-white/[0.15] text-white/70 text-xs font-medium
                             hover:border-site-red hover:text-site-red transition-colors duration-200 ease-site"
                  onClick={resetForm}
                >
                  Отмена
                </button>
                <button
                  className="btn-blue !py-2 !px-6 !text-sm inline-flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                  onClick={handleSubmit}
                  disabled={isSubmitDisabled}
                  title={!npcMode && !meetsMinLength ? `Минимум ${MIN_POST_LENGTH} символов` : undefined}
                >
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <line x1="22" y1="2" x2="11" y2="13" strokeLinecap="round" strokeLinejoin="round" />
                    <polygon points="22 2 15 22 11 13 2 9 22 2" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
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
