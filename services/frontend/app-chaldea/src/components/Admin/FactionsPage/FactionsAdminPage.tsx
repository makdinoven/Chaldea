import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft } from 'lucide-react';
import { useAppSelector } from '../../../redux/store';
import { selectPermissions } from '../../../redux/slices/userSlice';
import { hasPermission } from '../../../utils/permissions';
import { SubTabs } from './adminShared';
import FactionsListTab from './FactionsListTab';
import HostilitiesTab from './HostilitiesTab';
import ApplicationsTab from './ApplicationsTab';
import MembersTab from './MembersTab';
import FactionSettingsTab from './FactionSettingsTab';
import EconTemplatesTab from './EconTemplatesTab';

type TabKey = 'factions' | 'hostility' | 'applications' | 'members' | 'templates' | 'settings';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'factions', label: 'Фракции' },
  { key: 'hostility', label: 'Враждебность' },
  { key: 'applications', label: 'Заявки' },
  { key: 'members', label: 'Участники' },
  { key: 'templates', label: 'Шаблоны экономики' },
  { key: 'settings', label: 'Настройки' },
];

/**
 * FEAT-205 admin «Фракции». `factions:read` opens the page; editing needs `factions:edit`, deleting
 * `factions:delete`, applications / members `factions:manage`, the settings `factions:settings`.
 * Per-character view (memberships, reward deliveries) lives in the character card.
 */
const FactionsAdminPage = () => {
  const permissions = useAppSelector(selectPermissions);
  const perms = {
    edit: hasPermission(permissions, 'factions:edit'),
    remove: hasPermission(permissions, 'factions:delete'),
    manage: hasPermission(permissions, 'factions:manage'),
    settings: hasPermission(permissions, 'factions:settings'),
    economy: hasPermission(permissions, 'factions:economy'),
  };
  const [tab, setTab] = useState<TabKey>('factions');

  return (
    <div className="w-full max-w-container mx-auto flex flex-col gap-5 pb-10">
      <Link to="/admin" className="self-start text-white/60 hover:text-white text-sm flex items-center gap-1">
        <ArrowLeft size={15} />
        Админ-панель
      </Link>
      <div className="flex flex-col gap-1.5">
        <h1 className="gold-text text-2xl sm:text-3xl font-semibold uppercase tracking-[0.06em]">Фракции</h1>
        <p className="text-white/60 text-sm max-w-3xl">
          Лорные фракции: звания с условиями и наградами, условия вступления, враждебные пары, заявки во фракции «по
          приглашению», участники и сроки, экономика (казна, условные участники, интенданты — вкладка «Экономика» фракции). Фракции персонажа и выдачу наград за звания смотрите во вкладке «Фракции»
          его карточки в разделе «Персонажи».
        </p>
      </div>

      <SubTabs<TabKey> tabs={TABS} active={tab} onChange={setTab} />

      {tab === 'factions' && <FactionsListTab canEdit={perms.edit} canDelete={perms.remove} />}
      {tab === 'hostility' && <HostilitiesTab canEdit={perms.edit} />}
      {tab === 'applications' && <ApplicationsTab canManage={perms.manage} />}
      {tab === 'members' && <MembersTab canManage={perms.manage} />}
      {tab === 'templates' && <EconTemplatesTab canEdit={perms.economy} />}
      {tab === 'settings' && <FactionSettingsTab canEdit={perms.settings} />}
    </div>
  );
};

export default FactionsAdminPage;
