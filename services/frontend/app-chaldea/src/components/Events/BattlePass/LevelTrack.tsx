import { useState } from 'react';
import type { BPLevel, BPUserProgress } from '../../../types/battlePass';
import RewardCell from './RewardCell';

interface LevelTrackProps {
  levels: BPLevel[];
  progress: BPUserProgress | null;
  onClaim: (levelNumber: number, track: 'free' | 'premium') => void;
  onActivatePremium: () => void;
}

const LevelTrack = ({ levels, progress, onClaim, onActivatePremium }: LevelTrackProps) => {
  const [claimingKey, setClaimingKey] = useState<string | null>(null);

  const currentLevel = progress?.current_level ?? 0;
  const isPremium = progress?.is_premium ?? false;
  const claimedSet = new Set(
    (progress?.claimed_rewards ?? []).map((r) => `${r.level_number}-${r.track}`),
  );

  const handleClaim = async (levelNumber: number, track: 'free' | 'premium') => {
    const key = `${levelNumber}-${track}`;
    setClaimingKey(key);
    try {
      await onClaim(levelNumber, track);
    } finally {
      setClaimingKey(null);
    }
  };

  const sortedLevels = [...levels].sort((a, b) => a.level_number - b.level_number);

  return (
    <div className="relative">
      {/* Premium overlay */}
      {!isPremium && (
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs text-white/40 uppercase tracking-wider">Премиум дорожка заблокирована</span>
          <button
            onClick={onActivatePremium}
            className="btn-blue text-xs px-3 py-1"
          >
            Купить Премиум
          </button>
        </div>
      )}

      <div className="gold-scrollbar overflow-x-auto pb-2">
        <div className="inline-flex gap-2 min-w-max">
          {sortedLevels.map((level) => {
            const isReached = currentLevel >= level.level_number;

            return (
              <div
                key={level.level_number}
                className="flex flex-col items-center gap-1"
              >
                {/* Level number badge */}
                <span
                  className={`
                    text-xs font-medium px-2 py-0.5 rounded-full
                    ${isReached ? 'bg-gold/20 text-gold' : 'bg-white/10 text-white/40'}
                  `}
                >
                  {level.level_number}
                </span>

                {/* Free row */}
                <div>
                  {level.free_rewards.length > 0 ? (
                    level.free_rewards.map((reward) => (
                      <RewardCell
                        key={reward.id}
                        reward={reward}
                        track="free"
                        levelNumber={level.level_number}
                        isReached={isReached}
                        isClaimed={claimedSet.has(`${level.level_number}-free`)}
                        isPremiumLocked={false}
                        onClaim={handleClaim}
                        claiming={claimingKey === `${level.level_number}-free`}
                      />
                    ))
                  ) : (
                    <div className="min-w-[72px] sm:min-w-[80px] h-[90px] rounded-card border border-white/5 bg-white/[0.03]" />
                  )}
                </div>

                {/* Premium row */}
                <div>
                  {level.premium_rewards.length > 0 ? (
                    level.premium_rewards.map((reward) => (
                      <RewardCell
                        key={reward.id}
                        reward={reward}
                        track="premium"
                        levelNumber={level.level_number}
                        isReached={isReached}
                        isClaimed={claimedSet.has(`${level.level_number}-premium`)}
                        isPremiumLocked={!isPremium}
                        onClaim={handleClaim}
                        claiming={claimingKey === `${level.level_number}-premium`}
                      />
                    ))
                  ) : (
                    <div className={`min-w-[72px] sm:min-w-[80px] h-[90px] rounded-card border border-white/5 bg-white/[0.03] ${!isPremium ? 'opacity-40' : ''}`} />
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Row labels */}
      <div className="flex justify-between mt-1 text-[10px] text-white/30 uppercase tracking-wider px-1">
        <span>Бесплатно</span>
        <span>Премиум</span>
      </div>
    </div>
  );
};

export default LevelTrack;
