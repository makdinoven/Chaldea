import { useEffect, useState, useCallback } from 'react';
import { motion } from 'motion/react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { BASE_URL } from '../../api/api';

/* ── Types ── */

interface QuestObjective {
  id: number;
  description: string;
  objective_type: string;
  target_count: number;
  current_count: number;
}

interface QuestRewardItem {
  item_id: number;
  item_name: string;
  item_image: string | null;
  quantity: number;
}

interface ActiveQuest {
  id: number;
  quest_id: number;
  title: string;
  description: string;
  quest_type: string;
  reward_currency: number;
  reward_exp: number;
  reward_items: QuestRewardItem[];
  objectives: QuestObjective[];
  accepted_at: string;
}

interface QuestLogTabProps {
  characterId: number;
}

const QUEST_TYPE_LABELS: Record<string, string> = {
  standard: 'Обычный',
  daily: 'Ежедневный',
  repeatable: 'Повторяемый',
};

/* ── Component ── */

const QuestLogTab = ({ characterId }: QuestLogTabProps) => {
  const [quests, setQuests] = useState<ActiveQuest[]>([]);
  const [loading, setLoading] = useState(true);
  const [completing, setCompleting] = useState<number | null>(null);
  const [abandoning, setAbandoning] = useState<number | null>(null);

  const fetchQuests = useCallback(async () => {
    try {
      const res = await axios.get<ActiveQuest[]>(
        `${BASE_URL}/locations/quests/active`,
        { params: { character_id: characterId } },
      );
      setQuests(res.data);
    } catch {
      toast.error('Не удалось загрузить активные задания');
    } finally {
      setLoading(false);
    }
  }, [characterId]);

  useEffect(() => {
    fetchQuests();
  }, [fetchQuests]);

  const isQuestComplete = (quest: ActiveQuest) =>
    quest.objectives.length > 0 &&
    quest.objectives.every((obj) => obj.current_count >= obj.target_count);

  const handleComplete = async (questId: number) => {
    setCompleting(questId);
    try {
      await axios.post(`${BASE_URL}/locations/quests/${questId}/complete`, {
        character_id: characterId,
      });
      toast.success('Задание выполнено! Награда получена');
      setQuests((prev) => prev.filter((q) => q.id !== questId));
    } catch (err) {
      const message =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? err.response.data.detail
          : 'Не удалось сдать задание';
      toast.error(message);
    } finally {
      setCompleting(null);
    }
  };

  const handleAbandon = async (questId: number) => {
    if (!window.confirm('Отказаться от задания? Прогресс будет потерян.')) return;
    setAbandoning(questId);
    try {
      await axios.post(`${BASE_URL}/locations/quests/${questId}/abandon`, {
        character_id: characterId,
      });
      toast.success('Вы отказались от задания');
      setQuests((prev) => prev.filter((q) => q.id !== questId));
    } catch (err) {
      const message =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? err.response.data.detail
          : 'Не удалось отказаться от задания';
      toast.error(message);
    } finally {
      setAbandoning(null);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16">
        <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
      </div>
    );
  }

  if (quests.length === 0) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: 'easeOut' }}
        className="flex flex-col items-center justify-center py-32"
      >
        <svg xmlns="http://www.w3.org/2000/svg" className="w-16 h-16 text-white/10 mb-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        </svg>
        <h2 className="gold-text text-xl sm:text-2xl font-medium uppercase mb-2">
          Нет активных заданий
        </h2>
        <p className="text-white/50 text-sm">
          Поговорите с НПС, чтобы получить задания
        </p>
      </motion.div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="flex flex-col gap-4"
    >
      {quests.map((quest) => {
        const complete = isQuestComplete(quest);
        return (
          <div
            key={quest.id}
            className={`
              bg-black/50 rounded-card p-4 sm:p-5
              border transition-colors
              ${complete ? 'border-green-500/40' : 'border-gold/20'}
            `}
          >
            {/* Title + type badge */}
            <div className="flex flex-col sm:flex-row sm:items-center gap-2 mb-3">
              <h3 className="text-white font-medium text-sm sm:text-base flex-1">
                {quest.title}
              </h3>
              <div className="flex items-center gap-2 shrink-0">
                <span className="px-2 py-0.5 rounded-full bg-gold/20 text-gold text-[10px] sm:text-xs font-medium uppercase">
                  {QUEST_TYPE_LABELS[quest.quest_type] || quest.quest_type}
                </span>
                {complete && (
                  <span className="px-2 py-0.5 rounded-full bg-green-500/20 text-green-400 text-[10px] sm:text-xs font-medium uppercase">
                    Выполнен
                  </span>
                )}
              </div>
            </div>

            {/* Description */}
            <p className="text-white/60 text-xs sm:text-sm mb-4 leading-relaxed">
              {quest.description}
            </p>

            {/* Objectives */}
            {quest.objectives.length > 0 && (
              <div className="flex flex-col gap-2.5 mb-4">
                <span className="text-white/50 text-xs uppercase font-medium tracking-wide">
                  Задачи
                </span>
                {quest.objectives.map((obj) => {
                  const progress = Math.min(obj.current_count / Math.max(obj.target_count, 1), 1);
                  const done = obj.current_count >= obj.target_count;
                  return (
                    <div key={obj.id} className="flex flex-col gap-1">
                      <div className="flex items-center justify-between">
                        <span className={`text-xs sm:text-sm ${done ? 'text-green-400 line-through' : 'text-white/80'}`}>
                          {obj.description}
                        </span>
                        <span className={`text-xs font-medium ml-2 shrink-0 ${done ? 'text-green-400' : 'text-white/50'}`}>
                          {obj.current_count}/{obj.target_count}
                        </span>
                      </div>
                      <div className="stat-bar">
                        <div
                          className={`stat-bar-fill ${done ? 'stat-bar-energy' : 'stat-bar-mana'}`}
                          style={{ width: `${progress * 100}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Rewards */}
            <div className="flex flex-wrap items-center gap-3 mb-4">
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

            {/* Actions */}
            <div className="flex flex-col sm:flex-row gap-2">
              {complete && (
                <button
                  onClick={() => handleComplete(quest.id)}
                  disabled={completing === quest.id}
                  className="
                    flex-1 px-4 py-2.5 rounded-card
                    border border-green-500/50 bg-green-500/10
                    text-green-400 text-sm font-medium uppercase tracking-wide
                    hover:bg-green-500/20 hover:border-green-500/80
                    disabled:opacity-50 disabled:cursor-not-allowed
                    transition-all duration-200
                    flex items-center justify-center gap-2
                  "
                >
                  {completing === quest.id ? (
                    <div className="w-4 h-4 border-2 border-green-400/30 border-t-green-400 rounded-full animate-spin" />
                  ) : (
                    <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                  )}
                  Сдать задание
                </button>
              )}
              <button
                onClick={() => handleAbandon(quest.id)}
                disabled={abandoning === quest.id}
                className="
                  px-4 py-2.5 rounded-card
                  border border-white/20 bg-white/5
                  text-white/60 text-sm font-medium uppercase tracking-wide
                  hover:bg-site-red/10 hover:border-site-red/50 hover:text-site-red
                  disabled:opacity-50 disabled:cursor-not-allowed
                  transition-all duration-200
                  flex items-center justify-center gap-2
                "
              >
                {abandoning === quest.id ? (
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                ) : (
                  <svg xmlns="http://www.w3.org/2000/svg" className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                  </svg>
                )}
                Отказаться
              </button>
            </div>
          </div>
        );
      })}
    </motion.div>
  );
};

export default QuestLogTab;
