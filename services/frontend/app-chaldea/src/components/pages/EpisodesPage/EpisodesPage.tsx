import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Lock, EyeOff, Users, MessageSquare } from 'lucide-react';
import { CATEGORY_LABEL, listEpisodes, MEMBER_ROLE_LABEL, type EpisodeCard, type EpisodeCategory } from '../../../api/episodes';
import { apiErrorMessage } from '../../../api/errors';
import { useAppSelector } from '../../../redux/store';
import { formatRelativeTime } from '../../../utils/serverDate';
import EpisodeFormModal from './EpisodeFormModal';

/*
  FEAT-179: «Эпизоды» — stories players run outside the main world, in two
  categories. Private episodes are listed to their members only.
*/

const CATEGORIES: EpisodeCategory[] = ['world', 'separate'];

const EpisodesPage = () => {
  const [params, setParams] = useSearchParams();
  const category: EpisodeCategory = params.get('c') === 'separate' ? 'separate' : 'world';
  const [episodes, setEpisodes] = useState<EpisodeCard[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const userId = useAppSelector((state) => state.user.id) as number | null;
  const navigate = useNavigate();

  useEffect(() => {
    setEpisodes(null);
    setError(null);
    listEpisodes(category)
      .then(setEpisodes)
      .catch((e) => setError(apiErrorMessage(e, 'Не удалось загрузить эпизоды')));
  }, [category]);

  return (
    <div className="w-full max-w-container mx-auto flex flex-col gap-5 pb-10">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div className="flex flex-col gap-1.5">
          <h1 className="gold-text text-2xl sm:text-3xl font-semibold uppercase tracking-[0.06em]">Эпизоды</h1>
          <p className="text-white/60 text-sm max-w-2xl">
            Истории вне основной игры: сыграть событие задним числом или совсем другой мир. Пишут от мини-ролей,
            опыта и боёв здесь нет.
          </p>
        </div>
        {userId && (
          <button type="button" onClick={() => setCreating(true)} className="btn-blue !w-full sm:!w-auto !px-6 shrink-0">
            Создать эпизод
          </button>
        )}
      </div>

      <div className="flex gap-2 border-b border-white/10">
        {CATEGORIES.map((c) => (
          <button key={c} type="button" onClick={() => setParams(c === 'world' ? {} : { c })}
            className={`px-3 sm:px-4 py-2 -mb-px border-b-2 text-sm uppercase tracking-[0.06em] transition-colors ${
              c === category ? 'border-gold text-gold' : 'border-transparent text-white/50 hover:text-white'
            }`}>
            {CATEGORY_LABEL[c]}
          </button>
        ))}
      </div>

      {error && <p className="text-site-red text-sm">{error}</p>}
      {!episodes && !error && <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />}
      {episodes?.length === 0 && (
        <p className="text-white/40 text-sm italic">Здесь пока нет ни одного эпизода. Начните первый!</p>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {episodes?.map((ep) => (
          <Link key={ep.id} to={`/episodes/${ep.id}`}
            className="group bg-site-bg backdrop-blur-sm rounded-card border border-white/[0.07] hover:border-gold-dark/50 overflow-hidden flex flex-col transition-colors">
            <div className="relative aspect-[16/8] bg-black/40 overflow-hidden">
              {ep.image_url && (
                <img src={ep.image_url} alt="" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
              )}
              <div className="absolute top-2 left-2 flex gap-1.5 flex-wrap">
                {ep.is_private && (
                  <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-black/70 text-gold text-[11px]"><Lock size={12} />Закрытый</span>
                )}
                {ep.is_hidden && (
                  <span className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-black/70 text-site-red text-[11px]"><EyeOff size={12} />Скрыт</span>
                )}
                {ep.my_role && (
                  <span className="px-2 py-0.5 rounded-full bg-black/70 text-white/80 text-[11px]">{MEMBER_ROLE_LABEL[ep.my_role]}</span>
                )}
              </div>
            </div>
            <div className="p-4 flex flex-col gap-2 flex-1">
              <h2 className="text-white text-lg font-medium leading-tight break-words">{ep.title}</h2>
              <p className="text-white/60 text-sm line-clamp-3 break-words">{ep.description}</p>
              <div className="mt-auto pt-2 flex items-center gap-4 text-xs text-white/45 flex-wrap">
                <span className="flex items-center gap-1"><Users size={13} />{ep.members_count}</span>
                <span className="flex items-center gap-1"><MessageSquare size={13} />{ep.posts_count}</span>
                {ep.last_post_at && <span>{formatRelativeTime(ep.last_post_at)}</span>}
                {ep.owner && <span className="ml-auto truncate">ведёт {ep.owner.username}</span>}
              </div>
            </div>
          </Link>
        ))}
      </div>

      {creating && (
        <EpisodeFormModal
          defaultCategory={category}
          onClose={() => setCreating(false)}
          onSaved={(ep) => navigate(`/episodes/${ep.id}`)}
        />
      )}
    </div>
  );
};

export default EpisodesPage;
