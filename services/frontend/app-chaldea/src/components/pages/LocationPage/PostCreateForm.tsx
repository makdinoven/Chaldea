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

interface PostCreateFormProps {
  onSubmit: (content: string) => Promise<void>;
  onSubmitAsNpc?: (npcId: number, content: string) => Promise<void>;
  disabled?: boolean;
  isStaff?: boolean;
  npcs?: NpcInLocation[];
}

const stripHtmlTags = (html: string) => html.replace(/<[^>]*>/g, '').trim();

const isContentEmpty = (html: string) => stripHtmlTags(html).length === 0;

const PostCreateForm = ({ onSubmit, onSubmitAsNpc, disabled, isStaff, npcs = [] }: PostCreateFormProps) => {
  const [content, setContent] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [editorKey, setEditorKey] = useState(0);
  const [npcMode, setNpcMode] = useState(false);
  const [selectedNpcId, setSelectedNpcId] = useState<number | null>(null);
  const formRef = useRef<HTMLDivElement>(null);
  const spellCheck = useSpellCheck();

  const charCount = useMemo(() => stripHtmlTags(content).length, [content]);
  const meetsMinLength = charCount >= MIN_POST_LENGTH;
  const xpPreview = meetsMinLength ? Math.round(charCount / 100) : 0;

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
      toast.error(`Минимальная длина поста — ${MIN_POST_LENGTH} символов (сейчас: ${charCount})`);
      return;
    }

    setSubmitting(true);
    try {
      await onSubmit(content);
      setContent('');
      setEditorKey((k) => k + 1);
      setIsEditorOpen(false);
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
                  {charCount} / {MIN_POST_LENGTH} символов
                </span>
                <span className="text-white/50">
                  {meetsMinLength
                    ? `~${xpPreview} XP`
                    : `Минимум ${MIN_POST_LENGTH} символов`}
                </span>
              </div>
            )}

            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
              {/* Min length hint on mobile when submit is blocked */}
              {!npcMode && !meetsMinLength && charCount > 0 && (
                <span className="text-xs text-site-red sm:hidden">
                  Ещё {MIN_POST_LENGTH - charCount} символов до минимума
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
