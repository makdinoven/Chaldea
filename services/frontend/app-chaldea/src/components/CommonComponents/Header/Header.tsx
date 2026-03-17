import { useEffect } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { MessageSquare, User } from 'react-feather';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import { getMe, logout } from '../../../redux/slices/userSlice';
import NavLinks from './NavLinks';
import SearchInput from './SearchInput';
import AvatarDropdown from './AvatarDropdown';
import NotificationBell from './NotificationBell';
import AdminMenu from './AdminMenu';
import { DropdownLink } from './types';
import logo from '../../../assets/logo.png';

const Header = () => {
  const location = useLocation();
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const { username, avatar, character, role } = useAppSelector(
    (state) => state.user,
  );

  useEffect(() => {
    dispatch(getMe());
  }, [location.pathname, dispatch]);

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
      ]
    : [
        { label: 'Создать', path: '/createCharacter' },
        { label: 'Выбрать', path: '/selectCharacter' },
      ];

  const characterAvatar = character?.avatar ?? '';
  const userAvatar = avatar ?? '';

  return (
    <header className="relative w-full max-w-[1240px] mx-auto pt-5 flex items-center justify-between mb-20">
      {/* Left section: Logo + Nav */}
      <div className="flex items-center gap-10">
        <Link to="/home" className="flex-shrink-0">
          <div className="w-20 h-20 rounded-card-lg overflow-hidden">
            <img
              src={logo}
              alt="Логотип"
              className="w-full h-full object-cover"
            />
          </div>
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

        <button
          className="p-1 text-white hover:text-site-blue transition-colors duration-200 ease-site"
          aria-label="Сообщения"
        >
          <MessageSquare size={32} strokeWidth={2} />
        </button>

        <AdminMenu role={role} />
      </div>
    </header>
  );
};

export default Header;
