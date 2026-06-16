import { useState, useCallback, useEffect, useRef } from 'react';
import { X } from 'react-feather';
import type { PrivateMessage } from '../../types/messenger';

interface MessageInputProps {
  onSend: (content: string) => void;
  onTyping?: () => void;
  disabled?: boolean;
  sending?: boolean;
  replyTo: PrivateMessage | null;
  editingMessage: PrivateMessage | null;
  quoteText: string | null;
  onClearReply: () => void;
  onClearEdit: () => void;
  onEditSubmit: (messageId: number, content: string) => void;
  onQuoteInserted: () => void;
}

const MAX_LENGTH = 2000;
// Matches the backend messenger rate limit (1s) so we block the button locally
// instead of letting the user hit a 429-style error.
const SEND_COOLDOWN_MS = 1000;

const truncate = (text: string, maxLen: number): string => {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + '...';
};

const MessageInput = ({
  onSend,
  onTyping,
  disabled = false,
  sending = false,
  replyTo,
  editingMessage,
  quoteText,
  onClearReply,
  onClearEdit,
  onEditSubmit,
  onQuoteInserted,
}: MessageInputProps) => {
  const [text, setText] = useState('');
  const [onCooldown, setOnCooldown] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const cooldownTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const lastTypingSentRef = useRef(0);

  // Throttle "typing" signals to at most one per 3s while there is content.
  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLTextAreaElement>) => {
      setText(e.target.value);
      if (onTyping && e.target.value.trim()) {
        const now = Date.now();
        if (now - lastTypingSentRef.current > 3000) {
          lastTypingSentRef.current = now;
          onTyping();
        }
      }
    },
    [onTyping],
  );

  // Clear any pending cooldown timer on unmount.
  useEffect(() => () => {
    if (cooldownTimerRef.current) clearTimeout(cooldownTimerRef.current);
  }, []);

  // When editingMessage is set, populate the textarea
  useEffect(() => {
    if (editingMessage) {
      setText(editingMessage.content);
      textareaRef.current?.focus();
    }
  }, [editingMessage]);

  // When reply is set, focus textarea
  useEffect(() => {
    if (replyTo) {
      textareaRef.current?.focus();
    }
  }, [replyTo]);

  // When quoteText changes, insert it
  useEffect(() => {
    if (quoteText) {
      setText((prev) => {
        const textarea = textareaRef.current;
        if (textarea) {
          const start = textarea.selectionStart;
          const end = textarea.selectionEnd;
          const newText = prev.slice(0, start) + quoteText + prev.slice(end);
          setTimeout(() => {
            textarea.selectionStart = start + quoteText.length;
            textarea.selectionEnd = start + quoteText.length;
            textarea.focus();
          }, 0);
          return newText;
        }
        return prev + quoteText;
      });
      onQuoteInserted();
    }
  }, [quoteText, onQuoteInserted]);

  const handleSubmit = useCallback(() => {
    const content = text.trim();
    if (!content || disabled || sending) return;
    // Send is rate-limited; editing is not.
    if (!editingMessage && onCooldown) return;

    if (editingMessage) {
      onEditSubmit(editingMessage.id, content);
    } else {
      onSend(content);
      setOnCooldown(true);
      cooldownTimerRef.current = setTimeout(() => setOnCooldown(false), SEND_COOLDOWN_MS);
    }
    setText('');
  }, [text, disabled, sending, editingMessage, onCooldown, onSend, onEditSubmit]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
      if (e.key === 'Escape') {
        if (editingMessage) {
          onClearEdit();
          setText('');
        } else if (replyTo) {
          onClearReply();
        }
      }
    },
    [handleSubmit, editingMessage, replyTo, onClearEdit, onClearReply],
  );

  const handleCancelEdit = useCallback(() => {
    onClearEdit();
    setText('');
  }, [onClearEdit]);

  const isOverLimit = text.length > MAX_LENGTH;

  return (
    <div className="px-3 py-2 border-t border-white/10">
      {/* Reply preview */}
      {replyTo && !editingMessage && (
        <div className="flex items-center gap-2 mb-2 px-2 py-1.5 bg-white/[0.04] border border-white/[0.08] rounded-lg">
          <div className="flex-1 min-w-0 border-l-2 border-l-gold pl-2">
            <p className="text-white/50 text-xs font-medium truncate">
              Ответ для {replyTo.sender_username}
            </p>
            <p className="text-white/35 text-xs truncate">
              {truncate(replyTo.content, 60)}
            </p>
          </div>
          <button
            onClick={onClearReply}
            className="text-white/30 hover:text-white/60 transition-colors duration-200 ease-site cursor-pointer flex-shrink-0 p-0.5"
            aria-label="Отменить ответ"
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Edit mode */}
      {editingMessage && (
        <div className="flex items-center gap-2 mb-2 px-2 py-1.5 bg-site-blue/[0.08] border border-site-blue/15 rounded-lg">
          <div className="flex-1 min-w-0 border-l-2 border-l-site-blue pl-2">
            <p className="text-site-blue text-xs font-medium">
              Редактирование
            </p>
            <p className="text-white/35 text-xs truncate">
              {truncate(editingMessage.content, 60)}
            </p>
          </div>
          <button
            onClick={handleCancelEdit}
            className="text-white/30 hover:text-white/60 transition-colors duration-200 ease-site cursor-pointer flex-shrink-0 p-0.5"
            aria-label="Отменить редактирование"
          >
            <X size={14} />
          </button>
        </div>
      )}

      <textarea
        ref={textareaRef}
        value={text}
        onChange={handleChange}
        onKeyDown={handleKeyDown}
        placeholder={disabled ? 'Выберите диалог...' : 'Написать сообщение...'}
        maxLength={MAX_LENGTH}
        rows={3}
        disabled={disabled}
        className="input-underline w-full text-sm !py-2 resize-none gold-scrollbar disabled:opacity-40 disabled:cursor-not-allowed"
      />

      <div className="flex items-center justify-between mt-2">
        {/* Character count */}
        <span className={`text-xs ${isOverLimit ? 'text-site-red' : 'text-white/30'}`}>
          {text.length}/{MAX_LENGTH}
        </span>

        {/* Send / Save button */}
        <button
          onClick={handleSubmit}
          disabled={!text.trim() || disabled || sending || isOverLimit || (!editingMessage && onCooldown)}
          className="btn-blue !px-3 !py-1.5 !text-sm disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {sending
            ? 'Отправка...'
            : editingMessage
              ? 'Сохранить'
              : 'Отправить'}
        </button>
      </div>
    </div>
  );
};

export default MessageInput;
