import { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import { UserX } from 'lucide-react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  loadProfileData,
  selectProfileLoading,
  selectProfileError,
} from '../../redux/slices/profileSlice';
import ProfileTabs from './ProfileTabs';
import CharacterTab from './CharacterTab/CharacterTab';
import SkillsTab from './SkillsTab/SkillsTab';
import PerksTab from './PerksTab/PerksTab';
import PartyTab from './PartyTab/PartyTab';
import GatheringTab from './GatheringTab/GatheringTab';
import QuestsTab from './QuestsTab/QuestsTab';
import BattlesTab from './BattlesTab/BattlesTab';
import LogsTab from './LogsTab/LogsTab';
import PostHistoryTab from './PostHistoryTab/PostHistoryTab';
import TitlesTab from './TitlesTab/TitlesTab';
import CraftTab from './CraftTab/CraftTab';
import ErrorBoundary from '../ui/ErrorBoundary';
import EmptyState from './shared/EmptyState';
import LoadingState from './shared/LoadingState';

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
      <EmptyState
        icon={<UserX size={32} strokeWidth={1.5} className="text-white/20" />}
        message="Персонаж не найден. Создайте персонажа, чтобы просматривать профиль."
        className="py-32 px-4"
      />
    );
  }

  if (loading) {
    return (
      <LoadingState className="py-32" />
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
      case 'party':
        return <PartyTab characterId={characterId} />;
      case 'gathering':
        return (
          <ErrorBoundary>
            <GatheringTab characterId={characterId} />
          </ErrorBoundary>
        );
      case 'quests':
        return <QuestsTab characterId={characterId} />;
      case 'battles':
        return <BattlesTab characterId={characterId} />;
      case 'logs':
        return <LogsTab characterId={characterId} />;
      case 'posts':
        return <PostHistoryTab characterId={characterId} />;
      case 'titles':
        return <TitlesTab characterId={characterId} />;
      case 'craft':
        return (
          <ErrorBoundary>
            <CraftTab characterId={characterId} />
          </ErrorBoundary>
        );
      default:
        return null;
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="-mt-12"
    >
      <ProfileTabs activeTab={activeTab} onTabChange={setActiveTab} />
      {renderTabContent()}
    </motion.div>
  );
};

export default ProfilePage;
