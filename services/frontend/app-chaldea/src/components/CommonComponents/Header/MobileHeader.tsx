import { useEffect, useRef, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  Bell,
  ChevronDown,
  MapPin,
  Menu,
  MessageCircle,
  MessageSquare,
  Search,
  Shield,
  User,
  X,
} from 'react-feather';
import { AnimatePresence, motion } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import { selectTotalUnread } from '../../../redux/slices/messengerSlice';
import {
  markAllAsRead,
  selectNotifications,
  selectUnreadCount,
} from '../../../redux/slices/notificationSlice';
import { toggleChat } from '../../../redux/slices/chatSlice';
import { isStaff } from '../../../utils/permissions';
import AvatarDropdown from './AvatarDropdown';
import CharacterSwitchDropdown from './CharacterSwitchDropdown';
import { CoinIcon } from './CharacterChip';
import { navItems, NavLinkItem } from './navData';
import { DropdownLink } from './types';
import logo from '../../../assets/logo_fog.png';

interface UnreadBadgeProps {
  count: number;
  className?: string;
}

const UnreadBadge = ({ count, className = '' }: UnreadBadgeProps) => {
  if (count <= 0) return null;
  return (
    <span
      className={`absolute min-w-[18px] h-[18px] px-1 flex items-center justify-center bg-site-red text-white text-[10px] font-bold rounded-full ${className}`}
    >
      {count > 99 ? '99+' : count}
    </span>
  );
};

/** Accordion / plain rows for the collapsible mobile menu, built from navData */
interface MenuRow {
  key: string;
  label: string;
  path?: string;
  links?: NavLinkItem[];
}

const buildMenuRows = (): MenuRow[] => {
  const rows: MenuRow[] = [];
  navItems.forEach((item) => {
    rows.push({ key: item.label, label: item.label, path: item.path });
    item.megaMenu?.forEach((cat) => {
      rows.push({ key: cat.title, label: cat.title, links: cat.links });
    });
  });
  return rows;
};

const menuRows = buildMenuRows();

interface MobileHeaderProps {
  userLinks: DropdownLink[];
}

/**
 * Mobile header (reference `.hdr-m`, shown below lg):
 * top bar = burger (unread badge) / logo / chat button / user avatar;
 * character + location strip below; collapsible menu = search +
 * accordion nav + notifications/messages buttons with badges.
 */
