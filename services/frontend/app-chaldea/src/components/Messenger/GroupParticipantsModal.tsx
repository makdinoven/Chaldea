import { useState, useEffect, useCallback, useMemo } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { X, UserPlus, UserX, Image as ImageIcon } from 'react-feather';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { setConversationAvatar } from '../../redux/slices/messengerSlice';
import {
  getGroupParticipants,
  addParticipants,
  removeParticipant,
  uploadGroupAvatar,
} from '../../api/messengerApi';
import { fetchAllUsers } from '../../api/usersApi';
import type { GroupParticipant } from '../../types/messenger';
import type { UserPublicItem } from '../../types/users';
import AvatarWithFrame from '../common/AvatarWithFrame';

interface GroupParticipantsModalProps {
  isOpen: boolean;
  onClose: () => void;
  conversationId: number;
  conversationTitle: string;
}

const Spinner = () => (
  <div className="w-5 h-5 border-2 border-gold/30 border-t-gold rounded-full animate-spin" />
);

const GroupParticipantsModal = ({
  isOpen,
  onClose,
  conversationId,
  conversationTitle,
}: GroupParticipantsModalProps) => {
  const dispatch = useAppDispatch();
  const currentUserId = useAppSelector((s) => s.user.id) as number | null;

  const [participants, setParticipants] = useState<GroupParticipant[]>([]);
  const [createdBy, setCreatedBy] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [uploadingAvatar, setUploadingAvatar] = useState(false);

  const [showAdd, setShowAdd] = useState(false);
  const [allUsers, setAllUsers] = useState<UserPublicItem[]>([]);
  const [search, setSearch] = useState('');

  const isCreator = createdBy !== null && createdBy === currentUserId;

  const load = useCallback(() => {
    setLoading(true);
    getGroupParticipants(conversationId)
      .then((resp) => {
        setParticipants(resp.data.participants);
        setCreatedBy(resp.data.created_by);
      })
      .catch(() => toast.error('Не удалось загрузить участников'))
      .finally(() => setLoading(false));
  }, [conversationId]);

  useEffect(() => {
    if (isOpen) load();
  }, [isOpen, load]);

  useEffect(() => {
    if (!isOpen) {
      setShowAdd(false);
      setSearch('');
    }
  }, [isOpen]);

  useEffect(() => {
    if (!showAdd || allUsers.length > 0) return;
    fetchAllUsers(1, 100)
      .then((r) => setAllUsers(r.data.items))
      .catch(() => {});
  }, [showAdd, allUsers.length]);

  const handleKick = useCallback(
    (userId: number) => {
      removeParticipant(conversationId, userId)
        .then(() => setParticipants((p) => p.filter((x) => x.user_id !== userId)))
        .catch(() => toast.error('Не удалось исключить участника'));
    },
    [conversationId],
  );

  const handleAdd = useCallback(
    (userId: number) => {
      addParticipants(conversationId, { user_ids: [userId] })
        .then(() => {
          load();
          setSearch('');
        })
        .catch(() => toast.error('Не удалось добавить участника'));
    },
    [conversationId, load],
  );

  const handleAvatarChange = useCallback(
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      e.target.value = '';
      if (!file) return;
      setUploadingAvatar(true);
      try {
        const resp = await uploadGroupAvatar(conversationId, file);
        dispatch(setConversationAvatar({ conversationId, avatar: resp.data.avatar_url }));
        toast.success('Аватар обновлён');
      } catch {
        toast.error('Не удалось загрузить аватар');
      } finally {
        setUploadingAvatar(false);
      }
    },
    [conversationId, dispatch],
  );

  const existingIds = useMemo(
    () => new Set(participants.map((p) => p.user_id)),
    [participants],
  );
  const filteredUsers = useMemo(() => {
    const q = search.trim().toLowerCase();
    return allUsers.filter(
      (u) => !existingIds.has(u.id) && (!q || u.username.toLowerCase().includes(q)),
    );
  }, [allUsers, existingIds, search]);

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="modal-overlay" onClick={onClose}>
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="modal-content gold-outline gold-outline-thick w-full max-w-md mx-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4 gap-2">
              <h2 className="gold-text text-xl font-medium uppercase truncate">
                {conversationTitle || 'Участники'}
              </h2>
              <button
                onClick={onClose}
                className="text-white/40 hover:text-white/70 cursor-pointer flex-shrink-0"
                aria-label="Закрыть"
              >
                <X size={18} />
              </button>
            </div>

            {/* Creator: edit avatar */}
            {isCreator && (
              <label className="flex items-center gap-2 mb-4 w-fit text-site-blue text-sm cursor-pointer hover:text-gold-light transition-colors duration-200 ease-site">
                {uploadingAvatar ? <Spinner /> : <ImageIcon size={16} />}
                Изменить аватар группы
                <input type="file" accept="image/*" onChange={handleAvatarChange} className="hidden" />
              </label>
            )}

            {/* Participants */}
            <div className="max-h-[300px] overflow-y-auto gold-scrollbar mb-3">
              {loading ? (
                <div className="flex items-center justify-center py-6">
                  <Spinner />
                </div>
              ) : (
                participants.map((p) => (
                  <div key={p.user_id} className="flex items-center gap-3 px-1 py-2">
                    <AvatarWithFrame
                      avatarUrl={p.avatar}
                      frameSlug={p.avatar_frame}
                      pixelSize={36}
                      rounded="full"
                      username={p.username ?? ''}
                    />
                    <div className="flex-1 min-w-0 flex items-center gap-2">
                      <span className="text-white text-sm truncate">
                        {p.username ?? 'Неизвестный'}
                      </span>
                      {p.is_creator && (
                        <span className="text-gold text-[10px] uppercase tracking-wider flex-shrink-0">
                          создатель
                        </span>
                      )}
                    </div>
                    {isCreator && !p.is_creator && (
                      <button
                        onClick={() => handleKick(p.user_id)}
                        className="text-white/40 hover:text-site-red p-1 cursor-pointer flex-shrink-0"
                        title="Исключить"
                        aria-label={`Исключить ${p.username ?? ''}`}
                      >
                        <UserX size={16} />
                      </button>
                    )}
                  </div>
                ))
              )}
            </div>

            {/* Creator: add participant */}
            {isCreator && (showAdd ? (
              <div>
                <input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Найти пользователя..."
                  className="input-underline w-full text-sm !py-1.5 mb-2"
                  autoFocus
                />
                <div className="max-h-[160px] overflow-y-auto gold-scrollbar border border-white/10 rounded-card">
                  {filteredUsers.length === 0 ? (
                    <div className="text-center text-white/40 text-xs py-4">Никого не найдено</div>
                  ) : (
                    filteredUsers.slice(0, 50).map((u) => (
                      <button
                        key={u.id}
                        onClick={() => handleAdd(u.id)}
                        className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-white/[0.04] transition-colors duration-200 ease-site cursor-pointer"
                      >
                        <div className="w-7 h-7 rounded-full overflow-hidden bg-white/10 flex-shrink-0 border border-white/15">
                          {u.avatar ? (
                            <img src={u.avatar} alt={u.username} className="w-full h-full object-cover" />
                          ) : (
                            <div className="w-full h-full flex items-center justify-center text-white/40 text-xs">
                              {u.username.charAt(0).toUpperCase()}
                            </div>
                          )}
                        </div>
                        <span className="text-white text-sm truncate flex-1">{u.username}</span>
                        <UserPlus size={14} className="text-site-blue flex-shrink-0" />
                      </button>
                    ))
                  )}
                </div>
                <button onClick={() => setShowAdd(false)} className="btn-line !px-3 !py-1 !text-sm mt-2">
                  Готово
                </button>
              </div>
            ) : (
              <button
                onClick={() => setShowAdd(true)}
                className="btn-blue !px-3 !py-1.5 !text-sm flex items-center gap-1.5"
              >
                <UserPlus size={14} /> Добавить участника
              </button>
            ))}
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};

export default GroupParticipantsModal;
