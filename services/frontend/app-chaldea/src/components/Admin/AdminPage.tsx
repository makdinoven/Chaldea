import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { selectPermissions, selectRole } from '../../redux/slices/userSlice';
import { fetchAdminOpenCount, selectAdminOpenCount } from '../../redux/slices/ticketSlice';
import { hasModuleAccess } from '../../utils/permissions';
import { BASE_URL_DEFAULT } from '../../api/api';

interface AdminSection {
  label: string;
  path: string;
  description: string;
  module: string;
}

const sections: AdminSection[] = [
  { label: 'Тикеты', path: '/admin/tickets', description: 'Управление тикетами поддержки', module: 'tickets' },
  { label: 'Заявки', path: '/requestsPage', description: 'Модерация заявок на создание персонажей', module: 'characters' },
  { label: 'Айтемы', path: '/admin/items', description: 'Управление предметами и экипировкой', module: 'items' },
  { label: 'Крафтовые предметы', path: '/admin/craft-items', description: 'Чертежи, рецепты, камни, руны, ресурсы', module: 'items' },
  { label: 'Локации', path: '/admin/locations', description: 'Редактирование мира, регионов и локаций', module: 'locations' },
  { label: 'Навыки', path: '/home/admin/skills', description: 'Редактирование деревьев навыков', module: 'skills' },
  { label: 'Деревья классов', path: '/admin/class-trees', description: 'Визуальный редактор деревьев навыков классов и подклассов', module: 'skill_trees' },
  { label: 'Стартовые наборы', path: '/admin/starter-kits', description: 'Настройка стартовых предметов и навыков по классам', module: 'characters' },
  { label: 'Персонажи', path: '/admin/characters', description: 'Управление персонажами всех игроков', module: 'characters' },
  { label: 'Правила', path: '/admin/rules', description: 'Управление блоками правил игры', module: 'rules' },
  { label: 'Пользователи и роли', path: '/admin/users-roles', description: 'Управление ролями, правами доступа и разрешениями', module: 'users' },
  { label: 'Расы', path: '/admin/races', description: 'Управление расами, подрасами и пресетами статов', module: 'races' },
  { label: 'Игровое время', path: '/admin/game-time', description: 'Настройка внутриигрового календаря', module: 'gametime' },
  { label: 'Модерация постов', path: '/admin/moderation', description: 'Жалобы и запросы на удаление постов локаций', module: 'moderation' },
  { label: 'НПС', path: '/admin/npcs', description: 'Управление НПС: создание, редактирование, размещение на локациях', module: 'npcs' },
  { label: 'Мобы', path: '/admin/mobs', description: 'Управление шаблонами мобов: создание, навыки, лут, спавн', module: 'mobs' },
  { label: 'Активные мобы', path: '/admin/active-mobs', description: 'Мониторинг активных мобов, ручное размещение и удаление', module: 'mobs' },
  { label: 'Бои', path: '/admin/battles', description: 'Мониторинг активных боёв, принудительное завершение', module: 'battles' },
  { label: 'Архив', path: '/admin/archive', description: 'Управление статьями и категориями архива', module: 'archive' },
  { label: 'Перки', path: '/admin/perks', description: 'Управление перками персонажей', module: 'perks' },
  { label: 'Титулы', path: '/admin/titles', description: 'Управление титулами персонажей', module: 'titles' },
  { label: 'Профессии', path: '/admin/professions', description: 'Управление профессиями и рангами', module: 'professions' },
  { label: 'Рецепты', path: '/admin/recipes', description: 'Управление рецептами крафта', module: 'professions' },
  { label: 'Батл Пасс', path: '/admin/battle-pass', description: 'Управление сезонами, наградами и заданиями', module: 'battlepass' },
  { label: 'Косметика', path: '/admin/cosmetics', description: 'Управление рамками и подложками', module: 'cosmetics' },
];

const AdminPage = () => {
  const dispatch = useAppDispatch();
  const role = useAppSelector(selectRole);
  const permissions = useAppSelector(selectPermissions);
  const openTicketCount = useAppSelector(selectAdminOpenCount);
  const [pendingRequestsCount, setPendingRequestsCount] = useState(0);
  const [pendingBattleJoinCount, setPendingBattleJoinCount] = useState(0);

  useEffect(() => {
    if (role === 'admin' || hasModuleAccess(permissions, 'tickets')) {
      dispatch(fetchAdminOpenCount());
    }
    if (role === 'admin' || hasModuleAccess(permissions, 'characters')) {
      const token = localStorage.getItem('accessToken');
      axios.get(`${BASE_URL_DEFAULT}/characters/moderation-requests`, {
        headers: { Authorization: `Bearer ${token}` },
      }).then((res) => {
        const data = res.data as Record<string, { status: string }>;
        const pending = Object.values(data).filter((r) => r.status === 'pending').length;
        setPendingRequestsCount(pending);
      }).catch(() => { /* ignore */ });
    }
    if (role === 'admin' || hasModuleAccess(permissions, 'battles')) {
      const token = localStorage.getItem('accessToken');
      axios.get<{ total: number }>(`${BASE_URL_DEFAULT}/battles/admin/join-requests`, {
        headers: { Authorization: `Bearer ${token}` },
        params: { status: 'pending', per_page: 1 },
      }).then((res) => {
        setPendingBattleJoinCount(res.data.total);
      }).catch(() => { /* ignore */ });
    }
  }, [dispatch, role, permissions]);

  const visibleSections = sections.filter((section) =>
    role === 'admin' || hasModuleAccess(permissions, section.module)
  );

  return (
    <div className="w-full max-w-[1240px] mx-auto">
      <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em] mb-8">
        Админ-панель
      </h1>
      {visibleSections.length === 0 ? (
        <p className="text-white/60 text-base">
          У вас нет доступа к модулям администрирования
        </p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-6">
          {visibleSections.map((section) => (
            <Link
              key={section.path}
              to={section.path}
              className="bg-black/50 backdrop-blur-md rounded-card p-6 hover:bg-white/10 transition-colors duration-200 ease-site relative"
            >
              <div className="flex items-center gap-2 mb-2">
                <h2 className="text-white text-lg font-semibold uppercase tracking-[0.06em]">
                  {section.label}
                </h2>
                {section.module === 'tickets' && openTicketCount > 0 && (
                  <span className="bg-site-red text-white text-xs font-medium px-1.5 py-0.5 rounded-full min-w-[20px] text-center">
                    {openTicketCount}
                  </span>
                )}
                {section.path === '/requestsPage' && pendingRequestsCount > 0 && (
                  <span className="bg-site-red text-white text-xs font-medium px-1.5 py-0.5 rounded-full min-w-[20px] text-center">
                    {pendingRequestsCount}
                  </span>
                )}
                {section.module === 'battles' && pendingBattleJoinCount > 0 && (
                  <span className="bg-site-red text-white text-xs font-medium px-1.5 py-0.5 rounded-full min-w-[20px] text-center">
                    {pendingBattleJoinCount}
                  </span>
                )}
              </div>
              <p className="text-white/60 text-sm">
                {section.description}
              </p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
};

export default AdminPage;
