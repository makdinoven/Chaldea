// ProfilePage PerksTab. FEAT-166: the tree sits in a PanelShell (auto height,
// no inner scroll). The wheel layout is derived from the backdrop's five 72°
// sectors in PerkTree.tsx — keep node placement and the art aligned together.
import { useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import axios from 'axios';
import { Star } from 'lucide-react';
import type { CharacterPerk, PerksResponse } from '../../../types/perks';
import PanelShell from '../PanelShell';
import PanelCounter from '../shared/PanelCounter';
import LoadingState from '../shared/LoadingState';
import ErrorState from '../shared/ErrorState';
import PerkTree from './PerkTree';
import PerkDetailModal from './PerkDetailModal';

const PANEL_TITLE = 'Перки';
const PANEL_ICON = <Star size={18} strokeWidth={1.8} className="text-gold shrink-0" />;
// Mobile: the tree's own list variant already has p-4, so the panel adds none
// there (keeps the list width unchanged); md+ tree gets the standard padding.
const PANEL_BODY_CLASS = 'p-0 md:p-4 lg:p-5';

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

  const unlockedCount = perks.filter((p) => p.is_unlocked).length;
  const fatalError = !loading && error !== null && perks.length === 0;

  let content: ReactNode;
  if (loading) {
    content = <LoadingState />;
  } else if (fatalError) {
    content = <ErrorState message={error ?? ''} />;
  } else {
    content = <PerkTree perks={perks} onSelectPerk={setSelectedPerk} />;
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
    >
      <PanelShell
        title={PANEL_TITLE}
        icon={PANEL_ICON}
        headerExtra={
          loading || fatalError ? undefined : (
            <PanelCounter>
              {unlockedCount}/{perks.length}
            </PanelCounter>
          )
        }
        bodyClassName={PANEL_BODY_CLASS}
      >
        {content}
      </PanelShell>

      {/* Detail dialog (portaled) */}
      <PerkDetailModal perk={selectedPerk} onClose={() => setSelectedPerk(null)} />
    </motion.div>
  );
};

export default PerksTab;
