import { useEffect, useRef } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { MessageSquare, User } from 'react-feather';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import { getMe, logout } from '../../../redux/slices/userSlice';
import { fetchUnreadCount, selectTotalUnread } from '../../../redux/slices/messengerSlice';
import NavLinks from './NavLinks';
import SearchInput from './SearchInput';
import AvatarDropdown from './AvatarDropdown';
import NotificationBell from './NotificationBell';
import AdminMenu from './AdminMenu';
import { DropdownLink } from './types';
import logo from '../../../assets/logo_fog.png';

const Header = () => {
  const location = useLocation();
  const isLocationPage = /^\/location\/\d+/.test(location.pathname);
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const { username, avatar, character, role } = useAppSelector(
    (state) => state.user,
  );
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
    localStorage.removeItem('accessToken');
    dispatch(logout());
    navigate('/');
  };

  const userLinks: DropdownLink[] = [
    { label: 'Мой профиль', path: '/user-profile' },
    { label: 'Персонаж', path: '/profile' },
    { label: 'Сообщения', path: '/messages' },
    { label: 'Выход', path: '/', onClick: handleLogout },
  ];

  const characterLinks: DropdownLink[] = character
    ? [
        { label: 'Профиль', path: '/profile' },
        ...(character.current_location
          ? [
              {
                label: character.current_location.name ?? 'Локация',
                path: `/location/${character.current_location.id}`,
              },
            ]
          : []),
        { label: 'Сменить персонажа', path: '/selectCharacter' },
      ]
    : [
        { label: 'Создать', path: '/createCharacter' },
        { label: 'Выбрать', path: '/selectCharacter' },
      ];

  const characterAvatar = character?.avatar ?? '';
  const userAvatar = avatar ?? '';

  return (
    <header className={`relative z-50 w-full max-w-[1240px] mx-auto mt-5 flex items-center justify-between mb-20 px-4 sm:px-6 py-3 ${isLocationPage ? 'bg-black/60' : 'bg-black/40'} rounded-card backdrop-blur-sm`}>
      {/* Left section: Logo + Nav */}
      <div className="flex items-center gap-10">
        <Link to="/home" className="flex-shrink-0">
          <img
            src={logo}
            alt="Fall of Gods"
            className="h-16 w-auto object-contain"
          />
        </Link>
        <NavLinks />
      </div>

      {/* Right section: Search + Avatars + Icons + Admin */}
      <div className="flex items-center gap-5">
        <SearchInput />

        <AvatarDropdown
          imageSrc={characterAvatar}
          altText={character?.name ?? 'Персонаж'}
          size={64}
          links={characterLinks}
          placeholderIcon={<User size={28} className="text-white/50" />}
        />

        <AvatarDropdown
          imageSrc={userAvatar}
          altText={username ?? 'Пользователь'}
          size={64}
          links={userLinks}
          placeholderIcon={<User size={28} className="text-white/50" />}
        />

        <NotificationBell />

        <Link
          to="/messages"
          className="relative p-1 text-white hover:text-site-blue transition-colors duration-200 ease-site"
          aria-label="Сообщения"
        >
          <MessageSquare size={32} strokeWidth={2} />
          {totalUnread > 0 && (
            <span className="absolute -top-1 -right-1 bg-site-red text-white text-xs font-bold rounded-full w-5 h-5 flex items-center justify-center">
              {totalUnread > 99 ? '99+' : totalUnread}
            </span>
          )}
        </Link>

        <AdminMenu role={role} />
      </div>
    </header>
  );
};

export default Header;
