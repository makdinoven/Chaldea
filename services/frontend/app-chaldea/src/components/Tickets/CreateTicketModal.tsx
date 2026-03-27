import { useState, useCallback, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { Paperclip } from 'react-feather';
import { uploadTicketAttachment } from '../../api/ticketApi';
import type { TicketCategory, CreateTicketPayload } from '../../types/ticket';
import toast from 'react-hot-toast';

interface CreateTicketModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: CreateTicketPayload) => void;
  isLoading: boolean;
}

const CATEGORY_OPTIONS: { value: TicketCategory; label: string }[] = [
  { value: 'bug', label: 'Баг / Ошибка' },
  { value: 'question', label: 'Вопрос' },
  { value: 'suggestion', label: 'Предложение' },
  { value: 'complaint', label: 'Жалоба' },
  { value: 'other', label: 'Другое' },
];

const CreateTicketModal = ({ isOpen, onClose, onSubmit, isLoading }: CreateTicketModalProps) => {
  const [category, setCategory] = useState<TicketCategory>('bug');
  const [subject, setSubject] = useState('');
  const [content, setContent] = useState('');
  const [attachmentUrl, setAttachmentUrl] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';

    setUploading(true);
    try {
      const response = await uploadTicketAttachment(file);
      setAttachmentUrl(response.data.image_url);
      toast.success('Файл загружен');
    } catch {
      toast.error('Не удалось загрузить файл. Допустимы только изображения.');
    } finally {
      setUploading(false);
    }
  }, []);

  const handleSubmit = useCallback(() => {
    const trimSubject = subject.trim();
    const trimContent = content.trim();

    if (!trimSubject) {
      toast.error('Укажите тему тикета');
      return;
    }
    if (trimSubject.length > 255) {
      toast.error('Тема не может быть длиннее 255 символов');
      return;
    }
    if (!trimContent) {
      toast.error('Напишите сообщение');
      return;
    }
    if (trimContent.length > 5000) {
      toast.error('Сообщение не может быть длиннее 5000 символов');
      return;
    }

    onSubmit({
      subject: trimSubject,
      category,
      content: trimContent,
      attachment_url: attachmentUrl,
    });
  }, [subject, content, category, attachmentUrl, onSubmit]);

  const handleClose = useCallback(() => {
    if (isLoading) return;
    setSubject('');
    setContent('');
    setCategory('bug');
    setAttachmentUrl(null);
    onClose();
  }, [isLoading, onClose]);

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="modal-overlay" onClick={handleClose}>
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="w-full max-w-lg mx-4 rounded-card border border-white/10 bg-black/50 backdrop-blur-md p-6 sm:p-8"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="gold-text text-2xl font-medium uppercase mb-6">
              Создать тикет
            </h2>

            {/* Category */}
            <div className="mb-4">
              <label className="text-white/60 text-xs font-medium uppercase tracking-wider mb-1.5 block">
                Категория
              </label>
              <select
                value={category}
                onChange={(e) => setCategory(e.target.value as TicketCategory)}
                className="w-full bg-white/[0.06] border border-white/10 rounded-lg px-3 py-2 text-white text-sm focus:border-site-blue outline-none transition-colors duration-200 ease-site"
              >
                {CATEGORY_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value} className="bg-site-dark text-white">
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>

            {/* Subject */}
            <div className="mb-4">
              <label className="text-white/60 text-xs font-medium uppercase tracking-wider mb-1.5 block">
                Тема
              </label>
              <input
                type="text"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder="Краткое описание проблемы"
                maxLength={255}
                className="input-underline w-full text-sm"
              />
              <span className="text-white/30 text-xs mt-1 block">{subject.length}/255</span>
            </div>

            {/* Content */}
            <div className="mb-4">
              <label className="text-white/60 text-xs font-medium uppercase tracking-wider mb-1.5 block">
                Сообщение
              </label>
              <textarea
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder="Подробно опишите проблему или вопрос..."
                maxLength={5000}
                rows={5}
                className="textarea-bordered w-full text-sm resize-none gold-scrollbar"
              />
              <span className="text-white/30 text-xs mt-1 block">{content.length}/5000</span>
            </div>

            {/* Attachment */}
            <div className="mb-6">
              {attachmentUrl ? (
                <div className="flex items-center gap-3">
                  <img
                    src={attachmentUrl}
                    alt="Вложение"
                    className="h-16 w-16 object-cover rounded border border-white/10"
                  />
                  <button
                    onClick={() => setAttachmentUrl(null)}
                    className="text-white/40 hover:text-site-red text-xs transition-colors duration-200 ease-site cursor-pointer"
                  >
                    Удалить вложение
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => fileInputRef.current?.click()}
                  disabled={uploading}
                  className="flex items-center gap-2 text-white/40 hover:text-site-blue text-sm transition-colors duration-200 ease-site cursor-pointer disabled:opacity-30"
                >
                  <Paperclip size={16} />
                  {uploading ? 'Загрузка...' : 'Прикрепить изображение'}
                </button>
              )}
              <input
                ref={fileInputRef}
                type="file"
                accept="image/jpeg,image/png,image/webp,image/gif"
                onChange={handleFileChange}
                className="hidden"
              />
            </div>

            {/* Actions */}
            <div className="flex gap-4 justify-end">
              <button
                onClick={handleClose}
                disabled={isLoading}
                className="btn-line !px-4 !py-2 !text-sm"
              >
                Отмена
              </button>
              <button
                onClick={handleSubmit}
                disabled={isLoading || uploading}
                className="btn-blue !px-4 !py-2 !text-sm disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {isLoading ? 'Создание...' : 'Создать'}
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};

export default CreateTicketModal;
