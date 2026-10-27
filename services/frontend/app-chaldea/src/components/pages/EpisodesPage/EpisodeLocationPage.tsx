import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { ArrowLeft, Lock } from 'lucide-react';
import {
  createPost,
  getLocation,
  listPosts,
  type EpisodeLocationView,
  type EpisodePost,
} from '../../../api/episodes';
import { apiErrorMessage } from '../../../api/errors';
import { useAppSelector } from '../../../redux/store';
import { selectRole } from '../../../redux/slices/userSlice';
import { useBodyBackground } from '../../../hooks/useBodyBackground';
import WysiwygEditor from '../../CommonComponents/WysiwygEditor/WysiwygEditor';
import { isContentEmpty } from '../LocationPage/gateConstants';
import EpisodePostCard from './EpisodePostCard';

/*
  An episode's location: its picture as the page background, the posts newest
  first, and — for a member with a mini-role — the editor. The unsent text is
  kept in this browser per location, so a reload doesn't lose it.
*/

const draftKey = (locationId: number) => `episode-draft:${locationId}`;

const readDraft = (locationId: number): string => {
  try {
    return localStorage.getItem(draftKey(locationId)) ?? '';
  } catch {
    return '';
  }
};

const writeDraft = (locationId: number, html: string) => {
  try {
    if (isContentEmpty(html)) localStorage.removeItem(draftKey(locationId));
    else localStorage.setItem(draftKey(locationId), html);
  } catch {
    /* no storage — the editor still works */
  }
};

