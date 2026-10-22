import { useState } from 'react';
import toast from 'react-hot-toast';
import axios from 'axios';
import { submitJoinRequest } from '../../../api/battles';
import type { LocationBattleParticipant } from '../../../api/battles';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';

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
    <ModalShell
      open
      onClose={onClose}
      title="Подать заявку"
      size="sm"
      dismissible={!loading}
      footer={
        <>
          <button
            onClick={onClose}
            disabled={loading}
            className="btn-line w-full sm:w-auto text-xs sm:text-sm px-4 py-1.5"
          >
            Отмена
          </button>
          <button
            onClick={handleSubmit}
            disabled={selectedTeam === null || loading}
            className="btn-blue w-full sm:w-auto text-xs sm:text-sm px-4 py-1.5 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Отправка...' : 'Отправить заявку'}
          </button>
        </>
      }
    >
      <p className="text-white/70 text-sm mb-4">
        Выберите команду, к которой хотите присоединиться:
      </p>

      {/* Team selection */}
      <div className="flex flex-col sm:flex-row gap-3">
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
    </ModalShell>
  );
};

export default JoinRequestModal;
