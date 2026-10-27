import { useState } from 'react';
import toast from 'react-hot-toast';
import { Heart, Pencil, Trash2 } from 'lucide-react';
import { deletePost, editPost, likePost, type EpisodePost } from '../../../api/episodes';
import { apiErrorMessage } from '../../../api/errors';
import ArchiveLinkPreview from '../../CommonComponents/ArchiveLinkPreview/ArchiveLinkPreview';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import WysiwygEditor from '../../CommonComponents/WysiwygEditor/WysiwygEditor';
import { formatRelativeTime } from '../../../utils/serverDate';
import { sanitizePostHtml } from '../../../utils/sanitizePostHtml';
import ConfirmDialog from '../LocationPage/ConfirmDialog';

interface EpisodePostCardProps {
  episodeId: number;
  post: EpisodePost;
  canEdit: boolean;
  canDelete: boolean;
  signedIn: boolean;
  onChanged: (post: EpisodePost | null) => void;
}

/** A post written from a mini-role; the player behind it is named in small print. */
const EpisodePostCard = ({ episodeId, post, canEdit, canDelete, signedIn, onChanged }: EpisodePostCardProps) => {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(post.content);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);

  const toggleLike = async () => {
    try {
      await likePost(episodeId, post.id, !post.liked);
      onChanged({ ...post, liked: !post.liked, likes_count: post.likes_count + (post.liked ? -1 : 1) });
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось поставить лайк'));
    }
  };

  const save = async () => {
    setSaving(true);
    try {
      onChanged(await editPost(episodeId, post.id, draft));
      setEditing(false);
      toast.success('Пост изменён');
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить пост'));
    } finally {
      setSaving(false);
    }
  };

  const remove = async () => {
    setDeleting(false);
    try {
      await deletePost(episodeId, post.id);
      onChanged(null);
      toast.success('Пост удалён');
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось удалить пост'));
    }
  };

  const role = post.role;
  return (
    <article className="bg-site-bg backdrop-blur-sm rounded-card border border-white/[0.07] hover:border-gold-dark/30 transition-colors p-4 sm:p-5 flex flex-col gap-3.5">
      <div className="flex items-start gap-3 sm:gap-3.5">
        <div className="gold-outline w-12 h-12 sm:w-[52px] sm:h-[52px] rounded-full overflow-hidden bg-black/40 shrink-0">
          {role?.avatar_url && <img src={role.avatar_url} alt={role.name} className="w-full h-full object-cover" />}
        </div>
        <div className="flex flex-col gap-0.5 min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap min-w-0">
            <span className="text-white text-sm sm:text-[15px] font-medium truncate max-w-full">{role?.name ?? 'Роль удалена'}</span>
            <span className="text-white/40 text-[11px] shrink-0">{formatRelativeTime(post.created_at)}</span>
            {post.edited_at && <span className="text-white/35 text-[11px] italic shrink-0">· изменено</span>}
          </div>
          <span className="text-white/35 text-[11px] truncate">игрок {post.username ?? `#${post.user_id}`}</span>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {canEdit && (
            <button type="button" title="Редактировать" onClick={() => { setDraft(post.content); setEditing(true); }}
              className="w-8 h-8 flex items-center justify-center rounded-[8px] text-white/35 hover:text-site-blue transition-colors">
              <Pencil size={15} />
            </button>
          )}
          {canDelete && (
            <button type="button" title="Удалить" onClick={() => setDeleting(true)}
              className="w-8 h-8 flex items-center justify-center rounded-[8px] text-white/35 hover:text-site-red transition-colors">
              <Trash2 size={15} />
            </button>
          )}
        </div>
      </div>

      <ArchiveLinkPreview>
        <div
          className="text-white/[0.88] text-sm sm:text-[14.5px] leading-relaxed whitespace-pre-wrap break-words prose-rules
            [&_blockquote]:border-l-2 [&_blockquote]:border-gold/50 [&_blockquote]:pl-3.5 [&_blockquote]:my-2 [&_blockquote]:italic [&_blockquote]:text-white/75
            [&_em]:italic"
          dangerouslySetInnerHTML={{ __html: sanitizePostHtml(post.content) }}
        />
      </ArchiveLinkPreview>

      <div className="flex items-center gap-4 pt-3 border-t border-white/[0.06]">
        <button type="button" onClick={() => void toggleLike()} disabled={!signedIn}
          className="flex items-center gap-1.5 text-sm group disabled:cursor-default"
          aria-label={post.liked ? 'Убрать лайк' : 'Поставить лайк'}>
          <Heart size={17} className={post.liked ? 'text-site-red fill-current' : 'text-white/40 group-hover:text-site-red/70'} />
          <span className={post.liked ? 'text-site-red' : 'text-white/40'}>{post.likes_count}</span>
        </button>
        <span className="ml-auto text-white/30 text-[11px]">{post.length} симв.</span>
      </div>

      {editing && (
        <ModalShell
          open
          onClose={() => setEditing(false)}
          title="Редактирование поста"
          size="lg"
          dismissible={!saving}
          closeOnBackdrop={false}
          closeOnEscape={false}
          footer={
            <>
              <button type="button" onClick={() => setEditing(false)} disabled={saving} className="btn-line w-full sm:w-auto !px-5">Отмена</button>
              <button type="button" onClick={() => void save()} disabled={saving} className="btn-blue w-full sm:w-auto !px-6 disabled:opacity-50">
                {saving ? 'Сохранение...' : 'Сохранить'}
              </button>
            </>
          }
        >
          <WysiwygEditor content={post.content} onChange={setDraft} enableArchiveLinks />
        </ModalShell>
      )}
      {deleting && (
        <ConfirmDialog title="Удалить пост" message="Пост будет удалён безвозвратно." confirmLabel="Удалить" danger
          onCancel={() => setDeleting(false)} onConfirm={() => void remove()} />
      )}
    </article>
  );
};

export default EpisodePostCard;
