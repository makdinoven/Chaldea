import { Link } from 'react-router-dom';

interface AdminSection {
  label: string;
  path: string;
  description: string;
}

const sections: AdminSection[] = [
  { label: 'Заявки', path: '/requestsPage', description: 'Модерация заявок на создание персонажей' },
  { label: 'Айтемы', path: '/admin/items', description: 'Управление предметами и экипировкой' },
  { label: 'Локации', path: '/admin/locations', description: 'Редактирование мира, регионов и локаций' },
  { label: 'Навыки', path: '/home/admin/skills', description: 'Редактирование деревьев навыков' },
  { label: 'Стартовые наборы', path: '/admin/starter-kits', description: 'Настройка стартовых предметов и навыков по классам' },
];

const AdminPage = () => {
  return (
    <div className="w-full max-w-[1240px] mx-auto">
      <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em] mb-8">
        Админ-панель
      </h1>
      <div className="grid grid-cols-2 gap-6">
        {sections.map((section) => (
          <Link
            key={section.path}
            to={section.path}
            className="bg-black/50 backdrop-blur-md rounded-[15px] p-6 hover:bg-white/10 transition-colors duration-200 ease-site"
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
    </div>
  );
};

export default AdminPage;
