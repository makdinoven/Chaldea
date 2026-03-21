import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Edit3 } from 'react-feather';
import WysiwygEditor from '../../CommonComponents/WysiwygEditor/WysiwygEditor';
import { NpcInLocation } from './types';

interface PostCreateFormProps {
  onSubmit: (content: string) => Promise<void>;
  onSubmitAsNpc?: (npcId: number, content: string) => Promise<void>;
  disabled?: boolean;
  isStaff?: boolean;
  npcs?: NpcInLocation[];
}

const isContentEmpty = (html: string) => {
  const stripped = html.replace(/<[^>]*>/g, '').trim();
  return stripped.length === 0;
};

const PostCreateForm = ({ onSubmit, onSubmitAsNpc, disabled, isStaff, npcs = [] }: PostCreateFormProps) => {
  const [content, setContent] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [editorKey, setEditorKey] = useState(0);
  const [npcMode, setNpcMode] = useState(false);
  const [selectedNpcId, setSelectedNpcId] = useState<number | null>(null);
  const formRef = useRef<HTMLDivElement>(null);

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

  const resetForm = () => {
    setIsEditorOpen(false);
    setContent('');
    setEditorKey((k) => k + 1);
    setNpcMode(false);
    setSelectedNpcId(null);
  };

  const selectedNpc = npcs.find((n) => n.id === selectedNpcId);

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
            className="bg-black/40 px-4 py-3 flex items-center gap-3 cursor-pointer hover:bg-black/50 transition-colors rounded-card"
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
            className="bg-black/40 p-5 flex flex-col gap-3 rounded-card"
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
            />
            <div className="flex justify-end gap-3">
              <button
                className="btn-line !py-2 !px-6 !text-sm"
                onClick={resetForm}
              >
                Отмена
              </button>
              <button
                className="btn-blue !py-2 !px-6 !text-sm"
                onClick={handleSubmit}
                disabled={submitting || isContentEmpty(content) || (npcMode && !selectedNpcId)}
              >
                {submitting ? 'Отправка...' : npcMode ? 'Опубликовать от НПС' : 'Опубликовать'}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default PostCreateForm;
