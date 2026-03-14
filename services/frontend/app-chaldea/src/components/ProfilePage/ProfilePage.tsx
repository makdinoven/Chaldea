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
import InventoryTab from './InventoryTab/InventoryTab';

const ProfilePage = () => {
  const dispatch = useAppDispatch();
  const character = useAppSelector((state) => state.user.character);
  const loading = useAppSelector(selectProfileLoading);
  const error = useAppSelector(selectProfileError);
  const [activeTab, setActiveTab] = useState('inventory');

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
      case 'inventory':
        return <InventoryTab characterId={characterId} />;
      case 'stats':
        return <PlaceholderTab tabName="Статы" />;
      case 'skills':
        return <PlaceholderTab tabName="Навыки" />;
      case 'logs':
        return <PlaceholderTab tabName="Логи персонажа" />;
      case 'titles':
        return <PlaceholderTab tabName="Титулы" />;
      case 'craft':
        return <PlaceholderTab tabName="Крафт" />;
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
      <ProfileTabs activeTab={activeTab} onTabChange={setActiveTab} />
      {renderTabContent()}
    </motion.div>
  );
};

export default ProfilePage;
