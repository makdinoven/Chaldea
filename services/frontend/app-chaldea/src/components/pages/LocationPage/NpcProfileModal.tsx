import { useEffect, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { BASE_URL } from '../../../api/api';
import { NPC_ROLE_LABELS } from '../../../constants/npc';

interface NpcDetail {
  id: number;
  name: string;
  avatar: string | null;
  level: number;
  class_name: string | null;
  race_name: string | null;
  npc_role: string | null;
  biography: string | null;
  personality: string | null;
  sex: string | null;
  age: number | null;
}

interface NpcProfileModalProps {
  npcId: number;
  onClose: () => void;
}

const NpcProfileModal = ({ npcId, onClose }: NpcProfileModalProps) => {
  const [npc, setNpc] = useState<NpcDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const fetchNpc = async () => {
      try {
        const res = await axios.get<NpcDetail>(`${BASE_URL}/characters/admin/npcs/${npcId}`);
        setNpc(res.data);
      } catch {
        toast.error('Не удалось загрузить данные НПС');
        onClose();
      } finally {
        setLoading(false);
      }
    };
    fetchNpc();
  }, [npcId, onClose]);

  const handleOverlayClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose();
  };

  const roleLabel = npc?.npc_role ? (NPC_ROLE_LABELS[npc.npc_role] || npc.npc_role) : null;

  return (
    <div className="modal-overlay" onClick={handleOverlayClick}>
      <div className="modal-content gold-outline gold-outline-thick relative max-w-lg w-full mx-4">
        {/* Close button */}
        <button
          onClick={onClose}
          className="absolute top-4 right-4 text-white/50 hover:text-white transition-colors z-10"
          aria-label="Закрыть"
        >
          <svg xmlns="http://www.w3.org/2000/svg" className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>

        {loading ? (
          <div className="flex items-center justify-center py-12">
            <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
          </div>
        ) : npc ? (
          <div className="flex flex-col items-center gap-4">
            {/* Avatar */}
            <div className="gold-outline relative w-28 h-28 sm:w-32 sm:h-32 rounded-full overflow-hidden bg-black/40 shrink-0">
              {npc.avatar ? (
                <img src={npc.avatar} alt={npc.name} className="w-full h-full object-cover" />
              ) : (
                <div className="w-full h-full flex items-center justify-center text-white/20">
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-12 h-12" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                  </svg>
                </div>
              )}
            </div>

            {/* Name */}
            <h2 className="gold-text text-xl sm:text-2xl font-medium uppercase text-center">
              {npc.name}
            </h2>

            {/* Role badge */}
            {roleLabel && (
              <span className="px-3 py-1 rounded-full bg-gold/20 text-gold text-xs sm:text-sm font-medium uppercase tracking-wide">
                {roleLabel}
              </span>
            )}

            {/* Info grid */}
            <div className="w-full grid grid-cols-2 sm:grid-cols-3 gap-3 mt-2">
              <div className="flex flex-col items-center gap-1 bg-white/5 rounded-card p-3">
                <span className="text-white/50 text-xs uppercase">Уровень</span>
                <span className="text-white text-sm font-medium">{npc.level}</span>
              </div>
              {npc.class_name && (
                <div className="flex flex-col items-center gap-1 bg-white/5 rounded-card p-3">
                  <span className="text-white/50 text-xs uppercase">Класс</span>
                  <span className="text-white text-sm font-medium">{npc.class_name}</span>
                </div>
              )}
              {npc.race_name && (
                <div className="flex flex-col items-center gap-1 bg-white/5 rounded-card p-3">
                  <span className="text-white/50 text-xs uppercase">Раса</span>
                  <span className="text-white text-sm font-medium">{npc.race_name}</span>
                </div>
              )}
              {npc.sex && (
                <div className="flex flex-col items-center gap-1 bg-white/5 rounded-card p-3">
                  <span className="text-white/50 text-xs uppercase">Пол</span>
                  <span className="text-white text-sm font-medium">
                    {npc.sex === 'male' ? 'Мужской' : npc.sex === 'female' ? 'Женский' : 'Бесполый'}
                  </span>
                </div>
              )}
              {npc.age !== null && npc.age !== undefined && (
                <div className="flex flex-col items-center gap-1 bg-white/5 rounded-card p-3">
                  <span className="text-white/50 text-xs uppercase">Возраст</span>
                  <span className="text-white text-sm font-medium">{npc.age}</span>
                </div>
              )}
            </div>

            {/* Biography */}
            {npc.biography && (
              <div className="w-full mt-2">
                <h3 className="text-white/50 text-xs font-medium uppercase tracking-wide mb-2">Биография</h3>
                <p className="text-white/80 text-sm leading-relaxed">{npc.biography}</p>
              </div>
            )}

            {/* Personality */}
            {npc.personality && (
              <div className="w-full mt-2">
                <h3 className="text-white/50 text-xs font-medium uppercase tracking-wide mb-2">Характер</h3>
                <p className="text-white/80 text-sm leading-relaxed">{npc.personality}</p>
              </div>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default NpcProfileModal;
