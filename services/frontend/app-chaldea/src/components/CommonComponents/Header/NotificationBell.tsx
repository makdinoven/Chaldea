import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Bell } from 'react-feather';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  selectUnreadCount,
  selectNotifications,
  selectDropdownOpen,
  toggleDropdown,
  closeDropdown,
  markAllAsRead,
} from '../../../redux/slices/notificationSlice';
import { getIncomingInvites, respondInvite, IncomingInvite } from '../../../api/squads';
import toast from 'react-hot-toast';

const NotificationBell = () => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const unreadCount = useAppSelector(selectUnreadCount);
  const notifications = useAppSelector(selectNotifications);
  const dropdownOpen = useAppSelector(selectDropdownOpen);
  const userId = useAppSelector((state) => state.user.id);
  const characterId = useAppSelector((state) => state.user.character?.id ?? null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // FEAT-144: live party invites shown at the top of the bell with accept/decline.
  const [invites, setInvites] = useState<IncomingInvite[]>([]);
  const [inviteBusy, setInviteBusy] = useState<number | null>(null);

  const loadInvites = useCallback(async () => {
    if (!characterId) {
      setInvites([]);
      return;
    }
    try {
      setInvites(await getIncomingInvites(characterId));
    } catch {
      /* silent — invites are a non-critical bell extra */
    }
  }, [characterId]);

  // Refresh on mount, when the dropdown opens, and whenever a new notification
  // arrives (a party invite also pushes a text notification).
  useEffect(() => {
    loadInvites();
  }, [loadInvites, dropdownOpen, notifications.length]);

  const handleRespondInvite = async (partyId: number, accept: boolean) => {
    if (!characterId || inviteBusy) return;
    setInviteBusy(partyId);
    try {
      await respondInvite(partyId, characterId, accept);
      toast.success(accept ? 'Вы вступили в отряд' : 'Приглашение отклонено');
      await loadInvites();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Не удалось обработать приглашение');
    } finally {
      setInviteBusy(null);
    }
  };

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        dispatch(closeDropdown());
      }
    };

    if (dropdownOpen) {
      document.addEventListener('mousedown', handleClickOutside);
    }

    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [dropdownOpen, dispatch]);

  const handleToggle = () => {
    dispatch(toggleDropdown());
  };

  const handleMarkAllRead = async () => {
    if (!userId) return;
    try {
      await dispatch(markAllAsRead(userId)).unwrap();
    } catch {
      toast.error('Не удалось отметить уведомления как прочитанные');
    }
  };

  const formatTime = (dateStr: string): string => {
    try {
      const date = new Date(dateStr);
      return date.toLocaleString('ru-RU', {
        hour: '2-digit',
        minute: '2-digit',
        day: '2-digit',
        month: '2-digit',
      });
    } catch {
      return '';
    }
  };

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={handleToggle}
        className="relative p-1 text-white hover:text-site-blue transition-colors duration-200 ease-site"
        aria-label="Уведомления"
      >
        <Bell size={26} strokeWidth={2} />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 bg-site-red text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {dropdownOpen && (
        <div className="absolute top-full right-0 mt-2 z-50 dropdown-menu min-w-[300px] max-h-[400px]">
          <div className="px-4 py-2 border-b border-white/10">
            <span className="nav-link text-sm">
              Уведомления
            </span>
          </div>

          {/* FEAT-144: actionable party invites */}
          {invites.length > 0 && (
            <div className="border-b border-white/10">
              {invites.map((inv) => (
                <div key={inv.party_id} className="px-4 py-3 bg-gold/[0.06]">
                  <p className="text-white text-sm font-montserrat">
                    <span className="gold-text">{inv.leader_name ?? 'Игрок'}</span>
                    {' приглашает в отряд «'}
                    {inv.party_name}
                    {'»'}
                  </p>
                  <div className="flex gap-2 mt-2">
                    <button
                      disabled={inviteBusy === inv.party_id}
                      onClick={() => handleRespondInvite(inv.party_id, true)}
                      className="px-3 py-1 rounded-lg border border-emerald-400/40 text-emerald-300 text-xs hover:bg-emerald-400/10 transition disabled:opacity-50"
                    >
                      Принять
                    </button>
                    <button
                      disabled={inviteBusy === inv.party_id}
                      onClick={() => handleRespondInvite(inv.party_id, false)}
                      className="px-3 py-1 rounded-lg border border-white/15 text-white/60 text-xs hover:bg-white/5 transition disabled:opacity-50"
                    >
                      Отклонить
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}

          <div className="overflow-y-auto max-h-[300px] gold-scrollbar">
            {notifications.length === 0 ? (
              <div className="px-4 py-6 text-center text-white/50 text-sm font-montserrat">
                Нет уведомлений
              </div>
            ) : (
              notifications.map((notification) => (
                <div
                  key={notification.id}
                  className={`px-4 py-3 border-b border-white/5 ${
                    notification.status === 'unread' ? 'bg-white/5' : ''
                  }`}
                >
                  <p className="text-white text-sm font-montserrat">
                    {notification.message}
                  </p>
                  <div className="flex items-center justify-between mt-1">
                    <span className="text-white/40 text-xs font-montserrat">
                      {formatTime(notification.created_at)}
                    </span>
                    {notification.link && (
                      <button
                        onClick={() => {
                          navigate(notification.link!);
                          dispatch(closeDropdown());
                        }}
                        className="text-xs text-site-blue hover:text-gold-light font-montserrat transition-colors duration-200 ease-site cursor-pointer"
                      >
                        Открыть бой
                      </button>
                    )}
                  </div>
                </div>
              ))
            )}
          </div>

          {unreadCount > 0 && (
            <div className="px-4 py-2 border-t border-white/10">
              <button
                onClick={handleMarkAllRead}
                className="text-sm text-site-blue hover:text-gold-light font-montserrat transition-colors duration-200 ease-site"
              >
                Отметить все как прочитанные
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

export default NotificationBell;
