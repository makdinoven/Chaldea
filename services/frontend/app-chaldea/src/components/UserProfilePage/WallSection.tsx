import { useState, useRef, useEffect, useMemo } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { motion, AnimatePresence } from 'motion/react';
import { User, Trash2, Edit3 } from 'react-feather';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  selectWallPosts,
  selectPostsLoading,
  selectHasMorePosts,
  selectPostsPage,
  selectUserProfile,
  createPost,
  editPost,
  deletePost,
  loadWallPosts,
  type WallPost,
  type ProfileStyleSettings,
} from '../../redux/slices/userProfileSlice';
import { buildColorEffectStyle } from './ProfileSettingsModal';
import WysiwygEditor from '../CommonComponents/WysiwygEditor/WysiwygEditor';

interface WallSectionProps {
  profileUserId: number;
  isOwnProfile: boolean;
}

const PostCard = ({
  post,
  currentUserId,
  isWallOwner,
  postColorStyle,
}: {
  post: WallPost;
  currentUserId: number | null;
  isWallOwner: boolean;
  postColorStyle: React.CSSProperties | null;
}) => {
  const dispatch = useAppDispatch();
  const canDelete = currentUserId === post.author_id || isWallOwner;
  const canEdit = currentUserId === post.author_id;

  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState(post.content);
  const [saving, setSaving] = useState(false);
  const [editKey, setEditKey] = useState(0);

  const handleDelete = async () => {
    try {
      await dispatch(deletePost(post.id)).unwrap();
      toast.success('Пост удалён');
    } catch {
      toast.error('Не удалось удалить пост');
    }
  };

  const handleEdit = () => {
    setEditContent(post.content);
    setEditKey((k) => k + 1);
    setIsEditing(true);
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditContent(post.content);
  };

  const handleSaveEdit = async () => {
    const stripped = editContent.replace(/<[^>]*>/g, '').trim();
    if (!stripped) return;
    setSaving(true);
    try {
      await dispatch(editPost({ postId: post.id, content: editContent })).unwrap();
      setIsEditing(false);
      toast.success('Пост обновлён');
    } catch {
      toast.error('Не удалось сохранить изменения');
    } finally {
      setSaving(false);
    }
  };

  const date = new Date(post.created_at).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });

  return (
    <div
      className={postColorStyle ? 'rounded-card p-5' : 'gray-bg p-5'}
      style={postColorStyle ?? undefined}
    >
      {/* Author header */}
      <div className="flex items-center justify-between gap-2 mb-3">
        <div className="flex items-center gap-3">
          <Link
            to={`/user-profile/${post.author_id}`}
            className="flex-shrink-0"
          >
            <div className="w-8 h-8 rounded-full overflow-hidden bg-white/10 flex items-center justify-center">
              {post.author_avatar ? (
                <img
                  src={post.author_avatar}
                  alt={post.author_username}
                  className="w-full h-full object-cover"
                />
              ) : (
                <User size={14} className="text-white/40" />
              )}
            </div>
          </Link>
          <Link
            to={`/user-profile/${post.author_id}`}
            className="text-site-blue font-medium hover:underline text-sm"
          >
            {post.author_username}
          </Link>
          <span className="text-white/30 text-xs">{date}</span>
        </div>
        <div className="flex items-center gap-1">
          {canEdit && !isEditing && (
            <button
              onClick={handleEdit}
              className="text-white/30 hover:text-site-blue transition-colors p-1"
              title="Редактировать пост"
            >
              <Edit3 size={14} />
            </button>
          )}
          {canDelete && !isEditing && (
            <button
              onClick={handleDelete}
              className="text-white/30 hover:text-site-red transition-colors p-1"
              title="Удалить пост"
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Post content or editor */}
      {isEditing ? (
        <div className="flex flex-col gap-3">
          <WysiwygEditor
            key={editKey}
            content={editContent}
            onChange={setEditContent}
          />
          <div className="flex justify-end gap-3">
            <button
              className="btn-line !py-2 !px-6 !text-sm"
              onClick={handleCancelEdit}
            >
              Отмена
            </button>
            <button
              className="btn-blue !py-2 !px-6 !text-sm"
              onClick={handleSaveEdit}
              disabled={saving}
            >
              {saving ? 'Сохранение...' : 'Сохранить'}
            </button>
          </div>
        </div>
      ) : (
        <div
          className="prose-rules text-white/80 text-sm break-words"
          dangerouslySetInnerHTML={{ __html: post.content }}
        />
      )}
    </div>
  );
};

