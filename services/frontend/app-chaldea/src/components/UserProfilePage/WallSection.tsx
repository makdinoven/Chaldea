import { useState } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { User, Trash2 } from 'react-feather';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  selectWallPosts,
  selectPostsLoading,
  selectHasMorePosts,
  selectPostsPage,
  createPost,
  deletePost,
  loadWallPosts,
  type WallPost,
} from '../../redux/slices/userProfileSlice';
import WysiwygEditor from '../CommonComponents/WysiwygEditor/WysiwygEditor';

interface WallSectionProps {
  profileUserId: number;
  isOwnProfile: boolean;
}

const PostCard = ({
  post,
  currentUserId,
  isWallOwner,
}: {
  post: WallPost;
  currentUserId: number | null;
  isWallOwner: boolean;
}) => {
  const dispatch = useAppDispatch();
  const canDelete = currentUserId === post.author_id || isWallOwner;

  const handleDelete = async () => {
    try {
      await dispatch(deletePost(post.id)).unwrap();
      toast.success('Пост удалён');
    } catch {
      toast.error('Не удалось удалить пост');
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
    <div className="gray-bg p-5 flex gap-4">
      {/* Author avatar */}
      <Link
        to={`/user-profile/${post.author_id}`}
        className="flex-shrink-0"
      >
        <div className="w-10 h-10 rounded-full overflow-hidden bg-white/10 flex items-center justify-center">
          {post.author_avatar ? (
            <img
              src={post.author_avatar}
              alt={post.author_username}
              className="w-full h-full object-cover"
            />
          ) : (
            <User size={18} className="text-white/40" />
          )}
        </div>
      </Link>

      {/* Post content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2 mb-2">
          <div className="flex items-center gap-2">
            <Link
              to={`/user-profile/${post.author_id}`}
              className="text-site-blue font-medium hover:underline"
            >
              {post.author_username}
            </Link>
            <span className="text-white/30 text-xs">{date}</span>
          </div>
          {canDelete && (
            <button
              onClick={handleDelete}
              className="text-white/30 hover:text-site-red transition-colors p-1"
              title="Удалить пост"
            >
              <Trash2 size={14} />
            </button>
          )}
        </div>
        <div
          className="prose-rules text-white/80 text-sm break-words"
          dangerouslySetInnerHTML={{ __html: post.content }}
        />
      </div>
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

  const [editorContent, setEditorContent] = useState('');
  const [posting, setPosting] = useState(false);
  const [editorKey, setEditorKey] = useState(0);

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
        <div className="gray-bg p-5 flex flex-col gap-3">
          <WysiwygEditor
            key={editorKey}
            content={editorContent}
            onChange={setEditorContent}
          />
          <div className="flex justify-end">
            <button
              className="btn-blue !py-2 !px-6 !text-sm"
              onClick={handleSubmit}
              disabled={posting || isContentEmpty(editorContent)}
            >
              {posting ? 'Отправка...' : 'Опубликовать'}
            </button>
          </div>
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
