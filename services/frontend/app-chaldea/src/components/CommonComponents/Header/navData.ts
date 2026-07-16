// Shared navigation data for the desktop header (NavLinks/MegaMenu)
// and the mobile header accordion (MobileHeader). Single source of truth.

export interface NavLinkItem {
  label: string;
  path: string;
}

export interface MegaMenuCategory {
  title: string;
  links: NavLinkItem[];
}

export interface NavItem {
  label: string;
  path: string;
  megaMenu?: MegaMenuCategory[];
}

export const navItems: NavItem[] = [
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
          { label: 'Архив', path: '/archive' },
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
  },
  {
    label: 'ТИКЕТ',
    path: '/support',
  },
];
