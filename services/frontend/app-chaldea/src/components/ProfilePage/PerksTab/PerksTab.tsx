import { useEffect, useState } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import axios from 'axios';
import type { CharacterPerk, PerksResponse } from '../../../types/perks';
import PerkTree from './PerkTree';
import PerkDetailModal from './PerkDetailModal';

interface PerksTabProps {
  characterId: number;
}

const PerksTab = ({ characterId }: PerksTabProps) => {
  const [perks, setPerks] = useState<CharacterPerk[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedPerk, setSelectedPerk] = useState<CharacterPerk | null>(null);

  useEffect(() => {
    const fetchPerks = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await axios.get<PerksResponse>(`/attributes/${characterId}/perks`);
        setPerks(res.data.perks);
      } catch {
        const msg = 'Не удалось загрузить перки';
        setError(msg);
        toast.error(msg);
      } finally {
        setLoading(false);
      }
    };
    fetchPerks();
  }, [characterId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (error && perks.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <p className="text-white/50 text-lg">{error}</p>
      </div>
    );
  }

  const unlockedCount = perks.filter((p) => p.is_unlocked).length;

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="space-y-4"
    >
      {/* Header */}
      <div className="flex items-center justify-between">
        <h3 className="gold-text text-xl font-medium uppercase">
          Перки ({unlockedCount}/{perks.length})
        </h3>
      </div>

      {/* Perk tree */}
      <PerkTree perks={perks} onSelectPerk={setSelectedPerk} />

      {/* Detail modal */}
      {selectedPerk && (
        <PerkDetailModal
          perk={selectedPerk}
          onClose={() => setSelectedPerk(null)}
        />
      )}
    </motion.div>
  );
};

export default PerksTab;
