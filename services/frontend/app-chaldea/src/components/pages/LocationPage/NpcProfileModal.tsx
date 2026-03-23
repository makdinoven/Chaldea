import { useEffect, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { BASE_URL } from '../../../api/api';
import { NPC_ROLE_LABELS } from '../../../constants/npc';
import { useAppSelector } from '../../../redux/store';
import useNpcAttack from '../../../hooks/useNpcAttack';
import NpcDialogueModal from './NpcDialogueModal';
import NpcShopModal from './NpcShopModal';
import NpcQuestsModal from './NpcQuestsModal';

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
  const [hasDialogue, setHasDialogue] = useState(false);
  const [dialogueOpen, setDialogueOpen] = useState(false);
  const [hasShop, setHasShop] = useState(false);
  const [shopOpen, setShopOpen] = useState(false);
  const [hasQuests, setHasQuests] = useState(false);
  const [questsOpen, setQuestsOpen] = useState(false);
  const characterId = useAppSelector((state) => state.user.character?.id) as number | null;
  const [npcNameForAttack, setNpcNameForAttack] = useState('');
  const { attacking, handleAttack } = useNpcAttack({
    npcId,
    npcName: npcNameForAttack,
    currentCharacterId: characterId,
  });

  useEffect(() => {
    const fetchNpc = async () => {
      try {
        const res = await axios.get<NpcDetail>(`${BASE_URL}/characters/admin/npcs/${npcId}`);
        setNpc(res.data);
        setNpcNameForAttack(res.data.name);
      } catch {
        toast.error('Не удалось загрузить данные НПС');
        onClose();
      } finally {
        setLoading(false);
      }
    };
    fetchNpc();
  }, [npcId, onClose]);

  // Check if NPC has a dialogue tree
  useEffect(() => {
    const checkDialogue = async () => {
      try {
        await axios.get(`${BASE_URL}/locations/npcs/${npcId}/dialogue`);
        setHasDialogue(true);
      } catch {
        setHasDialogue(false);
      }
    };
    checkDialogue();
  }, [npcId]);

  // Check if NPC has a shop
  useEffect(() => {
    const checkShop = async () => {
      try {
        const res = await axios.get(`${BASE_URL}/locations/npcs/${npcId}/shop`);
        setHasShop(Array.isArray(res.data) && res.data.length > 0);
      } catch {
        setHasShop(false);
      }
    };
    checkShop();
  }, [npcId]);

  // Check if NPC has quests (available OR dialogue-only)
  useEffect(() => {
    const checkQuests = async () => {
      try {
        const [questsRes, dqRes] = await Promise.allSettled([
          characterId
            ? axios.get(`${BASE_URL}/locations/npcs/${npcId}/quests`, { params: { character_id: characterId } })
            : Promise.resolve({ data: [] }),
          axios.get<number[]>(`${BASE_URL}/locations/npcs/${npcId}/dialogue-quest-ids`),
        ]);
        const hasAvailable = questsRes.status === 'fulfilled' && Array.isArray(questsRes.value.data) && questsRes.value.data.length > 0;
        const hasDialogueQuests = dqRes.status === 'fulfilled' && Array.isArray(dqRes.value.data) && dqRes.value.data.length > 0;
        setHasQuests(hasAvailable || hasDialogueQuests);
      } catch {
        setHasQuests(false);
      }
    };
    checkQuests();
  }, [npcId, characterId]);

  const handleOverlayClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose();
  };

  const roleLabel = npc?.npc_role ? (NPC_ROLE_LABELS[npc.npc_role] || npc.npc_role) : null;

  if (questsOpen && npc) {
    return (
      <NpcQuestsModal
        npcId={npc.id}
        npcName={npc.name}
        npcAvatar={npc.avatar}
        onClose={() => setQuestsOpen(false)}
      />
    );
  }

  if (shopOpen && npc) {
    return (
      <NpcShopModal
        npcId={npc.id}
        npcName={npc.name}
        npcAvatar={npc.avatar}
        onClose={() => setShopOpen(false)}
      />
    );
  }

  if (dialogueOpen && npc) {
    return (
      <NpcDialogueModal
        npcId={npc.id}
        npcName={npc.name}
        npcAvatar={npc.avatar}
        onClose={() => setDialogueOpen(false)}
      />
    );
  }

  return (
    <div className="modal-overlay !bg-black/80" onClick={handleOverlayClick}>
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

            {/* Talk button */}
            {hasDialogue && (
              <button
                onClick={() => setDialogueOpen(true)}
                className="
                  mt-2 w-full px-6 py-3 rounded-card
                  border border-gold/50 bg-gold/10
                  text-gold text-sm sm:text-base font-medium uppercase tracking-wide
                  hover:bg-gold/20 hover:border-gold/80
                  transition-all duration-200
                  flex items-center justify-center gap-2
                "
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
                Поговорить
              </button>
            )}

            {/* Trade button */}
            {hasShop && (
              <button
                onClick={() => setShopOpen(true)}
                className="
                  mt-2 w-full px-6 py-3 rounded-card
                  border border-gold/50 bg-gold/10
                  text-gold text-sm sm:text-base font-medium uppercase tracking-wide
                  hover:bg-gold/20 hover:border-gold/80
                  transition-all duration-200
                  flex items-center justify-center gap-2
                "
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 100 4 2 2 0 000-4z" />
                </svg>
                Торговля
              </button>
            )}

            {/* Quests button */}
            {hasQuests && (
              <button
                onClick={() => setQuestsOpen(true)}
                className="
                  mt-2 w-full px-6 py-3 rounded-card
                  border border-gold/50 bg-gold/10
                  text-gold text-sm sm:text-base font-medium uppercase tracking-wide
                  hover:bg-gold/20 hover:border-gold/80
                  transition-all duration-200
                  flex items-center justify-center gap-2
                "
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
                </svg>
                Задания
              </button>
            )}

            {/* Attack button */}
            {characterId && (
              <button
                onClick={handleAttack}
                disabled={attacking}
                className="
                  mt-2 w-full px-6 py-3 rounded-card
                  border border-site-red/50 bg-site-red/10
                  text-site-red text-sm sm:text-base font-medium uppercase tracking-wide
                  hover:bg-site-red/20 hover:border-site-red/80
                  transition-all duration-200
                  flex items-center justify-center gap-2
                  disabled:opacity-50 disabled:cursor-not-allowed
                "
              >
                {attacking ? (
                  <div className="w-5 h-5 border-2 border-site-red/30 border-t-site-red rounded-full animate-spin" />
                ) : (
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                )}
                {attacking ? 'Атака...' : 'Напасть'}
              </button>
            )}
          </div>
        ) : null}
      </div>
    </div>
  );
};

export default NpcProfileModal;
