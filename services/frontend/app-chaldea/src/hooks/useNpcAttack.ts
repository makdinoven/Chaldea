import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import axios from 'axios';
import { createBattle } from '../api/mobs';

interface UseNpcAttackOptions {
  npcId: number;
  npcName: string;
  currentCharacterId: number | null;
}

interface UseNpcAttackReturn {
  attacking: boolean;
  handleAttack: () => Promise<void>;
}

const useNpcAttack = ({ npcId, npcName, currentCharacterId }: UseNpcAttackOptions): UseNpcAttackReturn => {
  const navigate = useNavigate();
  const { locationId } = useParams<{ locationId: string }>();
  const [attacking, setAttacking] = useState(false);

  const handleAttack = async () => {
    if (!currentCharacterId) {
      toast.error('У вас нет персонажа для начала боя');
      return;
    }

    setAttacking(true);
    try {
      // Check if NPC is already in battle
      const inBattleRes = await axios.get<{ in_battle: boolean }>(
        `/battles/character/${npcId}/in-battle`,
      );
      if (inBattleRes.data.in_battle) {
        toast.error('НПС уже в бою');
        setAttacking(false);
        return;
      }

      // Create battle
      const result = await createBattle(currentCharacterId, npcId);
      toast.success(`Бой с ${npcName} начинается!`);
      navigate(`/location/${locationId}/battle/${result.battle_id}`);
    } catch (err) {
      const message =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? err.response.data.detail
          : 'Не удалось начать бой';
      toast.error(message);
    } finally {
      setAttacking(false);
    }
  };

  return { attacking, handleAttack };
};

export default useNpcAttack;
