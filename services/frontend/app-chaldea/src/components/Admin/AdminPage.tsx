import { Link } from 'react-router-dom';
import { useAppSelector } from '../../redux/store';
import { selectPermissions, selectRole } from '../../redux/slices/userSlice';
import { hasModuleAccess } from '../../utils/permissions';

interface AdminSection {
  label: string;
  path: string;
  description: string;
  module: string;
}

const sections: AdminSection[] = [
  { label: 'Заявки', path: '/requestsPage', description: 'Модерация заявок на создание персонажей', module: 'characters' },
  { label: 'Айтемы', path: '/admin/items', description: 'Управление предметами и экипировкой', module: 'items' },
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
];

const AdminPage = () => {
  const role = useAppSelector(selectRole);
  const permissions = useAppSelector(selectPermissions);

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
              className="bg-black/50 backdrop-blur-md rounded-card p-6 hover:bg-white/10 transition-colors duration-200 ease-site"
            >
              <h2 className="text-white text-lg font-semibold uppercase tracking-[0.06em] mb-2">
                {section.label}
              </h2>
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
