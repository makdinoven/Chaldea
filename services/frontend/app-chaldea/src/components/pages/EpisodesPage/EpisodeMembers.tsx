import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { Pencil, Plus, Trash2, UserMinus, Crown } from 'lucide-react';
import {
  addMember,
  answerRequest,
  createRole,
  deleteRole,
  listRequests,
  MEMBER_ROLE_LABEL,
  removeMember,
  searchUsers,
  setMemberRole,
  type EpisodeDetail,
  type JoinRequest,
  type MiniRole,
  type UserBrief,
} from '../../../api/episodes';
import { apiErrorMessage } from '../../../api/errors';
import ConfirmDialog from '../LocationPage/ConfirmDialog';
import RoleFormModal from './RoleFormModal';
import { FIELD } from './EpisodeFormModal';

interface EpisodeMembersProps {
  episode: EpisodeDetail;
  userId: number | null;
  onChanged: () => void;
}

interface Confirm {
  title: string;
  message: string;
  label: string;
  action: () => Promise<unknown>;
  done: string;
}

const Avatar = ({ src, size = 'w-9 h-9' }: { src: string | null; size?: string }) => (
  <div className={`${size} rounded-full overflow-hidden bg-black/40 border border-gold-dark/30 shrink-0`}>
    {src && <img src={src} alt="" className="w-full h-full object-cover" />}
  </div>
);