const WallSection = ({ profileUserId, isOwnProfile }: WallSectionProps) => {
  const dispatch = useAppDispatch();
  const posts = useAppSelector(selectWallPosts);
  const postsLoading = useAppSelector(selectPostsLoading);
  const hasMore = useAppSelector(selectHasMorePosts);
  const page = useAppSelector(selectPostsPage);
  const currentUserId = useAppSelector((state) => state.user.id) as number | null;
  const isLoggedIn = currentUserId !== null;
  const profile = useAppSelector(selectUserProfile);

  const [editorContent, setEditorContent] = useState('');
  const [posting, setPosting] = useState(false);
  const [editorKey, setEditorKey] = useState(0);
  const [isEditorOpen, setIsEditorOpen] = useState(false);
  const formRef = useRef<HTMLDivElement>(null);

  /** Compute post color style from the profile owner's settings */
  const postColorStyle = useMemo<React.CSSProperties | null>(() => {
    const color = profile?.post_color;
    if (!color) return null;
    const ss: ProfileStyleSettings = profile?.profile_style_settings ?? {};
    const style = buildColorEffectStyle(color, 'post_color', ss);
    // Ensure the post has rounded corners matching gray-bg
    style.borderRadius = '15px';
    return style;
  }, [profile?.post_color, profile?.profile_style_settings]);

  useEffect(() => {
    if (!isEditorOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (formRef.current && !formRef.current.contains(e.target as Node)) {
        if (isContentEmpty(editorContent)) {
          setIsEditorOpen(false);
        }
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isEditorOpen, editorContent]);

  const isContentEmpty = (html: string) => {
    const stripped = html.replace(/<[^>]*>/g, '').trim();
    return stripped.length === 0;
  };

  const handleSubmit = async () => {
    if (isContentEmpty(editorContent)) return;
    setPosting(true);
    try {
      await dispatch(createPost({ userId: profileUserId, content: editorContent })).unwrap();
      setEditorContent('');
      setEditorKey((k) => k + 1);
      setIsEditorOpen(false);
      toast.success('Пост опубликован');
    } catch {
      toast.error('Не удалось опубликовать пост');
    } finally {
      setPosting(false);
    }
  };

  const handleLoadMore = () => {
    dispatch(loadWallPosts({ userId: profileUserId, page: page + 1 }));
  };

  return (
    <div className="flex flex-col gap-4">
      {/* New post form with WYSIWYG editor */}
      {isLoggedIn && (
        <div ref={formRef}>
          <AnimatePresence mode="wait">
            {!isEditorOpen ? (
              <motion.div
                key="toggle-placeholder"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.15 }}
                className={
                  postColorStyle
                    ? 'px-4 py-3 flex items-center gap-3 cursor-pointer hover:brightness-110 transition-all rounded-card'
                    : 'gray-bg px-4 py-3 flex items-center gap-3 cursor-pointer hover:bg-white/[0.08] transition-colors rounded-card'
                }
                style={postColorStyle ?? undefined}
                onClick={() => setIsEditorOpen(true)}
              >
                <Edit3 size={16} className="text-white/30 flex-shrink-0" />
                <span className="text-white/30 text-sm select-none">Написать на стену...</span>
              </motion.div>
            ) : (
              <motion.div
                key="editor-form"
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -10 }}
                transition={{ duration: 0.2, ease: 'easeOut' }}
                className={postColorStyle ? 'p-5 flex flex-col gap-3 rounded-card' : 'gray-bg p-5 flex flex-col gap-3'}
                style={postColorStyle ?? undefined}
              >
                <WysiwygEditor
                  key={editorKey}
                  content={editorContent}
                  onChange={setEditorContent}
                />
                <div className="flex justify-end gap-3">
                  <button
                    className="btn-line !py-2 !px-6 !text-sm"
                    onClick={() => {
                      setIsEditorOpen(false);
                      setEditorContent('');
                      setEditorKey((k) => k + 1);
                    }}
                  >
                    Отмена
                  </button>
                  <button
                    className="btn-blue !py-2 !px-6 !text-sm"
                    onClick={handleSubmit}
                    disabled={posting || isContentEmpty(editorContent)}
                  >
                    {posting ? 'Отправка...' : 'Опубликовать'}
                  </button>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}

      {/* Posts list */}
      {posts.length === 0 && !postsLoading && (
        <p className="text-white/30 text-sm text-center py-8">
          Пока нет записей на стене
        </p>
      )}

      {posts.map((post) => (
        <PostCard
          key={post.id}
          post={post}
          currentUserId={currentUserId}
          isWallOwner={isOwnProfile}
          postColorStyle={postColorStyle}
        />
      ))}

      {/* Load more */}
      {hasMore && posts.length > 0 && (
        <button
          className="btn-line mx-auto"
          onClick={handleLoadMore}
          disabled={postsLoading}
        >
          {postsLoading ? 'Загрузка...' : 'Загрузить ещё'}
        </button>
      )}
    </div>
  );
};

export default WallSection;
