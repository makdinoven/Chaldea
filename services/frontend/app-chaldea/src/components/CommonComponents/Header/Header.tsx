import { useEffect, useRef } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { MessageCircle, MessageSquare, User } from 'react-feather';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import { getMe, logout } from '../../../redux/slices/userSlice';
import { clearTokens } from '../../../api/authToken';
import { fetchUnreadCount, selectTotalUnread } from '../../../redux/slices/messengerSlice';
import { toggleChat } from '../../../redux/slices/chatSlice';
import NavLinks from './NavLinks';
import SearchInput from './SearchInput';
import AvatarDropdown from './AvatarDropdown';
import NotificationBell from './NotificationBell';
import AdminMenu from './AdminMenu';
import CharacterChip from './CharacterChip';
import MobileHeader from './MobileHeader';
import { DropdownLink } from './types';
import logo from '../../../assets/logo_fog.png';

const Header = () => {
  const location = useLocation();
  const isLocationPage = /^\/location\/\d+/.test(location.pathname);
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const { username, avatar, role } = useAppSelector((state) => state.user);
  const totalUnread = useAppSelector(selectTotalUnread);

  const isInitialMount = useRef(true);

  useEffect(() => {
    if (isInitialMount.current) {
      isInitialMount.current = false;
      return;
    }
    dispatch(getMe());
  }, [location.pathname, dispatch]);

  useEffect(() => {
    dispatch(fetchUnreadCount());
  }, [dispatch]);

  const handleLogout = () => {
    // Explicit user logout: clear BOTH tokens (FEAT-150) — a leftover
    // refreshToken would let the refresh interceptor resurrect the session.
    clearTokens();
    dispatch(logout());
    navigate('/');
  };

  const userLinks: DropdownLink[] = [
    { label: 'Мой профиль', path: '/user-profile' },
    { label: 'Персонаж', path: '/profile' },
    { label: 'Сообщения', path: '/messages' },
    { label: 'Выход', path: '/', onClick: handleLogout },
  ];

  const userAvatar = avatar ?? '';

  return (
    <>
      {/* ===== Desktop header (reference .hdr layout, from lg) ===== */}
      <header
        className={`hidden lg:flex relative z-50 w-full max-w-container mx-auto mt-5 items-center justify-between gap-3 mb-20 px-3 xl:px-6 py-3 ${
          isLocationPage ? 'bg-black/60' : 'bg-black/40'
        } rounded-card backdrop-blur-sm`}
      >
        {/* Left: chat button + logo + nav */}
        <div className="flex items-center gap-3 xl:gap-5 flex-shrink-0">
          <button
            onClick={() => dispatch(toggleChat())}
            title="Открыть чат"
            className="flex-shrink-0 w-12 h-12 flex items-center justify-center rounded-card border border-gold/30 bg-gold/10 text-gold hover:bg-gold/20 hover:text-gold-light transition-colors duration-200 ease-site"
            aria-label="Открыть чат"
          >
            <MessageCircle size={24} strokeWidth={2} />
          </button>

          <Link to="/home" className="flex-shrink-0">
            <img
              src={logo}
              alt="Fall of Gods"
              className="h-12 xl:h-16 w-auto object-contain"
            />
          </Link>

          <NavLinks />
        </div>

        {/* Right: search + character chip + bell + messages + user avatar + admin */}
        <div className="flex items-center gap-2.5 xl:gap-3.5 flex-shrink-0 min-w-0">
          {/* Decorative search — only at full desktop widths, so the header fits at lg */}
          <div className="hidden xl:block">
            <SearchInput />
          </div>

          <CharacterChip />

          <NotificationBell />

          <Link
            to="/messages"
            className="relative p-1 text-white hover:text-site-blue transition-colors duration-200 ease-site"
            aria-label="Сообщения"
          >
            <MessageSquare size={26} strokeWidth={2} />
            {totalUnread > 0 && (
              <span className="absolute -top-1 -right-1 bg-site-red text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center">
                {totalUnread > 99 ? '99+' : totalUnread}
              </span>
            )}
          </Link>

          <AvatarDropdown
            imageSrc={userAvatar}
            altText={username ?? 'Пользователь'}
            size={44}
            links={userLinks}
            placeholderIcon={<User size={20} className="text-white/50" />}
          />

          <AdminMenu role={role} />
        </div>
      </header>

      {/* ===== Mobile header (reference .hdr-m layout, below lg) ===== */}
      <MobileHeader userLinks={userLinks} />
    </>
  );
};

export default Header;
