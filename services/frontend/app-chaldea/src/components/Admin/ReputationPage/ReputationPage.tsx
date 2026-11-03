import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { useAppSelector } from '../../../redux/store';
import { selectPermissions } from '../../../redux/slices/userSlice';
import { hasPermission } from '../../../utils/permissions';
import ReputationSettingsTab from './ReputationSettingsTab';
import ReputationActionsTab from './ReputationActionsTab';
import ReputationRolesTab from './ReputationRolesTab';

type ReputationTab = 'settings' | 'actions' | 'roles';

const TABS: { key: ReputationTab; label: string }[] = [
  { key: 'settings', label: 'Ступени и общие' },
  { key: 'actions', label: 'Действия' },
  { key: 'roles', label: 'Роли НПС' },
];

/**
 * FEAT-197 admin «Репутация». Moderators (reputation:read + manage) see everything read-only;
 * editing needs `reputation:settings` (admin). Per-character edits live in the character card.
 */
const ReputationPage = () => {
  const canEdit = hasPermission(useAppSelector(selectPermissions), 'reputation:settings');
  const [tab, setTab] = useState<ReputationTab>('settings');

  return (
    <div className="w-full max-w-container mx-auto flex flex-col gap-5 pb-10">
      <Link to="/admin" className="self-start text-white/60 hover:text-white text-sm flex items-center gap-1">
        <ArrowLeft size={15} />
        Админ-панель
      </Link>
      <div className="flex flex-col gap-1.5">
        <h1 className="gold-text text-2xl sm:text-3xl font-semibold uppercase tracking-[0.06em]">Репутация</h1>
        <p className="text-white/60 text-sm max-w-2xl">
          Репутация персонажа в каждом регионе: ступени и их влияние на торговлю, вес действий, вес убийства НПС по
          ролям. Править репутацию конкретного персонажа — во вкладке «Репутация» его карточки в разделе «Персонажи».
        </p>
      </div>

      <div className="flex gap-1 sm:gap-2 border-b border-white/10 overflow-x-auto gold-scrollbar">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`px-3 sm:px-4 py-2 -mb-px border-b-2 text-sm uppercase tracking-[0.06em] whitespace-nowrap transition-colors duration-200 ease-site ${
              t.key === tab ? 'border-gold text-gold' : 'border-transparent text-white/50 hover:text-white'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'settings' && <ReputationSettingsTab canEdit={canEdit} />}
      {tab === 'actions' && <ReputationActionsTab canEdit={canEdit} />}
      {tab === 'roles' && <ReputationRolesTab canEdit={canEdit} />}
    </div>
  );
};

export default ReputationPage;
