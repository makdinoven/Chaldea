import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { Footprints, Lock, MessageSquare } from 'lucide-react';
import {
  createRoomPost,
  getRoom,
  MIN_ROOM_POST_LENGTH,
  type ActingCharacter,
  type HouseRoom,
  type RoomPost,
  type RoomView,
} from '../../../api/houses';
import { apiErrorMessage } from '../../../api/errors';
import WysiwygEditor from '../../CommonComponents/WysiwygEditor/WysiwygEditor';
import { isContentEmpty, stripHtmlTags } from '../LocationPage/gateConstants';
import RoomPostCard from './RoomPostCard';

/*
  FEAT-180 — the posts of a house room, newest first, with the editor for the
  acting character. Stage 7: writing needs the character standing in the room.
  The unsent text is kept in this browser per room, so a reload doesn't lose it.
*/

const draftKey = (roomId: number) => `house-draft:${roomId}`;

const readDraft = (roomId: number): string => {
  try {
    return localStorage.getItem(draftKey(roomId)) ?? '';
  } catch {
    return '';
  }
};

const writeDraft = (roomId: number, html: string) => {
  try {
    if (isContentEmpty(html)) localStorage.removeItem(draftKey(roomId));
    else localStorage.setItem(draftKey(roomId), html);
  } catch {
    /* no storage — the editor still works */
  }
};

interface RoomPostsProps {
  room: HouseRoom;
  /** The character the viewer acts through, if any (it writes). */
  acting: ActingCharacter | null;
  frozen: boolean;
  /** Moves the acting character into this room (the «Перейти сюда» shortcut). */
  onMoveHere: (() => void) | null;
}

