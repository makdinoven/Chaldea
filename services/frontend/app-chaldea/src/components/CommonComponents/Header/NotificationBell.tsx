import { useEffect, useRef } from 'react';
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
import toast from 'react-hot-toast';

const NotificationBell = () => {
  const dispatch = useAppDispatch();
  const unreadCount = useAppSelector(selectUnreadCount);
  const notifications = useAppSelector(selectNotifications);
  const dropdownOpen = useAppSelector(selectDropdownOpen);
  const userId = useAppSelector((state) => state.user.id);
  const dropdownRef = useRef<HTMLDivElement>(null);

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
        <Bell size={32} strokeWidth={2} />
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
                  <span className="text-white/40 text-xs font-montserrat mt-1 block">
                    {formatTime(notification.created_at)}
                  </span>
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
