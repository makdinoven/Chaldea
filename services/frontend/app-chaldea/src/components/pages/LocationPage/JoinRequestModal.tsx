import { useState } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import axios from 'axios';
import { submitJoinRequest } from '../../../api/battles';
import type { LocationBattleParticipant } from '../../../api/battles';

interface JoinRequestModalProps {
  battleId: number;
  participants: LocationBattleParticipant[];
  characterId: number;
  onClose: () => void;
  onSuccess: () => void;
}

const JoinRequestModal = ({
  battleId,
  participants,
  characterId,
  onClose,
  onSuccess,
}: JoinRequestModalProps) => {
  const [selectedTeam, setSelectedTeam] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);

  const team0 = participants.filter((p) => p.team === 0);
  const team1 = participants.filter((p) => p.team === 1);

  const handleSubmit = async () => {
    if (selectedTeam === null) return;
    setLoading(true);
    try {
      await submitJoinRequest(battleId, characterId, selectedTeam);
      toast.success('Заявка отправлена');
      onSuccess();
      onClose();
    } catch (err) {
      const message =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? err.response.data.detail
          : 'Не удалось отправить заявку. Попробуйте позже.';
      toast.error(message);
    } finally {
      setLoading(false);
    }
  };

  const renderTeamMembers = (members: LocationBattleParticipant[]) => {
    if (members.length === 0) {
      return <span className="text-white/30 text-xs italic">Нет участников</span>;
    }
    return (
      <div className="flex flex-wrap gap-1.5 mt-1.5">
        {members.map((p) => (
          <span
            key={p.participant_id}
            className={`px-2 py-0.5 rounded-full text-[10px] sm:text-xs font-medium ${
              p.is_npc
                ? 'bg-purple-600/30 text-purple-200'
                : 'bg-white/10 text-white/80'
            }`}
          >
            {p.character_name}
            <span className="text-white/40 ml-1">Ур.{p.level}</span>
          </span>
        ))}
      </div>
    );
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.95 }}
        transition={{ duration: 0.2, ease: 'easeOut' }}
        className="modal-content gold-outline gold-outline-thick max-w-md w-full mx-4"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="gold-text text-lg sm:text-xl font-medium uppercase mb-4">
          Подать заявку
        </h3>

        <p className="text-white/70 text-sm mb-4">
          Выберите команду, к которой хотите присоединиться:
        </p>

        {/* Team selection */}
        <div className="flex flex-col sm:flex-row gap-3 mb-6">
          {/* Team 1 (index 0) */}
          <button
            type="button"
            onClick={() => setSelectedTeam(0)}
            disabled={loading}
            className={`flex-1 flex flex-col gap-2 p-3 sm:p-4 rounded-card border-2 transition-all duration-200 cursor-pointer ${
              selectedTeam === 0
                ? 'border-gold bg-gold/10'
                : 'border-white/10 bg-white/5 hover:border-white/30 hover:bg-white/10'
            } disabled:cursor-not-allowed disabled:opacity-50`}
          >
            <span
              className={`text-sm font-medium uppercase tracking-wider ${
                selectedTeam === 0 ? 'text-gold' : 'text-white/60'
              }`}
            >
              Команда 1
            </span>
            {renderTeamMembers(team0)}
          </button>

          {/* Team 2 (index 1) */}
          <button
            type="button"
            onClick={() => setSelectedTeam(1)}
            disabled={loading}
            className={`flex-1 flex flex-col gap-2 p-3 sm:p-4 rounded-card border-2 transition-all duration-200 cursor-pointer ${
              selectedTeam === 1
                ? 'border-gold bg-gold/10'
                : 'border-white/10 bg-white/5 hover:border-white/30 hover:bg-white/10'
            } disabled:cursor-not-allowed disabled:opacity-50`}
          >
            <span
              className={`text-sm font-medium uppercase tracking-wider ${
                selectedTeam === 1 ? 'text-gold' : 'text-white/60'
              }`}
            >
              Команда 2
            </span>
            {renderTeamMembers(team1)}
          </button>
        </div>

        {/* Buttons */}
        <div className="flex justify-end gap-3">
          <button
            onClick={onClose}
            disabled={loading}
            className="btn-line text-xs sm:text-sm px-4 py-1.5"
          >
            Отмена
          </button>
          <button
            onClick={handleSubmit}
            disabled={selectedTeam === null || loading}
            className="btn-blue text-xs sm:text-sm px-4 py-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Отправка...' : 'Отправить заявку'}
          </button>
        </div>
      </motion.div>
    </div>
  );
};

export default JoinRequestModal;
