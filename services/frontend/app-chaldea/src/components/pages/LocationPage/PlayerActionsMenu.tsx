import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import toast from 'react-hot-toast';
import axios from 'axios';
import { attackPlayer } from '../../../api/pvp';
import { proposeTrade } from '../../../api/trade';
import DuelInviteModal from './DuelInviteModal';
import DeathDuelConfirmModal from './DeathDuelConfirmModal';
import TradeModal from './TradeModal';

const DEATH_DUEL_MIN_LEVEL = 30;

interface PlayerActionsMenuProps {
  targetCharacterId: number;
  targetUserId: number;
  targetName: string;
  targetLevel: number;
  currentCharacterId: number;
  currentCharacterLevel: number;
  locationId: number;
  locationMarkerType: string;
  onActionComplete?: () => void;
}

const PlayerActionsMenu = ({
  targetCharacterId,
  targetUserId,
  targetName,
  targetLevel,
  currentCharacterId,
  currentCharacterLevel,
  locationId,
  locationMarkerType,
  onActionComplete,
}: PlayerActionsMenuProps) => {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [duelModalOpen, setDuelModalOpen] = useState(false);
  const [deathDuelModalOpen, setDeathDuelModalOpen] = useState(false);
  const [attacking, setAttacking] = useState(false);
  const [tradeModalOpen, setTradeModalOpen] = useState(false);
  const [tradeId, setTradeId] = useState<number | null>(null);
  const [proposingTrade, setProposingTrade] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  const isSafe = locationMarkerType === 'safe';
  const canDeathDuel =
    !isSafe &&
    currentCharacterLevel >= DEATH_DUEL_MIN_LEVEL &&
    targetLevel >= DEATH_DUEL_MIN_LEVEL;

  // Close dropdown on outside click
  useEffect(() => {
    if (!open) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [open]);

  const handleTradeClick = async () => {
    setOpen(false);
    setProposingTrade(true);
    try {
      const result = await proposeTrade(currentCharacterId, targetCharacterId);
      setTradeId(result.trade_id);
      setTradeModalOpen(true);
    } catch (err) {
      const message =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? err.response.data.detail
          : 'Не удалось предложить обмен';
      toast.error(message);
    } finally {
      setProposingTrade(false);
    }
  };

  const handleTradeClose = () => {
    setTradeModalOpen(false);
    setTradeId(null);
    onActionComplete?.();
  };

  const handleAttack = async () => {
    setAttacking(true);
    try {
      const result = await attackPlayer(currentCharacterId, targetCharacterId);
      toast.success(`Бой с ${targetName} начинается!`);
      setOpen(false);
      onActionComplete?.();
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

  const handleDuelClick = () => {
    setOpen(false);
    setDuelModalOpen(true);
  };

  const handleDuelComplete = () => {
    setDuelModalOpen(false);
    onActionComplete?.();
  };

  const handleDeathDuelClick = () => {
    setOpen(false);
    setDeathDuelModalOpen(true);
  };

  const handleDeathDuelComplete = () => {
    setDeathDuelModalOpen(false);
    onActionComplete?.();
  };

  return (
    <div className="relative" ref={menuRef}>
      <button
        onClick={() => setOpen((prev) => !prev)}
        className="btn-line text-[10px] sm:text-xs px-2 py-0.5 sm:px-3 sm:py-1"
      >
        Действие
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -5 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -5 }}
            transition={{ duration: 0.15 }}
            className="dropdown-menu absolute bottom-full left-1/2 -translate-x-1/2 mb-2 w-48 sm:w-52 z-30"
          >
            {/* Trade */}
            <button
              onClick={handleTradeClick}
              disabled={proposingTrade}
              className="dropdown-item w-full text-left"
            >
              <span className="flex items-center gap-2">
                {proposingTrade ? (
                  <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin shrink-0" />
                ) : (
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
                  </svg>
                )}
                {proposingTrade ? 'Предложение...' : 'Предложить обмен'}
              </span>
            </button>

            {/* Training Duel */}
            <button
              onClick={handleDuelClick}
              className="dropdown-item w-full text-left"
            >
              <span className="flex items-center gap-2">
                <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                </svg>
                Вызвать на тренировочный бой
              </span>
            </button>

            {/* Death Duel — visible when both players 30+ and location not safe */}
            {canDeathDuel && (
              <button
                onClick={handleDeathDuelClick}
                className="dropdown-item w-full text-left text-site-red hover:text-site-red"
              >
                <span className="flex items-center gap-2">
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  Вызвать на смертельный бой
                </span>
              </button>
            )}

            {/* Attack — only on non-safe locations */}
            {!isSafe && (
              <button
                onClick={handleAttack}
                disabled={attacking}
                className="dropdown-item w-full text-left text-site-red hover:text-site-red"
              >
                <span className="flex items-center gap-2">
                  {attacking ? (
                    <div className="w-3.5 h-3.5 border-2 border-site-red/30 border-t-site-red rounded-full animate-spin shrink-0" />
                  ) : (
                    <svg xmlns="http://www.w3.org/2000/svg" className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                  )}
                  {attacking ? 'Атака...' : 'Напасть'}
                </span>
              </button>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {/* Duel Invite Modal */}
      {duelModalOpen && (
        <DuelInviteModal
          targetName={targetName}
          targetLevel={targetLevel}
          battleType="pvp_training"
          initiatorCharacterId={currentCharacterId}
          targetCharacterId={targetCharacterId}
          onComplete={handleDuelComplete}
          onCancel={() => setDuelModalOpen(false)}
        />
      )}

      {/* Death Duel Confirm Modal */}
      {deathDuelModalOpen && (
        <DeathDuelConfirmModal
          targetName={targetName}
          targetLevel={targetLevel}
          targetCharacterId={targetCharacterId}
          currentCharacterId={currentCharacterId}
          onClose={() => setDeathDuelModalOpen(false)}
          onSuccess={handleDeathDuelComplete}
        />
      )}

      {/* Trade Modal */}
      {tradeModalOpen && tradeId !== null && (
        <TradeModal
          tradeId={tradeId}
          currentCharacterId={currentCharacterId}
          targetCharacterName={targetName}
          onClose={handleTradeClose}
        />
      )}
    </div>
  );
};

export default PlayerActionsMenu;
