import { useState } from 'react';

interface PostCreateFormProps {
  onSubmit: (content: string) => Promise<void>;
  disabled?: boolean;
}

const PostCreateForm = ({ onSubmit, disabled }: PostCreateFormProps) => {
  const [content, setContent] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = async () => {
    const trimmed = content.trim();
    if (!trimmed || submitting) return;

    setSubmitting(true);
    try {
      await onSubmit(trimmed);
      setContent('');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <textarea
        value={content}
        onChange={(e) => setContent(e.target.value)}
        placeholder="Написать пост..."
        disabled={disabled || submitting}
        rows={4}
        className="textarea-bordered w-full text-sm"
      />
      <button
        onClick={handleSubmit}
        disabled={!content.trim() || submitting || disabled}
        className="btn-blue self-start text-sm px-6 py-2.5 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {submitting ? 'Отправка...' : 'Отправить'}
      </button>
    </div>
  );
};

export default PostCreateForm;
