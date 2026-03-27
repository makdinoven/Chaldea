import { useState, useEffect, useCallback, useMemo } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { fetchAllUsers } from '../../api/usersApi';
import type { UserPublicItem } from '../../types/users';
import type { ConversationType } from '../../types/messenger';
import toast from 'react-hot-toast';

interface NewConversationModalProps {
  isOpen: boolean;
  isCreating: boolean;
  onClose: () => void;
  onCreate: (type: ConversationType, participantIds: number[], title: string | null) => void;
}

const NewConversationModal = ({
  isOpen,
  isCreating,
  onClose,
  onCreate,
}: NewConversationModalProps) => {
  const [searchQuery, setSearchQuery] = useState('');
  const [users, setUsers] = useState<UserPublicItem[]>([]);
  const [loadingUsers, setLoadingUsers] = useState(false);
  const [selectedUsers, setSelectedUsers] = useState<UserPublicItem[]>([]);
  const [conversationType, setConversationType] = useState<ConversationType>('direct');
  const [groupTitle, setGroupTitle] = useState('');

  // Load users on mount
  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;

    const loadUsers = async () => {
      setLoadingUsers(true);
      try {
        const response = await fetchAllUsers(1, 100);
        if (!cancelled) {
          setUsers(response.data.items);
        }
      } catch {
        if (!cancelled) {
          toast.error('Не удалось загрузить список пользователей');
        }
      } finally {
        if (!cancelled) {
          setLoadingUsers(false);
        }
      }
    };

    loadUsers();
    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  // Reset state when modal opens
  useEffect(() => {
    if (isOpen) {
      setSearchQuery('');
      setSelectedUsers([]);
      setConversationType('direct');
      setGroupTitle('');
    }
  }, [isOpen]);

  // Filter users by search
  const filteredUsers = useMemo(() => {
    if (!searchQuery.trim()) return users;
    const q = searchQuery.toLowerCase();
    return users.filter((u) => u.username.toLowerCase().includes(q));
  }, [users, searchQuery]);

  const toggleUser = useCallback((user: UserPublicItem) => {
    setSelectedUsers((prev) => {
      const exists = prev.some((u) => u.id === user.id);
      if (exists) {
        return prev.filter((u) => u.id !== user.id);
      }
      return [...prev, user];
    });
  }, []);

  const removeUser = useCallback((userId: number) => {
    setSelectedUsers((prev) => prev.filter((u) => u.id !== userId));
  }, []);

  // Auto-switch type based on selection
  useEffect(() => {
    if (selectedUsers.length <= 1) {
      setConversationType('direct');
    }
  }, [selectedUsers.length]);

  const handleCreate = () => {
    if (selectedUsers.length === 0) {
      toast.error('Выберите хотя бы одного участника');
      return;
    }

    const type = selectedUsers.length > 1 ? 'group' : conversationType;
    const title = type === 'group' && groupTitle.trim() ? groupTitle.trim() : null;

    onCreate(
      type,
      selectedUsers.map((u) => u.id),
      title,
    );
  };

  const isSelected = (userId: number) =>
    selectedUsers.some((u) => u.id === userId);

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
            <h2 className="gold-text text-xl font-medium uppercase mb-4">
              Новый диалог
            </h2>

            {/* Type toggle (when multiple users selected) */}
            {selectedUsers.length > 1 && (
              <div className="flex gap-2 mb-4">
                <button
                  onClick={() => setConversationType('direct')}
                  disabled
                  className="flex-1 py-1.5 text-sm rounded-card text-white/30 bg-white/[0.04] cursor-not-allowed"
                >
                  Личный
                </button>
                <button
                  onClick={() => setConversationType('group')}
                  className="flex-1 py-1.5 text-sm rounded-card text-white bg-site-blue/20 border border-site-blue/30"
                >
                  Групповой
                </button>
              </div>
            )}

            {/* Group title */}
            {(selectedUsers.length > 1 || conversationType === 'group') && (
              <div className="mb-4">
                <label className="text-white/50 text-xs uppercase tracking-wider mb-1 block">
                  Название группы
                </label>
                <input
                  type="text"
                  value={groupTitle}
                  onChange={(e) => setGroupTitle(e.target.value)}
                  placeholder="Введите название..."
                  maxLength={100}
                  className="input-underline w-full text-sm !py-1.5"
                />
              </div>
            )}

            {/* Selected users chips */}
            {selectedUsers.length > 0 && (
              <div className="flex flex-wrap gap-2 mb-3">
                {selectedUsers.map((user) => (
                  <span
                    key={user.id}
                    className="inline-flex items-center gap-1 bg-site-blue/20 text-white text-xs rounded-full px-2.5 py-1 border border-site-blue/30"
                  >
                    {user.username}
                    <button
                      onClick={() => removeUser(user.id)}
                      className="text-white/50 hover:text-white ml-0.5 cursor-pointer"
                      aria-label={`Убрать ${user.username}`}
                    >
                      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="w-3 h-3">
                        <line x1="18" y1="6" x2="6" y2="18" />
                        <line x1="6" y1="6" x2="18" y2="18" />
                      </svg>
                    </button>
                  </span>
                ))}
              </div>
            )}

            {/* User search */}
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Найти пользователя..."
              className="input-underline w-full text-sm !py-1.5 mb-3"
            />

            {/* User list */}
            <div className="max-h-[250px] overflow-y-auto gold-scrollbar border border-white/10 rounded-card mb-4">
              {loadingUsers ? (
                <div className="flex items-center justify-center py-6">
                  <div className="w-5 h-5 border-2 border-gold/30 border-t-gold rounded-full animate-spin" />
                </div>
              ) : filteredUsers.length === 0 ? (
                <div className="text-center text-white/40 text-sm py-6">
                  {searchQuery.trim() ? 'Никого не найдено' : 'Нет пользователей'}
                </div>
              ) : (
                filteredUsers.map((user) => (
                  <button
                    key={user.id}
                    onClick={() => toggleUser(user)}
                    className={`w-full flex items-center gap-3 px-3 py-2.5 text-left transition-colors duration-200 ease-site cursor-pointer ${
                      isSelected(user.id)
                        ? 'bg-site-blue/15'
                        : 'hover:bg-white/[0.04]'
                    }`}
                  >
                    {/* Avatar */}
                    <div className="w-8 h-8 rounded-full overflow-hidden bg-white/10 flex-shrink-0 border border-white/15">
                      {user.avatar ? (
                        <img
                          src={user.avatar}
                          alt={user.username}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-white/40 text-xs font-medium">
                          {user.username.charAt(0).toUpperCase()}
                        </div>
                      )}
                    </div>

                    <span className="text-white text-sm truncate flex-1">
                      {user.username}
                    </span>

                    {/* Check indicator */}
                    {isSelected(user.id) && (
                      <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" className="w-4 h-4 text-site-blue flex-shrink-0">
                        <polyline points="20 6 9 17 4 12" />
                      </svg>
                    )}
                  </button>
                ))
              )}
            </div>

            {/* Actions */}
            <div className="flex gap-3 justify-end">
              <button
                onClick={onClose}
                className="btn-line !px-4 !py-1.5 !text-sm"
              >
                Отмена
              </button>
              <button
                onClick={handleCreate}
                disabled={selectedUsers.length === 0 || isCreating}
                className="btn-blue !px-4 !py-1.5 !text-sm disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {isCreating ? 'Создание...' : 'Создать'}
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};

export default NewConversationModal;