const RoomPosts = ({ room, acting, frozen, onMoveHere }: RoomPostsProps) => {
  const rid = room.id;
  const [view, setView] = useState<RoomView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [posts, setPosts] = useState<RoomPost[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [content, setContent] = useState('');
  const [editorKey, setEditorKey] = useState(0);
  const [sending, setSending] = useState(false);

  const load = useCallback(async () => {
    try {
      const v = await getRoom(rid);
      setView(v);
      setPosts(v.posts);
      setHasMore(v.has_more);
      setError(null);
    } catch (e) {
      setError(apiErrorMessage(e, 'Не удалось загрузить комнату'));
    }
  }, [rid]);

  useEffect(() => {
    setView(null);
    setError(null);
    setContent(readDraft(rid));
    setEditorKey((k) => k + 1);
    void load();
  }, [load, rid]);

  const more = async () => {
    setLoadingMore(true);
    try {
      const v = await getRoom(rid, posts[posts.length - 1]?.id);
      setPosts((prev) => [...prev, ...v.posts]);
      setHasMore(v.has_more);
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось загрузить посты'));
    } finally {
      setLoadingMore(false);
    }
  };

  const writer = acting?.character ?? null;
  const canWriteHere = writer != null && view != null && view.writers.some((w) => w.id === writer.id);
  const inRoom = acting?.room_id === rid;
  const built = room.level >= 1;
  const length = stripHtmlTags(content).length;

  const send = async () => {
    if (!writer) return;
    if (isContentEmpty(content)) {
      toast.error('Пост пустой');
      return;
    }
    if (length < MIN_ROOM_POST_LENGTH) {
      toast.error(`Минимальная длина поста — ${MIN_ROOM_POST_LENGTH} символов (сейчас: ${length})`);
      return;
    }
    setSending(true);
    try {
      const post = await createRoomPost(rid, writer.id, content);
      setPosts((prev) => [post, ...prev]);
      setContent('');
      writeDraft(rid, '');
      setEditorKey((k) => k + 1);
      toast.success('Пост опубликован');
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось опубликовать пост'));
    } finally {
      setSending(false);
    }
  };

  if (error) {
    return (
      <div className="bg-site-bg backdrop-blur-sm rounded-card border border-white/10 p-5 text-white/80 text-sm flex items-center gap-3">
        <Lock size={18} className="text-gold shrink-0" />{error}
      </div>
    );
  }
  if (!view) return <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin mx-auto" />;

  return (
    <div className="flex flex-col gap-3 sm:gap-4">
      <div className="flex items-center gap-2.5 px-1">
        <MessageSquare size={17} className="text-gold shrink-0" />
        <h2 className="gold-text text-[13px] font-medium uppercase tracking-[0.08em]">Летопись комнаты</h2>
      </div>

      {canWriteHere && !built && (
        <p className="bg-site-bg backdrop-blur-sm rounded-card border border-white/[0.07] p-4 text-white/60 text-sm">
          Комната ещё строится — писать здесь можно будет, когда стройка закончится.
        </p>
      )}

      {canWriteHere && built && (
        <section className="bg-site-bg backdrop-blur-sm rounded-card border border-white/[0.07] p-4 sm:p-5 flex flex-col gap-3">
          {frozen && (
            <p className="text-site-red text-sm">
              Дом заморожен за неуплату налога — писать здесь нельзя, пока налог не уплачен (вкладка «Управление домом»).
            </p>
          )}
          {!inRoom && (
            <div className="flex flex-col sm:flex-row sm:items-center gap-2 text-sm text-gold-light bg-gold/10 border border-gold-dark/30 rounded-card px-3 py-2">
              <span className="flex-1">Писать здесь можно, только стоя в этой комнате.</span>
              {onMoveHere && (
                <button type="button" onClick={onMoveHere}
                  className="btn-line !w-full sm:!w-auto !px-4 !py-1 !text-xs flex items-center justify-center gap-1.5 shrink-0">
                  <Footprints size={12} />Перейти сюда
                </button>
              )}
            </div>
          )}
          <div className={inRoom ? '' : 'opacity-50 pointer-events-none'} aria-disabled={!inRoom}>
            <WysiwygEditor key={editorKey} content={content}
              onChange={(html) => {
                setContent(html);
                writeDraft(rid, html);
              }}
              enableArchiveLinks />
          </div>
          <div className="flex flex-col-reverse sm:flex-row sm:items-center gap-2">
            <span className="text-white/35 text-xs">
              <span className={length >= MIN_ROOM_POST_LENGTH ? 'text-stat-energy' : 'text-white/50'}>
                {length} / {MIN_ROOM_POST_LENGTH}
              </span>
              {' '}· минимум {MIN_ROOM_POST_LENGTH} символов · черновик сохраняется в этом браузере
            </span>
            <button type="button" onClick={() => void send()} disabled={sending || frozen || !inRoom}
              className="btn-blue !w-full sm:!w-auto !px-6 sm:ml-auto shrink-0 disabled:opacity-50">
              {sending ? 'Отправка...' : `Написать от «${writer!.name}»`}
            </button>
          </div>
        </section>
      )}

      {writer && !canWriteHere && (
        <p className="text-white/45 text-xs px-1">«{writer.name}» не может писать в этой комнате — хозяин не пускал этого персонажа сюда.</p>
      )}

      {posts.length === 0 && <p className="text-white/40 text-sm italic px-1">Здесь ещё никто не писал.</p>}
      {posts.map((post) => (
        <RoomPostCard
          key={post.id}
          post={post}
          onChanged={(next) => setPosts((prev) => (next
            ? prev.map((p) => (p.id === post.id ? next : p))
            : prev.filter((p) => p.id !== post.id)))}
        />
      ))}
      {hasMore && (
        <button type="button" onClick={() => void more()} disabled={loadingMore} className="btn-line !w-full sm:!w-auto !px-6 self-center disabled:opacity-50">
          {loadingMore ? 'Загрузка...' : 'Показать ещё'}
        </button>
      )}
    </div>
  );
};

export default RoomPosts;
