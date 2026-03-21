import { useAppSelector } from '../../redux/store';
import SkillsTab from '../ProfilePage/SkillsTab/SkillsTab';

const SkillTreePage = () => {
  const character = useAppSelector((state) => state.user.character);
  const status = useAppSelector((state) => state.user.status);
  const authInitialized = useAppSelector((state) => state.user.authInitialized);
  const characterId = character?.id ?? null;

  // Still loading auth
  if (!authInitialized || status === 'loading') {
    return (
      <div className="flex items-center justify-center py-32">
        <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  // No character
  if (!characterId) {
    return (
      <div className="flex flex-col items-center justify-center py-32">
        <h2 className="gold-text text-3xl font-medium uppercase mb-4">Навыки</h2>
        <p className="text-white/50 text-lg">
          Создайте персонажа, чтобы открыть дерево навыков.
        </p>
      </div>
    );
  }

  return (
    <div className="w-full px-2 md:px-6 py-4">
      <SkillsTab characterId={characterId} />
    </div>
  );
};

export default SkillTreePage;
