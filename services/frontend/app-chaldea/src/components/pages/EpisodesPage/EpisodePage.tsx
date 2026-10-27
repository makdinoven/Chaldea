import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { ArrowLeft, EyeOff, Lock, MessageSquare, Pencil, Settings, Trash2 } from 'lucide-react';
import {
  CATEGORY_LABEL,
  deleteEpisode,
  deleteLocation,
  getEpisode,
  hideEpisode,
  removeMember,
  requestToJoin,
  withdrawRequest,
  type EpisodeDetail,
  type EpisodeLocationCard,
} from '../../../api/episodes';
import { apiErrorMessage } from '../../../api/errors';
import { useAppSelector } from '../../../redux/store';
import { useBodyBackground } from '../../../hooks/useBodyBackground';
import { formatRelativeTime } from '../../../utils/serverDate';
import ConfirmDialog from '../LocationPage/ConfirmDialog';
import EpisodeFormModal, { FIELD } from './EpisodeFormModal';
import EpisodeMembers from './EpisodeMembers';
import LocationFormModal from './LocationFormModal';

type Tab = 'locations' | 'members';

interface Confirm {
  title: string;
  message: string;
  label: string;
  action: () => Promise<unknown>;
  after?: () => void;
}

const EpisodePage = () => {
  const { episodeId } = useParams();
  const id = Number(episodeId);
  const navigate = useNavigate();
  const userId = useAppSelector((state) => state.user.id) as number | null;
  const [episode, setEpisode] = useState<EpisodeDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('locations');
  const [settings, setSettings] = useState(false);
  const [locationForm, setLocationForm] = useState<EpisodeLocationCard | 'new' | null>(null);
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const [joinText, setJoinText] = useState('');
  const [joining, setJoining] = useState(false);

  useBodyBackground(episode?.image_url);

  const load = useCallback(() => {
    getEpisode(id)
      .then((ep) => {
        setEpisode(ep);
        setError(null);
      })
      .catch((e) => setError(apiErrorMessage(e, 'Не удалось загрузить эпизод')));
  }, [id]);

  useEffect(load, [load]);

  const act = async (job: () => Promise<unknown>, done: string, failed: string, after?: () => void) => {
    try {
      await job();
      toast.success(done);
      (after ?? load)();
    } catch (e) {
      toast.error(apiErrorMessage(e, failed));
    }
  };

  if (error) {
    return (
      <div className="w-full max-w-container mx-auto flex flex-col items-start gap-4">
        <Link to="/episodes" className="text-white/60 hover:text-white text-sm flex items-center gap-1"><ArrowLeft size={15} />Все эпизоды</Link>
        <div className="bg-site-bg backdrop-blur-sm rounded-card border border-white/10 p-6 text-white/80 flex items-center gap-3">
          <Lock size={18} className="text-gold shrink-0" />{error}
        </div>
      </div>
    );
  }
  if (!episode) return <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin mx-auto" />;

  const member = episode.my_role !== null;
  const canDelete = episode.can_own || episode.can_moderate;

  return (
    <div className="w-full max-w-container mx-auto flex flex-col gap-5 pb-10">
      <Link to={`/episodes${episode.category === 'separate' ? '?c=separate' : ''}`}
        className="self-start text-white/60 hover:text-white text-sm flex items-center gap-1">
        <ArrowLeft size={15} />{CATEGORY_LABEL[episode.category]}
      </Link>

      <section className="bg-site-bg backdrop-blur-sm rounded-card border border-gold-dark/20 shadow-card p-4 sm:p-7 flex flex-col gap-3">
        <div className="flex items-center gap-2 flex-wrap text-[11px] uppercase tracking-[0.06em]">
          <span className="px-3 py-1 rounded-full border border-gold-dark/60 text-gold">{CATEGORY_LABEL[episode.category]}</span>
          {episode.is_private && <span className="flex items-center gap-1 px-3 py-1 rounded-full bg-black/50 text-gold"><Lock size={12} />Закрытый</span>}
          {episode.is_hidden && <span className="flex items-center gap-1 px-3 py-1 rounded-full bg-black/50 text-site-red"><EyeOff size={12} />Скрыт модерацией</span>}
        </div>
        <h1 className="text-white text-2xl sm:text-4xl font-medium uppercase leading-tight break-words"
          style={{ textShadow: '0 6px 26px rgba(0,0,0,.8)' }}>
          {episode.title}
        </h1>
        <p className="text-white/80 text-sm sm:text-[15px] font-light leading-relaxed whitespace-pre-wrap break-words max-w-3xl">
          {episode.description}
        </p>
        <p className="text-white/45 text-xs">Ведёт {episode.owner?.username ?? '—'} · участников: {episode.members.length}</p>

        <div className="flex flex-col sm:flex-row gap-2 sm:items-center flex-wrap pt-1">
          {episode.can_manage && (
            <button type="button" onClick={() => setSettings(true)} className="btn-line !w-full sm:!w-auto !px-4 flex items-center justify-center gap-2">
              <Settings size={15} />Настройки
            </button>
          )}
          {episode.can_moderate && (
            <button type="button" className="btn-line !w-full sm:!w-auto !px-4"
              onClick={() => void act(() => hideEpisode(episode.id, !episode.is_hidden),
                episode.is_hidden ? 'Эпизод снова виден' : 'Эпизод скрыт', 'Не удалось')}>
              {episode.is_hidden ? 'Вернуть в список' : 'Скрыть'}
            </button>
          )}
          {canDelete && (
            <button type="button" className="text-site-red/80 hover:text-site-red text-sm flex items-center gap-1 sm:ml-auto"
              onClick={() => setConfirm({
                title: 'Удалить эпизод',
                message: 'Все локации, роли и посты эпизода будут удалены безвозвратно.',
                label: 'Удалить',
                action: () => deleteEpisode(episode.id),
                after: () => navigate('/episodes'),
              })}>
              <Trash2 size={15} />Удалить эпизод
            </button>
          )}
          {member && episode.my_role !== 'owner' && (
            <button type="button" className="text-white/50 hover:text-site-red text-sm sm:ml-auto"
              onClick={() => setConfirm({
                title: 'Покинуть эпизод',
                message: 'Ваши роли перестанут писать, посты останутся. Вернуться можно будет только по приглашению.',
                label: 'Покинуть',
                action: () => removeMember(episode.id, userId!),
                after: () => navigate('/episodes'),
              })}>
              Покинуть эпизод
            </button>
          )}
        </div>

        {!member && userId && !episode.is_private && (
          <div className="border-t border-white/10 pt-3 flex flex-col gap-2">
            {episode.my_request ? (
              <div className="flex items-center gap-3 flex-wrap">
                <span className="text-white/60 text-sm">Заявка на участие отправлена — ждёт ответа владельца.</span>
                <button type="button" className="text-white/45 hover:text-white text-xs"
                  onClick={() => void act(() => withdrawRequest(episode.id), 'Заявка отозвана', 'Не удалось отозвать')}>
                  Отозвать
                </button>
              </div>
            ) : (
              <>
                <span className="text-white/60 text-sm">Писать могут только участники. Хотите в историю — попроситесь:</span>
                <div className="flex flex-col sm:flex-row gap-2">
                  <input value={joinText} maxLength={500} onChange={(e) => setJoinText(e.target.value)}
                    placeholder="Пара слов владельцу (по желанию)" className={`${FIELD} flex-1`} />
                  <button type="button" disabled={joining} className="btn-blue !w-full sm:!w-auto !px-5 disabled:opacity-50"
                    onClick={async () => {
                      setJoining(true);
                      await act(() => requestToJoin(episode.id, joinText.trim()), 'Заявка отправлена', 'Не удалось отправить заявку');
                      setJoining(false);
                    }}>
                    Попроситься
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </section>

      <div className="flex gap-2 border-b border-white/10">
        {([['locations', 'Локации'], ['members', 'Участники и роли']] as [Tab, string][]).map(([t, label]) => (
          <button key={t} type="button" onClick={() => setTab(t)}
            className={`relative px-3 sm:px-4 py-2 -mb-px border-b-2 text-sm uppercase tracking-[0.06em] transition-colors ${
              t === tab ? 'border-gold text-gold' : 'border-transparent text-white/50 hover:text-white'
            }`}>
            {label}
            {t === 'members' && episode.requests_count > 0 && (
              <span className="ml-1.5 px-1.5 rounded-full bg-site-red text-white text-[10px]">{episode.requests_count}</span>
            )}
          </button>
        ))}
      </div>

      {tab === 'locations' && (
        <div className="flex flex-col gap-4">
          {episode.can_manage && (
            <button type="button" onClick={() => setLocationForm('new')} className="btn-blue !w-full sm:!w-auto !px-5 self-start">
              Новая локация
            </button>
          )}
          {episode.locations.length === 0 && (
            <p className="text-white/40 text-sm italic">
              {episode.can_manage ? 'Локаций пока нет — создайте первую.' : 'Локаций пока нет.'}
            </p>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {episode.locations.map((loc) => (
              <div key={loc.id} className="group relative bg-site-bg backdrop-blur-sm rounded-card border border-white/[0.07] hover:border-gold-dark/50 overflow-hidden flex flex-col transition-colors">
                <Link to={`/episodes/${episode.id}/location/${loc.id}`} className="flex flex-col flex-1">
                  <div className="aspect-[16/8] bg-black/40 overflow-hidden">
                    {loc.image_url && <img src={loc.image_url} alt="" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />}
                  </div>
                  <div className="p-4 flex flex-col gap-1.5 flex-1">
                    <h3 className="text-white text-base font-medium break-words">{loc.name}</h3>
                    {loc.description && <p className="text-white/55 text-sm line-clamp-2 break-words">{loc.description}</p>}
                    <div className="mt-auto pt-1 flex items-center gap-3 text-xs text-white/45">
                      <span className="flex items-center gap-1"><MessageSquare size={13} />{loc.posts_count}</span>
                      {loc.last_post_at && <span>{formatRelativeTime(loc.last_post_at)}</span>}
                    </div>
                  </div>
                </Link>
                {episode.can_manage && (
                  <div className="absolute top-2 right-2 flex gap-1">
                    <button type="button" title="Изменить" onClick={() => setLocationForm(loc)}
                      className="w-8 h-8 flex items-center justify-center rounded-full bg-black/70 text-white/70 hover:text-gold">
                      <Pencil size={14} />
                    </button>
                    <button type="button" title="Удалить" className="w-8 h-8 flex items-center justify-center rounded-full bg-black/70 text-white/70 hover:text-site-red"
                      onClick={() => setConfirm({
                        title: 'Удалить локацию',
                        message: `«${loc.name}» и все посты в ней будут удалены безвозвратно.`,
                        label: 'Удалить',
                        action: () => deleteLocation(episode.id, loc.id),
                      })}>
                      <Trash2 size={14} />
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {tab === 'members' && <EpisodeMembers episode={episode} userId={userId} onChanged={load} />}

      {settings && (
        <EpisodeFormModal episode={episode} onClose={() => setSettings(false)}
          onSaved={() => {
            setSettings(false);
            load();
          }} />
      )}
      {locationForm && (
        <LocationFormModal
          episodeId={episode.id}
          location={locationForm === 'new' ? undefined : locationForm}
          nextOrder={episode.locations.length}
          onClose={() => setLocationForm(null)}
          onSaved={() => {
            setLocationForm(null);
            load();
          }}
        />
      )}
      {confirm && (
        <ConfirmDialog
          title={confirm.title}
          message={confirm.message}
          confirmLabel={confirm.label}
          danger
          onCancel={() => setConfirm(null)}
          onConfirm={() => {
            const c = confirm;
            setConfirm(null);
            void act(c.action, 'Готово', 'Не получилось', c.after);
          }}
        />
      )}
    </div>
  );
};

export default EpisodePage;