/** Members, their mini-roles, join requests and adding players. */
const EpisodeMembers = ({ episode, userId, onChanged }: EpisodeMembersProps) => {
  const [editing, setEditing] = useState<MiniRole | null>(null);
  const [confirm, setConfirm] = useState<Confirm | null>(null);
  const [requests, setRequests] = useState<JoinRequest[]>([]);
  const [query, setQuery] = useState('');
  const [found, setFound] = useState<UserBrief[]>([]);
  const manage = episode.can_manage;
  const ownerRights = episode.can_own;
  const memberIds = new Set(episode.members.map((m) => m.user_id));

  const run = async (job: () => Promise<unknown>, done: string, failed: string) => {
    try {
      await job();
      toast.success(done);
      onChanged();
    } catch (e) {
      toast.error(apiErrorMessage(e, failed));
    }
  };

  useEffect(() => {
    if (!manage || !episode.requests_count) {
      setRequests([]);
      return;
    }
    listRequests(episode.id)
      .then(setRequests)
      .catch((e) => toast.error(apiErrorMessage(e, 'Не удалось загрузить заявки')));
  }, [manage, episode.id, episode.requests_count]);

  useEffect(() => {
    if (!manage || query.trim().length < 2) {
      setFound([]);
      return;
    }
    const t = setTimeout(() => {
      searchUsers(episode.id, query.trim())
        .then(setFound)
        .catch((e) => toast.error(apiErrorMessage(e, 'Поиск не удался')));
    }, 300);
    return () => clearTimeout(t);
  }, [manage, episode.id, query]);

  return (
    <div className="flex flex-col gap-5">
      {manage && requests.length > 0 && (
        <section className="gray-bg p-4 flex flex-col gap-3">
          <h3 className="gold-text text-sm font-medium uppercase tracking-[0.06em]">Заявки на участие</h3>
          {requests.map((r) => (
            <div key={r.id} className="flex flex-col sm:flex-row sm:items-center gap-3">
              <div className="flex items-center gap-3 min-w-0 flex-1">
                <Avatar src={r.avatar} />
                <div className="min-w-0">
                  <p className="text-white text-sm truncate">{r.username}</p>
                  {r.message && <p className="text-white/55 text-xs break-words">{r.message}</p>}
                </div>
              </div>
              <div className="flex gap-2">
                <button type="button" className="btn-blue !w-auto !px-4 !py-1.5 text-xs"
                  onClick={() => void run(() => answerRequest(episode.id, r.id, true), `${r.username} — в эпизоде`, 'Не удалось принять')}>
                  Принять
                </button>
                <button type="button" className="btn-line !w-auto !px-4 !py-1.5 text-xs"
                  onClick={() => void run(() => answerRequest(episode.id, r.id, false), 'Заявка отклонена', 'Не удалось отклонить')}>
                  Отклонить
                </button>
              </div>
            </div>
          ))}
        </section>
      )}

      {manage && (
        <section className="flex flex-col gap-2">
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Добавить игрока: начните вводить ник"
            className={FIELD} />
          {found.length > 0 && (
            <div className="bg-black/60 border border-white/10 rounded-card divide-y divide-white/5">
              {found.map((u) => (
                <div key={u.id} className="flex items-center gap-3 px-3 py-2">
                  <Avatar src={u.avatar} size="w-7 h-7" />
                  <span className="text-white text-sm flex-1 truncate">{u.username}</span>
                  {memberIds.has(u.id) ? (
                    <span className="text-white/40 text-xs">уже участник</span>
                  ) : (
                    <button type="button" className="text-site-blue hover:text-white text-xs"
                      onClick={() => void run(async () => {
                        await addMember(episode.id, u.id);
                        setQuery('');
                      }, `${u.username} — в эпизоде`, 'Не удалось добавить')}>
                      Добавить
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      <div className="flex flex-col gap-3">
        {episode.members.map((m) => {
          const isMe = m.user_id === userId;
          const canRemove = m.role !== 'owner' && !isMe && manage && (m.role !== 'master' || ownerRights);
          return (
            <article key={m.user_id} className="bg-site-bg backdrop-blur-sm rounded-card border border-white/[0.07] p-4 flex flex-col gap-3">
              <div className="flex items-center gap-3 flex-wrap">
                <Avatar src={m.avatar} />
                <div className="min-w-0 flex-1">
                  <p className="text-white text-sm truncate">{m.username ?? `Игрок #${m.user_id}`}{isMe && <span className="text-white/40"> (вы)</span>}</p>
                  <p className={`text-xs ${m.role === 'player' ? 'text-white/45' : 'text-gold'}`}>{MEMBER_ROLE_LABEL[m.role]}</p>
                </div>
                <div className="flex items-center gap-1">
                  {ownerRights && m.role !== 'owner' && (
                    <button type="button" title={m.role === 'master' ? 'Снять мастера' : 'Сделать мастером'}
                      className={`w-8 h-8 flex items-center justify-center rounded-[8px] transition-colors ${m.role === 'master' ? 'text-gold' : 'text-white/40 hover:text-gold'}`}
                      onClick={() => void run(() => setMemberRole(episode.id, m.user_id, m.role === 'master' ? 'player' : 'master'),
                        m.role === 'master' ? 'Больше не мастер' : 'Теперь мастер', 'Не удалось сменить права')}>
                      <Crown size={16} />
                    </button>
                  )}
                  {manage && (
                    <button type="button" title="Выдать роль" className="w-8 h-8 flex items-center justify-center rounded-[8px] text-white/40 hover:text-site-blue transition-colors"
                      onClick={() => void run(() => createRole(episode.id, m.user_id), 'Роль выдана — её можно оформить', 'Не удалось выдать роль')}>
                      <Plus size={17} />
                    </button>
                  )}
                  {canRemove && (
                    <button type="button" title="Исключить" className="w-8 h-8 flex items-center justify-center rounded-[8px] text-white/40 hover:text-site-red transition-colors"
                      onClick={() => setConfirm({
                        title: 'Исключить участника',
                        message: `${m.username} больше не сможет писать в эпизоде. Его посты останутся.`,
                        label: 'Исключить',
                        action: () => removeMember(episode.id, m.user_id),
                        done: 'Участник исключён',
                      })}>
                      <UserMinus size={16} />
                    </button>
                  )}
                </div>
              </div>

              {m.roles.length > 0 ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                  {m.roles.map((r) => (
                    <div key={r.id} className="flex items-center gap-3 bg-black/30 rounded-card px-3 py-2 min-w-0">
                      <Avatar src={r.avatar_url} />
                      <div className="min-w-0 flex-1">
                        <p className="text-white text-sm truncate">{r.name}</p>
                        {r.description && <p className="text-white/45 text-xs truncate">{r.description}</p>}
                      </div>
                      {(isMe || manage) && (
                        <button type="button" title="Оформить роль" onClick={() => setEditing(r)}
                          className="w-7 h-7 flex items-center justify-center text-white/40 hover:text-gold transition-colors">
                          <Pencil size={14} />
                        </button>
                      )}
                      {manage && (
                        <button type="button" title="Убрать роль"
                          className="w-7 h-7 flex items-center justify-center text-white/40 hover:text-site-red transition-colors"
                          onClick={() => setConfirm({
                            title: 'Убрать роль',
                            message: `«${r.name}» больше нельзя будет выбрать. Если роль уже писала, её посты останутся.`,
                            label: 'Убрать',
                            action: () => deleteRole(episode.id, r.id),
                            done: 'Роль убрана',
                          })}>
                          <Trash2 size={14} />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-white/35 text-xs">
                  {manage ? 'Ролей пока нет — выдайте кнопкой «+»' : 'Ролей пока нет'}
                </p>
              )}
            </article>
          );
        })}
      </div>

      {editing && (
        <RoleFormModal
          episodeId={episode.id}
          role={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            onChanged();
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
            void run(c.action, c.done, 'Не получилось');
          }}
        />
      )}
    </div>
  );
};

export default EpisodeMembers;
