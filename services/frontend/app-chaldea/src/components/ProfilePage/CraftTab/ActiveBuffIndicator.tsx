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

const BUFF_TYPE_LABELS: Record<string, string> = {
  xp_bonus: 'XP',
};

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
  const label = BUFF_TYPE_LABELS[buff.buff_type] || buff.buff_type;

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.9 }}
      transition={{ duration: 0.2 }}
      className="flex items-center gap-2 px-3 py-1.5 rounded-card bg-site-bg gold-outline relative"
    >
      <span className="text-xs font-medium text-gold">
        +{bonusPct}% {label}
      </span>
      <span className="text-xs text-white/70">
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
    <div className="flex flex-wrap gap-2">
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
