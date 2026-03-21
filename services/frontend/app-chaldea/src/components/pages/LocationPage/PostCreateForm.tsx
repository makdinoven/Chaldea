import { useState, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Edit3 } from 'react-feather';
import WysiwygEditor from '../../CommonComponents/WysiwygEditor/WysiwygEditor';

interface PostCreateFormProps {
  onSubmit: (content: string) => Promise<void>;
  disabled?: boolean;
}

const isContentEmpty = (html: string) => {
  const stripped = html.replace(/<[^>]*>/g, '').trim();
  return stripped.length === 0;
};

const PostCreateForm = ({ onSubmit, disabled }: PostCreateFormProps) => {
  const [content, setContent] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const [editorKey, setEditorKey] = useState(0);
  const formRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isEditorOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (formRef.current && !formRef.current.contains(e.target as Node)) {
        if (isContentEmpty(content)) {
          setIsEditorOpen(false);
        }
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isEditorOpen, content]);

  const handleSubmit = async () => {
    if (isContentEmpty(content) || submitting) return;

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
            <WysiwygEditor
              key={editorKey}
              content={content}
              onChange={setContent}
            />
            <div className="flex justify-end gap-3">
              <button
                className="btn-line !py-2 !px-6 !text-sm"
                onClick={() => {
                  setIsEditorOpen(false);
                  setContent('');
                  setEditorKey((k) => k + 1);
                }}
              >
                Отмена
              </button>
              <button
                className="btn-blue !py-2 !px-6 !text-sm"
                onClick={handleSubmit}
                disabled={submitting || isContentEmpty(content)}
              >
                {submitting ? 'Отправка...' : 'Опубликовать'}
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default PostCreateForm;
