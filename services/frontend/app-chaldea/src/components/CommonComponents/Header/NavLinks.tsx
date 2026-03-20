import { Link } from 'react-router-dom';
import MegaMenu from './MegaMenu';

interface MegaMenuCategory {
  title: string;
  links: { label: string; path: string }[];
}

interface NavItem {
  label: string;
  path: string;
  megaMenu?: MegaMenuCategory[];
}

const navItems: NavItem[] = [
  {
    label: 'ГЛАВНАЯ',
    path: '/home',
    megaMenu: [
      {
        title: 'ОБЩЕЕ',
        links: [
          { label: 'Поиск соигрока', path: '/search-player' },
          { label: 'Администрация', path: '/administration' },
          { label: 'Предложения', path: '/suggestions' },
          { label: 'Фандом', path: '/fandom' },
        ],
      },
      {
        title: 'НОВОСТИ',
        links: [
          { label: 'Обновления', path: '/news/updates' },
          { label: 'Технобук', path: '/news/technobook' },
          { label: 'Анонсы', path: '/news/announcements' },
          { label: 'Ивенты', path: '/news/events' },
        ],
      },
      {
        title: 'ИГРОВОЙ МИР',
        links: [
          { label: 'Персонажи', path: '/characters' },
          { label: 'Карта мира', path: '/world' },
          { label: 'Вестник', path: '/herald' },
        ],
      },
      {
        title: 'ПРОКАЧКА',
        links: [
          { label: 'Предметы', path: '/items' },
          { label: 'Аукцион', path: '/auction' },
          { label: 'Навыки', path: '/skills' },
        ],
      },
      {
        title: 'МАГАЗИН',
        links: [
          { label: 'Персонаж', path: '/shop/character' },
          { label: 'Рулетки', path: '/shop/roulette' },
          { label: 'Валюта', path: '/shop/currency' },
          { label: 'Гачи', path: '/shop/gacha' },
        ],
      },
    ],
  },
  {
    label: 'ПРАВИЛА',
    path: '/rules',
  },
  {
    label: 'СОБЫТИЯ',
    path: '/events',
    megaMenu: [
      {
        title: 'СОБЫТИЯ',
        links: [
          { label: 'Текущие ивенты', path: '/events/current' },
          { label: 'Архив', path: '/events/archive' },
          { label: 'Календарь', path: '/events/calendar' },
        ],
      },
    ],
  },
  {
    label: 'ТИКЕТ',
    path: '/support',
  },
];

const NavLinks = () => {
  return (
    <nav className="flex items-center gap-10">
      {navItems.map((item) =>
        item.megaMenu ? (
          <div key={item.label} className="group/nav relative pb-2 -mb-2">
            <Link to={item.path} className="nav-link text-base">
              {item.label}
            </Link>
            {/* Invisible bridge: padding area extends hover zone down to the dropdown */}
            <div
              className={`hidden group-hover/nav:block absolute z-50 pt-2 left-0`}
              style={{ top: '100%' }}
            >
              <MegaMenu categories={item.megaMenu} />
            </div>
          </div>
        ) : (
          <Link key={item.label} to={item.path} className="nav-link text-base">
            {item.label}
          </Link>
        ),
      )}
    </nav>
  );
};

export default NavLinks;
