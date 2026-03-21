import { useEffect, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { BASE_URL } from '../../../api/api';
import { useAppSelector } from '../../../redux/store';

/* ── Types ── */

interface QuestRewardItem {
  item_id: number;
  item_name: string;
  item_image: string | null;
  quantity: number;
}

interface Quest {
  id: number;
  title: string;
  description: string;
  quest_type: string;
  min_level: number;
  reward_currency: number;
  reward_exp: number;
  reward_items: QuestRewardItem[];
  is_active: boolean;
}

interface NpcQuestsModalProps {
  npcId: number;
  npcName: string;
  npcAvatar: string | null;
  onClose: () => void;
}

const QUEST_TYPE_LABELS: Record<string, string> = {
  standard: 'Обычный',
  daily: 'Ежедневный',
  repeatable: 'Повторяемый',
};

/* ── Component ── */

const NpcQuestsModal = ({ npcId, npcName, npcAvatar, onClose }: NpcQuestsModalProps) => {
  const [quests, setQuests] = useState<Quest[]>([]);
  const [loading, setLoading] = useState(true);
  const [accepting, setAccepting] = useState<number | null>(null);
  const character = useAppSelector((state) => state.user.character);
  const characterId = character?.id ?? null;

  useEffect(() => {
    const fetchQuests = async () => {
      try {
        const res = await axios.get<Quest[]>(`${BASE_URL}/locations/npcs/${npcId}/quests`);
        setQuests(res.data);
      } catch {
        toast.error('Не удалось загрузить квесты');
      } finally {
        setLoading(false);
      }
    };
    fetchQuests();
  }, [npcId]);

  const handleAccept = async (questId: number) => {
    if (!characterId) {
      toast.error('Персонаж не найден');
      return;
    }
    setAccepting(questId);
    try {
      await axios.post(`${BASE_URL}/locations/quests/${questId}/accept`, {
        character_id: characterId,
      });
      toast.success('Квест принят!');
      // Remove accepted quest from list
      setQuests((prev) => prev.filter((q) => q.id !== questId));
    } catch (err) {
      const message =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? err.response.data.detail
          : 'Не удалось принять квест';
      toast.error(message);
    } finally {
      setAccepting(null);
    }
  };

  const handleOverlayClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (e.target === e.currentTarget) onClose();
  };

  return (
    <div className="modal-overlay" onClick={handleOverlayClick}>
      <div className="modal-content gold-outline gold-outline-thick relative max-w-2xl w-full mx-4 max-h-[90vh] flex flex-col">
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

        {/* Header */}
        <div className="flex items-center gap-3 mb-4">
          <div className="gold-outline relative w-12 h-12 rounded-full overflow-hidden bg-black/40 shrink-0">
            {npcAvatar ? (
              <img src={npcAvatar} alt={npcName} className="w-full h-full object-cover" />
            ) : (
              <div className="w-full h-full flex items-center justify-center text-white/20">
                <svg xmlns="http://www.w3.org/2000/svg" className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
              </div>
            )}
          </div>
          <div>
            <h2 className="gold-text text-lg sm:text-xl font-medium uppercase tracking-wide">
              Квесты
            </h2>
            <p className="text-white/50 text-xs sm:text-sm">{npcName}</p>
          </div>
        </div>

        {/* Quest list */}
        <div className="flex-1 overflow-y-auto gold-scrollbar space-y-3 pr-1">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
            </div>
          ) : quests.length === 0 ? (
            <p className="text-center text-white/50 text-sm py-8">
              Нет доступных квестов
            </p>
          ) : (
            quests.map((quest) => (
              <div
                key={quest.id}
                className="bg-black/50 rounded-card p-4 border border-gold/20 hover:border-gold/40 transition-colors"
              >
                {/* Title + type badge */}
                <div className="flex flex-col sm:flex-row sm:items-center gap-2 mb-2">
                  <h3 className="text-white font-medium text-sm sm:text-base">
                    {quest.title}
                  </h3>
                  <span className="px-2 py-0.5 rounded-full bg-gold/20 text-gold text-[10px] sm:text-xs font-medium uppercase shrink-0 self-start">
                    {QUEST_TYPE_LABELS[quest.quest_type] || quest.quest_type}
                  </span>
                </div>

                {/* Description */}
                <p className="text-white/70 text-xs sm:text-sm mb-3 leading-relaxed">
                  {quest.description}
                </p>

                {/* Min level */}
                {quest.min_level > 1 && (
                  <p className="text-white/40 text-xs mb-2">
                    Мин. уровень: {quest.min_level}
                  </p>
                )}

                {/* Rewards */}
                <div className="flex flex-wrap items-center gap-3 mb-3">
                  <span className="text-white/50 text-xs uppercase font-medium">Награда:</span>
                  {quest.reward_currency > 0 && (
                    <span className="flex items-center gap-1 text-xs">
                      <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4 text-yellow-400" fill="currentColor" viewBox="0 0 20 20">
                        <circle cx="10" cy="10" r="8" />
                      </svg>
                      <span className="text-yellow-300 font-medium">{quest.reward_currency}</span>
                    </span>
                  )}
                  {quest.reward_exp > 0 && (
                    <span className="flex items-center gap-1 text-xs">
                      <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4 text-site-blue" fill="currentColor" viewBox="0 0 20 20">
                        <path d="M10 2l2.5 5.5L18 8.5l-4 4 1 5.5L10 15l-5 3 1-5.5-4-4 5.5-1z" />
                      </svg>
                      <span className="text-site-blue font-medium">{quest.reward_exp} XP</span>
                    </span>
                  )}
                  {quest.reward_items?.map((ri) => (
                    <span key={ri.item_id} className="flex items-center gap-1 text-xs">
                      {ri.item_image ? (
                        <img src={ri.item_image} alt={ri.item_name} className="w-5 h-5 rounded-full object-cover" />
                      ) : (
                        <span className="w-5 h-5 rounded-full bg-white/10 flex items-center justify-center text-[8px] text-white/30">?</span>
                      )}
                      <span className="text-white/80">{ri.item_name} x{ri.quantity}</span>
                    </span>
                  ))}
                </div>

                {/* Accept button */}
                <button
                  onClick={() => handleAccept(quest.id)}
                  disabled={accepting === quest.id}
                  className="
                    w-full px-4 py-2.5 rounded-card
                    border border-gold/50 bg-gold/10
                    text-gold text-sm font-medium uppercase tracking-wide
                    hover:bg-gold/20 hover:border-gold/80
                    disabled:opacity-50 disabled:cursor-not-allowed
                    transition-all duration-200
                    flex items-center justify-center gap-2
                  "
                >
                  {accepting === quest.id ? (
                    <div className="w-4 h-4 border-2 border-gold/30 border-t-gold rounded-full animate-spin" />
                  ) : (
                    <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                  )}
                  Принять квест
                </button>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
};

export default NpcQuestsModal;
