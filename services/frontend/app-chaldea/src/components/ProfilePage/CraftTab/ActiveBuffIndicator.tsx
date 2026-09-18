import { useEffect, useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  selectActiveBuffs,
  fetchActiveBuffs,
  type ActiveBuff,
} from '../../../redux/slices/profileSlice';

interface ActiveBuffIndicatorProps {
  characterId: number;
}

import { xpBuffLabel } from '../../../utils/itemEffects';

const formatTime = (totalSeconds: number): string => {
  if (totalSeconds <= 0) return '0:00';
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${seconds.toString().padStart(2, '0')}`;
};

const BuffItem = ({ buff, characterId }: { buff: ActiveBuff; characterId: number }) => {
  const dispatch = useAppDispatch();
  const [remaining, setRemaining] = useState(buff.remaining_seconds);

  useEffect(() => {
    setRemaining(buff.remaining_seconds);
  }, [buff.remaining_seconds]);

  useEffect(() => {
    if (remaining <= 0) return;

    const interval = setInterval(() => {
      setRemaining((prev) => {
        if (prev <= 1) {
          clearInterval(interval);
          // Refresh buffs when expired
          dispatch(fetchActiveBuffs(characterId));
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [remaining > 0, dispatch, characterId]);

  if (remaining <= 0) return null;

  const bonusPct = Math.round(buff.value * 100);
  // All 8 XP sources are labelled in the shared map (FEAT-168 §3.9-bis A).
  const label = xpBuffLabel(buff.buff_type);

  // The labels grew long with the 8 XP sources (§3.9-bis), so the pill wraps
  // instead of pushing the row past a 360px viewport: the countdown stays
  // pinned to the right and the label takes whatever space is left.
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      transition={{ duration: 0.2 }}
      className="flex items-center gap-2 min-w-0 max-w-full px-2.5 py-1 rounded-card sm:rounded-full border border-gold/30 bg-gold/[0.06]"
      title={`+${bonusPct}% ${label}`}
    >
      <span className="text-[11px] sm:text-xs font-medium text-gold min-w-0 break-words">
        +{bonusPct}% {label}
      </span>
      <span className="text-[11px] sm:text-xs text-white/70 shrink-0 tabular-nums">
        {formatTime(remaining)}
      </span>
    </motion.div>
  );
};

const ActiveBuffIndicator = ({ characterId }: ActiveBuffIndicatorProps) => {
  const activeBuffs = useAppSelector(selectActiveBuffs);

  const refreshBuffs = useCallback(() => {
    // Buffs are loaded as part of loadProfileData
  }, []);

  useEffect(() => {
    refreshBuffs();
  }, [refreshBuffs]);

  if (!activeBuffs || activeBuffs.length === 0) return null;

  return (
    <div className="flex flex-wrap items-center gap-2 min-w-0">
      <AnimatePresence>
        {activeBuffs.map((buff) => (
          <BuffItem
            key={buff.id}
            buff={buff}
            characterId={characterId}
          />
        ))}
      </AnimatePresence>
    </div>
  );
};

export default ActiveBuffIndicator;
