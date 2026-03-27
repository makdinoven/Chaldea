import { useState, useCallback, useRef } from 'react';
import { Paperclip } from 'react-feather';
import { uploadTicketAttachment } from '../../api/ticketApi';
import toast from 'react-hot-toast';

interface TicketInputProps {
  onSend: (content: string, attachmentUrl: string | null) => void;
  disabled?: boolean;
  sending?: boolean;
}

const MAX_LENGTH = 5000;

const TicketInput = ({ onSend, disabled = false, sending = false }: TicketInputProps) => {
  const [text, setText] = useState('');
  const [attachmentUrl, setAttachmentUrl] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleFileChange = useCallback(async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Reset file input so user can re-select the same file
    e.target.value = '';

    setUploading(true);
    try {
      const response = await uploadTicketAttachment(file);
      setAttachmentUrl(response.data.image_url);
      toast.success('Файл загружен');
    } catch {
      toast.error('Не удалось загрузить файл. Допустимы только изображения (JPEG, PNG, WebP, GIF).');
    } finally {
      setUploading(false);
    }
  }, []);

  const handleSubmit = useCallback(() => {
    const content = text.trim();
    if (!content || disabled || sending || uploading) return;

    onSend(content, attachmentUrl);
    setText('');
    setAttachmentUrl(null);
  }, [text, disabled, sending, uploading, attachmentUrl, onSend]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit],
  );

  const isOverLimit = text.length > MAX_LENGTH;

  return (
    <div className="px-3 py-2 border-t border-white/10">
      {/* Attachment preview */}
      {attachmentUrl && (
        <div className="mb-2 flex items-center gap-2">
          <img
            src={attachmentUrl}
            alt="Вложение"
            className="h-12 w-12 object-cover rounded border border-white/10"
          />
          <button
            onClick={() => setAttachmentUrl(null)}
            className="text-white/40 hover:text-site-red text-xs transition-colors duration-200 ease-site cursor-pointer"
          >
            Удалить
          </button>
        </div>
      )}

      <textarea
        ref={textareaRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={disabled ? 'Тикет закрыт' : 'Написать сообщение...'}
        maxLength={MAX_LENGTH}
        rows={3}
        disabled={disabled}
        className="input-underline w-full text-sm !py-2 resize-none gold-scrollbar disabled:opacity-40 disabled:cursor-not-allowed"
      />

      <div className="flex items-center justify-between mt-2">
        <div className="flex items-center gap-3">
          {/* File upload */}
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled || uploading}
            className="text-white/40 hover:text-site-blue transition-colors duration-200 ease-site cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed"
            title="Прикрепить изображение"
          >
            <Paperclip size={18} />
          </button>
          <input
            ref={fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/gif"
            onChange={handleFileChange}
            className="hidden"
          />

          {/* Character count */}
          <span className={`text-xs ${isOverLimit ? 'text-site-red' : 'text-white/30'}`}>
            {text.length}/{MAX_LENGTH}
          </span>

          {uploading && (
            <span className="text-xs text-white/40">Загрузка...</span>
          )}
        </div>

        {/* Send button */}
        <button
          onClick={handleSubmit}
          disabled={!text.trim() || disabled || sending || isOverLimit || uploading}
          className="btn-blue !px-3 !py-1.5 !text-sm disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {sending ? 'Отправка...' : 'Отправить'}
        </button>
      </div>
    </div>
  );
};

export default TicketInput;
