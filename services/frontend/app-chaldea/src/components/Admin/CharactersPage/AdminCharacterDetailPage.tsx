import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import { fetchAdminCharacterById } from '../../../api/adminCharacters';
import { apiErrorMessage } from '../../../api/errors';
import {
  selectAdminCharacters,
  selectSelectedCharacter,
  setSelectedCharacter,
  clearDetail,
} from '../../../redux/slices/adminCharactersSlice';
import GeneralTab from './tabs/GeneralTab';
import AttributesTab from './tabs/AttributesTab';
import InventoryTab from './tabs/InventoryTab';
import SkillsTab from './tabs/SkillsTab';
import ReputationTab from './tabs/ReputationTab';
import FactionsTab from './tabs/FactionsTab';
import { selectPermissions } from '../../../redux/slices/userSlice';
import { hasPermission } from '../../../utils/permissions';

type TabKey = 'general' | 'attributes' | 'inventory' | 'skills' | 'reputation' | 'factions';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'general', label: 'Общее' },
  { key: 'attributes', label: 'Атрибуты' },
  { key: 'inventory', label: 'Инвентарь' },
  { key: 'skills', label: 'Навыки' },
  { key: 'reputation', label: 'Репутация' },
  { key: 'factions', label: 'Фракции' },
];

const AdminCharacterDetailPage = () => {
  const { characterId } = useParams<{ characterId: string }>();
  const dispatch = useAppDispatch();
  const characters = useAppSelector(selectAdminCharacters);
  const selectedCharacter = useAppSelector(selectSelectedCharacter);
  const [activeTab, setActiveTab] = useState<TabKey>('general');
  // FEAT-197: the reputation tab needs reputation:read (moderators and admins).
  const permissions = useAppSelector(selectPermissions);
  const canReadReputation = hasPermission(permissions, 'reputation:read');
  // FEAT-205: the factions tab needs factions:read.
  const canReadFactions = hasPermission(permissions, 'factions:read');
  const visibleTabs = TABS.filter(
    (t) => (t.key !== 'reputation' || canReadReputation) && (t.key !== 'factions' || canReadFactions),
  );
  const charId = Number(characterId);

  const [loadError, setLoadError] = useState<string | null>(null);

  // Load character data
  useEffect(() => {
    setLoadError(null);
    if (!charId) {
      setLoadError('Некорректный номер персонажа');
      return;
    }

    let cancelled = false;

    // Opened from the list: the row is already loaded.
    const found = characters.find((c) => c.id === charId);
    if (found) {
      dispatch(setSelectedCharacter(found));
    } else {
      // Direct link / page reload: load the character by id.
      fetchAdminCharacterById(charId)
        .then((char) => {
          if (cancelled) return;
          if (char) {
            dispatch(setSelectedCharacter(char));
          } else {
            setLoadError('Персонаж не найден');
            toast.error('Персонаж не найден');
          }
        })
        .catch((error: unknown) => {
          if (cancelled) return;
          const message = apiErrorMessage(error, 'Не удалось загрузить персонажа');
          setLoadError(message);
          toast.error(message);
        });
    }

    return () => {
      cancelled = true;
      dispatch(clearDetail());
    };
  }, [charId, dispatch]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!selectedCharacter) {
    return (
      <div className="w-full max-w-container mx-auto">
        <Link
          to="/admin/characters"
          className="text-white/60 text-sm hover:text-site-blue transition-colors duration-200 mb-6 inline-block"
        >
          &larr; Назад к списку
        </Link>
        {loadError ? (
          <p className="text-site-red text-center py-12">{loadError}</p>
        ) : (
          <div className="flex justify-center items-center py-12">
            <div className="w-8 h-8 border-2 border-white/30 border-t-white rounded-full animate-spin" />
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="w-full max-w-container mx-auto">
      {/* Back link */}
      <Link
        to="/admin/characters"
        className="text-white/60 text-sm hover:text-site-blue transition-colors duration-200 mb-6 inline-block"
      >
        &larr; Назад к списку
      </Link>

      {/* Page header */}
      <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em] mb-8">
        {selectedCharacter.name}{' '}
        <span className="text-white/40 text-xl font-normal">#{selectedCharacter.id}</span>
      </h1>

      {/* Tab navigation */}
      <nav className="flex gap-4 sm:gap-6 mb-8 border-b border-white/10 pb-0 overflow-x-auto gold-scrollbar">
        {visibleTabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`nav-link text-base pb-3 relative whitespace-nowrap transition-colors duration-200 ${
              activeTab === tab.key ? 'text-site-blue' : ''
            }`}
          >
            {tab.label}
            {activeTab === tab.key && (
              <motion.div
                layoutId="active-tab-indicator"
                className="absolute bottom-0 left-0 right-0 h-[2px] bg-site-blue"
                transition={{ duration: 0.2, ease: 'easeOut' }}
              />
            )}
          </button>
        ))}
      </nav>

      {/* Tab content */}
      <AnimatePresence mode="wait">
        {activeTab === 'general' && (
          <GeneralTab key="general" character={selectedCharacter} />
        )}
        {activeTab === 'attributes' && (
          <AttributesTab key="attributes" characterId={charId} />
        )}
        {activeTab === 'inventory' && (
          <InventoryTab key="inventory" characterId={charId} />
        )}
        {activeTab === 'skills' && (
          <SkillsTab key="skills" characterId={charId} />
        )}
        {activeTab === 'reputation' && canReadReputation && (
          <ReputationTab key="reputation" characterId={charId} />
        )}
        {activeTab === 'factions' && canReadFactions && (
          <FactionsTab key="factions" characterId={charId} />
        )}
      </AnimatePresence>
    </div>
  );
};

export default AdminCharacterDetailPage;
