import { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  loadProfileData,
  selectProfileLoading,
  selectProfileError,
} from '../../redux/slices/profileSlice';
import ProfileTabs from './ProfileTabs';
import PlaceholderTab from './PlaceholderTab';
import CharacterTab from './CharacterTab/CharacterTab';
import SkillsTab from './SkillsTab/SkillsTab';
import PerksTab from './PerksTab/PerksTab';
import QuestLogTab from './QuestLogTab';
import BattlesTab from './BattlesTab/BattlesTab';
import LogsTab from './LogsTab/LogsTab';
import TitlesTab from './TitlesTab/TitlesTab';
import CraftTab from './CraftTab/CraftTab';
import ErrorBoundary from '../ui/ErrorBoundary';

const ProfilePage = () => {
  const dispatch = useAppDispatch();
  const character = useAppSelector((state) => state.user.character);
  const loading = useAppSelector(selectProfileLoading);
  const error = useAppSelector(selectProfileError);
  const [activeTab, setActiveTab] = useState('character');

  const characterId = character?.id ?? null;

  useEffect(() => {
    if (characterId) {
      dispatch(loadProfileData(characterId));
    }
  }, [dispatch, characterId]);

  useEffect(() => {
    if (error) {
      toast.error(error);
    }
  }, [error]);

  if (!characterId) {
    return (
      <div className="flex items-center justify-center py-32">
        <p className="text-white/50 text-lg">
          Персонаж не найден. Создайте персонажа, чтобы просматривать профиль.
        </p>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  const renderTabContent = () => {
    switch (activeTab) {
      case 'character':
        return <CharacterTab characterId={characterId} />;
      case 'skills':
        return <SkillsTab characterId={characterId} />;
      case 'perks':
        return <PerksTab characterId={characterId} />;
      case 'quests':
        return <QuestLogTab characterId={characterId} />;
      case 'battles':
        return <BattlesTab characterId={characterId} />;
      case 'logs':
        return <LogsTab characterId={characterId} />;
      case 'titles':
        return <TitlesTab characterId={characterId} />;
      case 'craft':
        return (
          <ErrorBoundary>
            <CraftTab characterId={characterId} />
          </ErrorBoundary>
        );
      default:
        return <PlaceholderTab tabName={activeTab} />;
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="-mt-12"
    >
      <ProfileTabs activeTab={activeTab} onTabChange={setActiveTab} characterId={characterId} />
      {renderTabContent()}
    </motion.div>
  );
};

export default ProfilePage;
