import type { BPReward } from '../../../types/battlePass';

interface RewardCellProps {
  reward: BPReward;
  track: 'free' | 'premium';
  levelNumber: number;
  isReached: boolean;
  isClaimed: boolean;
  isPremiumLocked: boolean;
  onClaim: (levelNumber: number, track: 'free' | 'premium') => void;
  claiming: boolean;
}

const REWARD_ICONS: Record<string, string> = {
  gold: '\u{1F4B0}',
  xp: '\u{2B50}',
  diamonds: '\u{1F48E}',
  item: '\u{1F4E6}',
  frame: '\u{1F5BC}',
  chat_background: '\u{1F4AC}',
};

const REWARD_LABELS: Record<string, string> = {
  gold: 'Золото',
  xp: 'Опыт',
  diamonds: 'Алмазы',
  item: 'Предмет',
  frame: 'Рамка',
  chat_background: 'Подложка',
};

const RewardCell = ({
  reward,
  track,
  levelNumber,
  isReached,
  isClaimed,
  isPremiumLocked,
  onClaim,
  claiming,
}: RewardCellProps) => {
  const canClaim = isReached && !isClaimed && !isPremiumLocked;

  return (
    <div
      className={`
        relative flex flex-col items-center justify-center gap-1
        min-w-[72px] sm:min-w-[80px] p-2 rounded-card
        border border-white/10 transition-all duration-200 ease-site
        ${isClaimed ? 'bg-white/5 opacity-60' : 'bg-white/[0.07]'}
        ${canClaim ? 'ring-1 ring-gold/50' : ''}
        ${isPremiumLocked ? 'opacity-40' : ''}
      `}
    >
      <span className="text-2xl" aria-label={REWARD_LABELS[reward.reward_type] || reward.reward_type}>
        {REWARD_ICONS[reward.reward_type] || '\u{1F381}'}
      </span>

      <span className="text-xs text-white font-medium text-center leading-tight">
        {reward.item_name
          || reward.cosmetic_slug
          || `${reward.reward_value} ${REWARD_LABELS[reward.reward_type] || ''}`}
      </span>

      {isClaimed && (
        <span className="text-[10px] text-gold uppercase tracking-wider font-medium">
          Получено
        </span>
      )}

      {canClaim && (
        <button
          onClick={() => onClaim(levelNumber, track)}
          disabled={claiming}
          className="btn-blue text-[10px] sm:text-xs px-2 py-0.5 mt-0.5 whitespace-nowrap"
        >
          {claiming ? '...' : 'Забрать'}
        </button>
      )}

      {!isReached && !isClaimed && !isPremiumLocked && (
        <span className="text-[10px] text-white/40 uppercase tracking-wider">
          Ур. {levelNumber}
        </span>
      )}
    </div>
  );
};

export default RewardCell;
