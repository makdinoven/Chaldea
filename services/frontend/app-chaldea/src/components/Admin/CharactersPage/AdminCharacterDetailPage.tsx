import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  fetchAdminCharacters,
  selectAdminCharacters,
  selectSelectedCharacter,
  setSelectedCharacter,
  clearDetail,
} from '../../../redux/slices/adminCharactersSlice';
import GeneralTab from './tabs/GeneralTab';
import AttributesTab from './tabs/AttributesTab';
import InventoryTab from './tabs/InventoryTab';
import SkillsTab from './tabs/SkillsTab';

type TabKey = 'general' | 'attributes' | 'inventory' | 'skills';

const TABS: { key: TabKey; label: string }[] = [
  { key: 'general', label: 'Общее' },
  { key: 'attributes', label: 'Атрибуты' },
  { key: 'inventory', label: 'Инвентарь' },
  { key: 'skills', label: 'Навыки' },
];

const AdminCharacterDetailPage = () => {
  const { characterId } = useParams<{ characterId: string }>();
  const dispatch = useAppDispatch();
  const characters = useAppSelector(selectAdminCharacters);
  const selectedCharacter = useAppSelector(selectSelectedCharacter);
  const [activeTab, setActiveTab] = useState<TabKey>('general');
  const charId = Number(characterId);

  // Load character data
  useEffect(() => {
    if (!charId) return;

    // Try to find in already loaded list
    const found = characters.find((c) => c.id === charId);
    if (found) {
      dispatch(setSelectedCharacter(found));
    } else {
      // Fetch the list to get the character
      dispatch(fetchAdminCharacters()).then((result) => {
        if (fetchAdminCharacters.fulfilled.match(result)) {
          const char = result.payload.items.find((c) => c.id === charId);
          if (char) {
            dispatch(setSelectedCharacter(char));
          } else {
            toast.error('Персонаж не найден');
          }
        }
      });
    }

    return () => {
      dispatch(clearDetail());
    };
  }, [charId, dispatch]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!selectedCharacter) {
    return (
      <div className="w-full max-w-[1240px] mx-auto">
        <Link
          to="/admin/characters"
          className="text-white/60 text-sm hover:text-site-blue transition-colors duration-200 mb-6 inline-block"
        >
          &larr; Назад к списку
        </Link>
        <div className="flex justify-center items-center py-12">
          <div className="w-8 h-8 border-2 border-white/30 border-t-white rounded-full animate-spin" />
        </div>
      </div>
    );
  }

  return (
    <div className="w-full max-w-[1240px] mx-auto">
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
      <nav className="flex gap-6 mb-8 border-b border-white/10 pb-0">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`nav-link text-base pb-3 relative transition-colors duration-200 ${
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
      </AnimatePresence>
    </div>
  );
};

export default AdminCharacterDetailPage;