const MobileHeader = ({ userLinks }: MobileHeaderProps) => {
  const location = useLocation();
  const dispatch = useAppDispatch();
  const isLocationPage = /^\/location\/\d+/.test(location.pathname);

  const { username, avatar, character, role, id: userId } = useAppSelector(
    (state) => state.user,
  );
  const totalUnread = useAppSelector(selectTotalUnread);
  const notifUnread = useAppSelector(selectUnreadCount);
  const notifications = useAppSelector(selectNotifications);

  const [menuOpen, setMenuOpen] = useState(false);
  const [expandedSection, setExpandedSection] = useState<string | null>(null);
  const [notifOpen, setNotifOpen] = useState(false);
  const [chipOpen, setChipOpen] = useState(false);
  const stripRef = useRef<HTMLDivElement>(null);

  const burgerBadge = totalUnread + notifUnread;

  // Close the character dropdown on outside tap
  useEffect(() => {
    if (!chipOpen) return;
    const handleClickOutside = (event: MouseEvent) => {
      if (stripRef.current && !stripRef.current.contains(event.target as Node)) {
        setChipOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [chipOpen]);

  // Collapse everything on navigation
  useEffect(() => {
    setMenuOpen(false);
    setNotifOpen(false);
    setChipOpen(false);
  }, [location.pathname]);

  const closeMenu = () => {
    setMenuOpen(false);
    setNotifOpen(false);
  };

  const handleChatOpen = () => {
    dispatch(toggleChat());
    closeMenu();
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
      return new Date(dateStr).toLocaleString('ru-RU', {
        hour: '2-digit',
        minute: '2-digit',
        day: '2-digit',
        month: '2-digit',
      });
    } catch {
      return '';
    }
  };

  const coins = typeof character?.currency_balance === 'number' ? character.currency_balance : null;
  const level = typeof character?.level === 'number' ? character.level : null;

  return (
    <header
      className={`lg:hidden relative z-50 w-full max-w-container mx-auto mt-5 mb-20 flex flex-col ${
        isLocationPage ? 'bg-black/60' : 'bg-black/40'
      } rounded-card backdrop-blur-sm`}
    >
      {/* ===== Top bar: burger / logo / chat / user avatar ===== */}
      <div className="flex items-center justify-between gap-2.5 px-3 py-2.5">
        <button
          onClick={() => setMenuOpen((prev) => !prev)}
          className="relative flex-shrink-0 w-[42px] h-[42px] flex items-center justify-center rounded-card border border-white/10 bg-white/5 text-gold hover:text-gold-light transition-colors duration-200 ease-site"
          aria-label={menuOpen ? 'Закрыть меню' : 'Меню'}
          aria-expanded={menuOpen}
        >
          {menuOpen ? <X size={22} strokeWidth={2.2} /> : <Menu size={22} strokeWidth={2.2} />}
          {!menuOpen && <UnreadBadge count={burgerBadge} className="-top-1.5 -right-1.5" />}
        </button>

        <Link to="/home" className="flex-shrink-0">
          <img src={logo} alt="Fall of Gods" className="h-10 w-auto object-contain" />
        </Link>

        <div className="flex items-center gap-2 flex-shrink-0">
          <button
            onClick={handleChatOpen}
            className="w-[42px] h-[42px] flex items-center justify-center rounded-card border border-gold/30 bg-gold/10 text-gold hover:bg-gold/20 hover:text-gold-light transition-colors duration-200 ease-site"
            aria-label="Чат"
          >
            <MessageCircle size={21} strokeWidth={2} />
          </button>

          <AvatarDropdown
            imageSrc={avatar ?? ''}
            altText={username ?? 'Пользователь'}
            size={42}
            links={userLinks}
            placeholderIcon={<User size={20} className="text-white/50" />}
          />
        </div>
      </div>

      {/* ===== Character + location strip ===== */}
      <div
        ref={stripRef}
        className={`relative border-t border-white/10 bg-black/20 ${menuOpen ? '' : 'rounded-b-card'}`}
      >
        <div
          role="button"
          tabIndex={0}
          onClick={() => setChipOpen((prev) => !prev)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              setChipOpen((prev) => !prev);
            }
          }}
          className="flex items-center gap-3 px-3.5 py-2.5 cursor-pointer select-none"
          aria-label={character ? `Персонаж: ${character.name}` : 'Персонаж'}
          aria-expanded={chipOpen}
        >
          <div className="w-[38px] h-[38px] rounded-full p-[2px] bg-gradient-to-b from-gold-light to-gold-dark flex-shrink-0">
            <div className="w-full h-full rounded-full bg-site-dark overflow-hidden flex items-center justify-center">
              {character?.avatar ? (
                <img
                  src={character.avatar}
                  alt={character.name}
                  className="w-full h-full object-cover"
                />
              ) : (
                <User size={18} className="text-white/50" />
              )}
            </div>
          </div>

          {character ? (
            <div className="flex flex-col gap-1 flex-1 min-w-0">
              <div className="flex items-center justify-between gap-2">
                <span className="text-white text-[13px] font-medium leading-none truncate">
                  {character.name}
                </span>
                {character.current_location && (
                  <Link
                    to={`/location/${character.current_location.id}`}
                    onClick={(e) => e.stopPropagation()}
                    title="Перейти в локацию"
                    className="flex items-center gap-1 text-site-blue hover:text-gold transition-colors duration-200 ease-site leading-none min-w-0"
                  >
                    <MapPin size={12} className="flex-shrink-0" />
                    <span className="text-[11px] font-medium truncate">
                      {character.current_location.name}
                    </span>
                  </Link>
                )}
              </div>
              <div className="flex items-center gap-3 leading-none">
                {level != null && (
                  <span className="text-white/70 text-[11px]">Ур. {level}</span>
                )}
                {coins != null && (
                  <span className="flex items-center gap-1 text-gold text-[11px]">
                    <CoinIcon size={11} />
                    {coins.toLocaleString('ru-RU')}
                  </span>
                )}
              </div>
            </div>
          ) : (
            <span className="text-white/70 text-[13px] font-medium">Персонаж не выбран</span>
          )}
        </div>

        <AnimatePresence>
          {chipOpen && (
            userId && character ? (
              <CharacterSwitchDropdown
                className="absolute top-full left-3 right-3 mt-1"
                onClose={() => setChipOpen(false)}
              />
            ) : (
              /* Guest or no active character — fallback (current behavior) */
              <motion.div
                initial={{ opacity: 0, y: -5 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -5 }}
                transition={{ duration: 0.15 }}
                className="dropdown-menu absolute top-full left-3 mt-1 z-50"
              >
                <Link to="/createCharacter" className="dropdown-item" onClick={() => setChipOpen(false)}>
                  Создать
                </Link>
                <Link to="/selectCharacter" className="dropdown-item" onClick={() => setChipOpen(false)}>
                  Выбрать
                </Link>
              </motion.div>
            )
          )}
        </AnimatePresence>
      </div>

      {/* ===== Collapsible menu ===== */}
      <AnimatePresence>
        {menuOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="overflow-hidden border-t border-gold/10"
          >
            <div className="flex flex-col px-3.5 pb-4 pt-2">
              {/* Search */}
              <div className="flex items-center gap-2 my-2 px-3 py-2.5 rounded-card border border-white/10 bg-white/5">
                <Search size={16} className="text-white/60 flex-shrink-0" strokeWidth={2} />
                <input
                  type="text"
                  placeholder="ПОИСК"
                  className="flex-1 min-w-0 bg-transparent font-montserrat font-medium text-xs uppercase tracking-[0.06em] text-white placeholder-white/50 outline-none"
                />
              </div>

              {/* Accordion nav */}
              {menuRows.map((row) =>
                row.links ? (
                  <div key={row.key} className="border-b border-white/10">
                    <button
                      onClick={() =>
                        setExpandedSection((prev) => (prev === row.key ? null : row.key))
                      }
                      className="w-full flex items-center justify-between gap-2.5 px-1 py-3.5 nav-link text-sm"
                      aria-expanded={expandedSection === row.key}
                    >
                      <span>{row.label}</span>
                      <ChevronDown
                        size={16}
                        strokeWidth={2.2}
                        className={`flex-shrink-0 transition-transform duration-200 ease-site ${
                          expandedSection === row.key ? 'rotate-180' : ''
                        }`}
                      />
                    </button>
                    <AnimatePresence>
                      {expandedSection === row.key && (
                        <motion.div
                          initial={{ opacity: 0, height: 0 }}
                          animate={{ opacity: 1, height: 'auto' }}
                          exit={{ opacity: 0, height: 0 }}
                          transition={{ duration: 0.15, ease: 'easeOut' }}
                          className="overflow-hidden"
                        >
                          <div className="flex flex-col pb-3 pl-3.5 pr-1">
                            {row.links.map((link) => (
                              <Link
                                key={link.label}
                                to={link.path}
                                onClick={closeMenu}
                                className="py-2 text-white/70 hover:text-site-blue transition-colors duration-200 ease-site text-xs uppercase tracking-[0.05em]"
                              >
                                {link.label}
                              </Link>
                            ))}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </div>
                ) : (
                  <Link
                    key={row.key}
                    to={row.path ?? '/home'}
                    onClick={closeMenu}
                    className="border-b border-white/10 px-1 py-3.5 nav-link text-sm"
                  >
                    {row.label}
                  </Link>
                ),
              )}

              {/* Admin entry */}
              {isStaff(role) && (
                <Link
                  to="/admin"
                  onClick={closeMenu}
                  className="border-b border-white/10 px-1 py-3.5 nav-link text-sm flex items-center gap-2"
                >
                  <Shield size={16} strokeWidth={2.2} className="flex-shrink-0" />
                  АДМИНКА
                </Link>
              )}

              {/* Notifications + messages buttons */}
              <div className="flex gap-2.5 mt-4">
                <button
                  onClick={() => setNotifOpen((prev) => !prev)}
                  className="relative flex-1 flex items-center justify-center gap-2 px-2 py-3 rounded-card border border-white/10 bg-white/5 text-white text-xs font-medium uppercase tracking-[0.04em] hover:text-site-blue transition-colors duration-200 ease-site"
                  aria-expanded={notifOpen}
                >
                  <Bell size={18} strokeWidth={2} className="flex-shrink-0" />
                  Уведомления
                  <UnreadBadge count={notifUnread} className="-top-2 -right-2" />
                </button>
                <Link
                  to="/messages"
                  onClick={closeMenu}
                  className="relative flex-1 flex items-center justify-center gap-2 px-2 py-3 rounded-card border border-white/10 bg-white/5 text-white text-xs font-medium uppercase tracking-[0.04em] hover:text-site-blue transition-colors duration-200 ease-site"
                >
                  <MessageSquare size={18} strokeWidth={2} className="flex-shrink-0" />
                  Сообщения
                  <UnreadBadge count={totalUnread} className="-top-2 -right-2" />
                </Link>
              </div>

              {/* Inline notifications list */}
              <AnimatePresence>
                {notifOpen && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    transition={{ duration: 0.15, ease: 'easeOut' }}
                    className="overflow-hidden"
                  >
                    <div className="mt-2.5 rounded-card border border-white/10 bg-black/30">
                      <div className="overflow-y-auto max-h-[260px] gold-scrollbar">
                        {notifications.length === 0 ? (
                          <div className="px-4 py-5 text-center text-white/50 text-sm font-montserrat">
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
                                  <Link
                                    to={notification.link}
                                    onClick={closeMenu}
                                    className="text-xs text-site-blue hover:text-gold-light font-montserrat transition-colors duration-200 ease-site"
                                  >
                                    Открыть
                                  </Link>
                                )}
                              </div>
                            </div>
                          ))
                        )}
                      </div>
                      {notifUnread > 0 && (
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
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </header>
  );
};

export default MobileHeader;
