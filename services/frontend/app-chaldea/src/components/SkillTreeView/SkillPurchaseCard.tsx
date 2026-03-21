import { useState } from 'react';
import toast from 'react-hot-toast';
import { useAppDispatch } from '../../redux/store';
import { purchaseSkill } from '../../redux/actions/playerTreeActions';
import type {
  TreeNodeSkillRead,
  PurchasedSkillProgress,
} from './types';
import SkillUpgradeModal from './SkillUpgradeModal';

interface SkillPurchaseCardProps {
  skill: TreeNodeSkillRead;
  nodeId: number;
  characterId: number;
  activeExperience: number;
  purchasedSkills: PurchasedSkillProgress[];
  onRefresh: () => void;
}

const SkillPurchaseCard = ({
  skill,
  nodeId,
  characterId,
  activeExperience,
  purchasedSkills,
  onRefresh,
}: SkillPurchaseCardProps) => {
  const dispatch = useAppDispatch();
  const [buying, setBuying] = useState(false);
  const [upgradeOpen, setUpgradeOpen] = useState(false);

  const purchased = purchasedSkills.find((ps) => ps.skill_id === skill.skill_id);
  const isPurchased = !!purchased;

  // We don't have purchase_cost on TreeNodeSkillRead, it's on the skill itself.
  // The backend handles the cost check. We show the cost from skill data if available.
  // For now we rely on the backend to reject if not enough XP.

  const handlePurchase = async () => {
    setBuying(true);
    try {
      await dispatch(
        purchaseSkill({
          characterId,
          nodeId,
          skillId: skill.skill_id,
        })
      ).unwrap();
      toast.success('Навык изучен!');
      onRefresh();
    } catch (err) {
      const message = typeof err === 'string' ? err : 'Ошибка покупки навыка';
      toast.error(message);
    } finally {
      setBuying(false);
    }
  };

  const skillTypeLabels: Record<string, string> = {
    attack: 'Атака',
    defense: 'Защита',
    support: 'Поддержка',
  };

  return (
    <>
      <div className="flex items-center gap-3 p-3 rounded-card bg-white/[0.04] hover:bg-white/[0.07] transition-colors duration-200 ease-site">
        {/* Skill image */}
        <div className="w-10 h-10 rounded-full bg-white/10 flex-shrink-0 flex items-center justify-center overflow-hidden">
          {skill.skill_image ? (
            <img
              src={skill.skill_image}
              alt={skill.skill_name ?? ''}
              className="w-full h-full object-cover"
            />
          ) : (
            <span className="text-white/30 text-lg">&#9733;</span>
          )}
        </div>

        {/* Skill info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-white text-sm font-medium truncate">
              {skill.skill_name ?? `Навык #${skill.skill_id}`}
            </span>
            {skill.skill_type && (
              <span className="text-[10px] text-white/50 uppercase bg-white/10 px-1.5 py-0.5 rounded-full flex-shrink-0">
                {skillTypeLabels[skill.skill_type] ?? skill.skill_type}
              </span>
            )}
          </div>

          {/* Action area */}
          <div className="mt-1.5">
            {isPurchased ? (
              <div className="flex items-center gap-2">
                <span className="text-green-400 text-xs font-medium">
                  Изучено &#10003;
                </span>
                <button
                  onClick={() => setUpgradeOpen(true)}
                  className="text-xs text-site-blue hover:text-gold transition-colors duration-200 ease-site"
                >
                  Улучшить
                </button>
              </div>
            ) : (
              <button
                onClick={handlePurchase}
                disabled={buying}
                className="text-xs font-medium px-3 py-1 rounded-card-lg bg-gradient-to-r from-[#2e353e] to-[#537895] text-white hover:shadow-hover active:shadow-pressed transition-shadow duration-200 ease-site disabled:opacity-40 disabled:cursor-not-allowed"
              >
                {buying ? 'Изучение...' : 'Изучить'}
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Upgrade modal */}
      {upgradeOpen && purchased && (
        <SkillUpgradeModal
          skillId={skill.skill_id}
          characterId={characterId}
          currentRankId={purchased.skill_rank_id}
          onClose={() => setUpgradeOpen(false)}
          onRefresh={onRefresh}
        />
      )}
    </>
  );
};

export default SkillPurchaseCard;