const EpisodeLocationPage = () => {
  const { episodeId, locationId } = useParams();
  const eid = Number(episodeId);
  const lid = Number(locationId);
  const navigate = useNavigate();
  const userId = useAppSelector((state) => state.user.id) as number | null;
  const siteRole = useAppSelector(selectRole);
  const [view, setView] = useState<EpisodeLocationView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [posts, setPosts] = useState<EpisodePost[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [roleId, setRoleId] = useState<number | null>(null);
  const [content, setContent] = useState('');
  const [editorKey, setEditorKey] = useState(0);
  const [sending, setSending] = useState(false);

  useBodyBackground(view?.location.image_url ?? view?.episode.image_url);

  const load = useCallback(async () => {
    try {
      const [v, p] = await Promise.all([getLocation(eid, lid), listPosts(eid, lid)]);
      setView(v);
      setPosts(p.posts);
      setHasMore(p.has_more);
      setError(null);
      setRoleId((cur) => (cur && v.my_roles.some((r) => r.id === cur) ? cur : v.my_roles[0]?.id ?? null));
    } catch (e) {
      setError(apiErrorMessage(e, 'Не удалось загрузить локацию'));
    }
  }, [eid, lid]);

  useEffect(() => {
    setView(null);
    setContent(readDraft(lid));
    setEditorKey((k) => k + 1);
    void load();
  }, [load, lid]);

  const more = async () => {
    setLoadingMore(true);
    try {
      const p = await listPosts(eid, lid, posts[posts.length - 1]?.id);
      setPosts((prev) => [...prev, ...p.posts]);
      setHasMore(p.has_more);
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось загрузить посты'));
    } finally {
      setLoadingMore(false);
    }
  };

  const send = async () => {
    if (!roleId) {
      toast.error('Выберите, от чьего имени писать');
      return;
    }
    if (isContentEmpty(content)) {
      toast.error('Пост пустой');
      return;
    }
    setSending(true);
    try {
      const post = await createPost(eid, lid, roleId, content);
      setPosts((prev) => [post, ...prev]);
      setContent('');
      writeDraft(lid, '');
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
      <div className="w-full max-w-container mx-auto flex flex-col items-start gap-4">
        <Link to={`/episodes/${eid}`} className="text-white/60 hover:text-white text-sm flex items-center gap-1"><ArrowLeft size={15} />К эпизоду</Link>
        <div className="bg-site-bg backdrop-blur-sm rounded-card border border-white/10 p-6 text-white/80 flex items-center gap-3">
          <Lock size={18} className="text-gold shrink-0" />{error}
        </div>
      </div>
    );
  }
  if (!view) return <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin mx-auto" />;

  const role = view.my_roles.find((r) => r.id === roleId);
  return (
    <div className="w-full max-w-container mx-auto flex flex-col gap-4 sm:gap-5 pb-10">
      <div className="flex items-center gap-3 flex-wrap">
        <Link to={`/episodes/${eid}`} className="text-white/60 hover:text-white text-sm flex items-center gap-1 min-w-0">
          <ArrowLeft size={15} className="shrink-0" /><span className="truncate">{view.episode.title}</span>
        </Link>
        {view.locations.length > 1 && (
          <select value={lid} onChange={(e) => navigate(`/episodes/${eid}/location/${e.target.value}`)}
            className="ml-auto max-w-full bg-black/50 border border-white/10 rounded-card text-white text-sm px-3 py-1.5 focus:outline-none focus:border-gold/50">
            {view.locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </select>
        )}
      </div>

      <section className="bg-site-bg backdrop-blur-sm rounded-card border border-gold-dark/20 shadow-card px-4 py-5 sm:px-8 sm:py-7 flex flex-col gap-2.5">
        <h1 className="text-white text-3xl sm:text-5xl font-medium uppercase leading-tight break-words"
          style={{ textShadow: '0 6px 26px rgba(0,0,0,.8)' }}>
          {view.location.name}
        </h1>
        {view.location.description && (
          <p className="max-w-2xl text-white/80 text-sm sm:text-[15px] font-light leading-relaxed whitespace-pre-wrap break-words">
            {view.location.description}
          </p>
        )}
      </section>

      {view.my_roles.length > 0 ? (
        <section className="bg-site-bg backdrop-blur-sm rounded-card border border-white/[0.07] p-4 sm:p-5 flex flex-col gap-3">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-white/50 text-xs uppercase tracking-[0.06em] mr-1">Пишет</span>
            {view.my_roles.map((r) => (
              <button key={r.id} type="button" onClick={() => setRoleId(r.id)}
                className={`flex items-center gap-2 pl-1 pr-3 py-1 rounded-full border text-sm transition-colors ${
                  r.id === roleId ? 'border-gold/70 text-gold bg-gold/10' : 'border-white/10 text-white/60 hover:text-white'
                }`}>
                <span className="w-6 h-6 rounded-full overflow-hidden bg-black/40 shrink-0">
                  {r.avatar_url && <img src={r.avatar_url} alt="" className="w-full h-full object-cover" />}
                </span>
                <span className="truncate max-w-[160px]">{r.name}</span>
              </button>
            ))}
          </div>
          <WysiwygEditor key={editorKey} content={content}
            onChange={(html) => {
              setContent(html);
              writeDraft(lid, html);
            }}
            enableArchiveLinks />
          <div className="flex flex-col-reverse sm:flex-row sm:items-center gap-2">
            <span className="text-white/35 text-xs">Черновик сохраняется в этом браузере</span>
            <button type="button" onClick={() => void send()} disabled={sending}
              className="btn-blue !w-full sm:!w-auto !px-6 sm:ml-auto disabled:opacity-50">
              {sending ? 'Отправка...' : `Написать${role ? ` от «${role.name}»` : ''}`}
            </button>
          </div>
        </section>
      ) : view.is_member ? (
        <p className="text-white/50 text-sm bg-site-bg rounded-card border border-white/[0.07] p-4">
          У вас пока нет роли в этом эпизоде — попросите владельца или мастера выдать её.
        </p>
      ) : null}

      <div className="flex flex-col gap-3">
        {posts.length === 0 && <p className="text-white/40 text-sm italic">Здесь ещё никто не писал.</p>}
        {posts.map((post) => (
          <EpisodePostCard
            key={post.id}
            episodeId={eid}
            post={post}
            signedIn={!!userId}
            canEdit={post.user_id === userId || siteRole === 'admin'}
            canDelete={post.user_id === userId || view.can_manage || view.can_moderate}
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
    </div>
  );
};

export default EpisodeLocationPage;
