// FEAT-151 — «Задания» tab, master-detail redesign per Claude Design mock
// (journal on the left / detail on the right; single column below `lg`).
// Same locations-service API as the former QuestLogTab.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { motion } from 'motion/react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { BookOpen, Scroll } from 'lucide-react';
import { BASE_URL } from '../../../api/api';
import PanelShell, { PANEL_DESKTOP_HEIGHT_CLASS } from '../PanelShell';
import FilterChips, { type FilterChipItem } from '../shared/FilterChips';
import EmptyState from '../shared/EmptyState';
import QuestJournalList from './QuestJournalList';
import QuestDetail from './QuestDetail';
import { type ActiveQuest, isQuestComplete } from './questModel';

interface QuestsTabProps {
  characterId: number;
}

const TYPE_FILTERS: FilterChipItem[] = [
  { key: 'all', label: 'Все' },
  { key: 'standard', label: 'Обычные', dot: 'bg-gold' },
  { key: 'daily', label: 'Ежедневные', dot: 'bg-site-blue' },
  { key: 'repeatable', label: 'Повторяемые', dot: 'bg-stat-energy' },
];

/** «1 готово к сдаче», «2 готовы к сдаче», «5 готово к сдаче» */
const readyText = (n: number): string => {
  const mod10 = n % 10;
  const mod100 = n % 100;
  const verb =
    mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14) ? 'готовы' : 'готово';
  return `${n} ${verb} к сдаче`;
};

const QuestsTab = ({ characterId }: QuestsTabProps) => {
  const [quests, setQuests] = useState<ActiveQuest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [typeFilter, setTypeFilter] = useState('all');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [completing, setCompleting] = useState(false);
  const [abandoning, setAbandoning] = useState(false);

  const fetchQuests = useCallback(async () => {
    try {
      const res = await axios.get<ActiveQuest[]>(`${BASE_URL}/locations/quests/active`, {
        params: { character_id: characterId },
      });
      setQuests(res.data);
      setError(null);
    } catch {
      setError('Не удалось загрузить активные задания');
      toast.error('Не удалось загрузить активные задания');
    } finally {
      setLoading(false);
    }
  }, [characterId]);

  useEffect(() => {
    fetchQuests();
  }, [fetchQuests]);

  const filteredQuests = useMemo(
    () =>
      typeFilter === 'all' ? quests : quests.filter((q) => q.quest_type === typeFilter),
    [quests, typeFilter],
  );

  const selectedQuest = useMemo(
    () => filteredQuests.find((q) => q.id === selectedId) ?? null,
    [filteredQuests, selectedId],
  );

  const readyCount = useMemo(() => quests.filter(isQuestComplete).length, [quests]);

  const handleComplete = async (quest: ActiveQuest) => {
    setCompleting(true);
    try {
      await axios.post(`${BASE_URL}/locations/quests/${quest.quest_id}/complete`, {
        character_id: characterId,
      });
      toast.success('Задание выполнено! Награда получена');
      setSelectedId(null);
      await fetchQuests();
    } catch (err) {
      const message =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? err.response.data.detail
          : 'Не удалось сдать задание';
      toast.error(message);
    } finally {
      setCompleting(false);
    }
  };

  const handleAbandon = async (quest: ActiveQuest) => {
    if (!window.confirm('Отказаться от задания? Прогресс будет потерян.')) return;
    setAbandoning(true);
    try {
      await axios.post(`${BASE_URL}/locations/quests/${quest.quest_id}/abandon`, {
        character_id: characterId,
      });
      toast.success('Вы отказались от задания');
      setSelectedId(null);
      await fetchQuests();
    } catch (err) {
      const message =
        axios.isAxiosError(err) && err.response?.data?.detail
          ? err.response.data.detail
          : 'Не удалось отказаться от задания';
      toast.error(message);
    } finally {
      setAbandoning(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="flex flex-col gap-4"
    >
      {/* Header row: title + counter, ready-to-turn-in chip */}
      <div className="flex items-center justify-between flex-wrap gap-3.5">
        <div className="flex items-center gap-3.5 min-w-0">
          <h3 className="gold-text text-sm font-medium uppercase tracking-[0.12em]">
            Активные задания
          </h3>
          <span className="font-mono tabular-nums text-[13px] text-white/50">
            {quests.length}
          </span>
        </div>
        {readyCount > 0 && (
          <span className="flex items-center gap-2 px-3.5 py-1.5 rounded-full border border-stat-energy/[0.35] bg-stat-energy/10">
            <span className="w-2 h-2 rounded-full bg-stat-energy shadow-[0_0_8px_rgba(136,179,50,0.8)]" />
            <span className="text-xs font-medium text-stat-energy">
              {readyText(readyCount)}
            </span>
          </span>
        )}
      </div>

      {/* Type filter */}
      <FilterChips items={TYPE_FILTERS} active={typeFilter} onChange={setTypeFilter} />

      {/* Master-detail: journal / detail (single column below lg) */}
      <div className="flex flex-col gap-4 lg:grid lg:grid-cols-[346px_1fr] lg:items-start">
        {/* Journal panel */}
        <PanelShell
          title="Журнал"
          icon={<BookOpen size={16} strokeWidth={1.7} className="text-gold shrink-0" />}
          headerExtra={
            <span className="font-mono tabular-nums text-xs text-white/50">
              {filteredQuests.length}
            </span>
          }
          className={PANEL_DESKTOP_HEIGHT_CLASS}
          bodyClassName="flex-1 min-h-0 p-3 lg:overflow-y-auto gold-scrollbar-wide"
        >
          {error && quests.length === 0 ? (
            <div className="flex flex-col items-center justify-center gap-4 py-14 text-center">
              <p className="text-sm text-site-red">{error}</p>
              <button type="button" onClick={fetchQuests} className="btn-line px-6 py-2 text-sm">
                Повторить
              </button>
            </div>
          ) : quests.length === 0 ? (
            <EmptyState
              icon={<Scroll size={36} strokeWidth={1.3} className="text-white/20" />}
              message="Нет активных заданий"
              action={
                <p className="text-xs text-white/30">
                  Поговорите с НПС, чтобы получить задания
                </p>
              }
            />
          ) : filteredQuests.length === 0 ? (
            <EmptyState
              icon={<Scroll size={36} strokeWidth={1.3} className="text-white/20" />}
              message="Нет заданий выбранного типа"
            />
          ) : (
            <QuestJournalList
              quests={filteredQuests}
              selectedId={selectedId}
              onSelect={setSelectedId}
            />
          )}
        </PanelShell>

        {/* Detail panel — hidden below lg until a quest is selected */}
        <PanelShell
          className={`${PANEL_DESKTOP_HEIGHT_CLASS} ${selectedQuest ? '' : 'hidden lg:flex'}`}
          bodyClassName="flex-1 min-h-0 flex flex-col"
        >
          {selectedQuest ? (
            <QuestDetail
              key={selectedQuest.id}
              quest={selectedQuest}
              completing={completing}
              abandoning={abandoning}
              onComplete={() => handleComplete(selectedQuest)}
              onAbandon={() => handleAbandon(selectedQuest)}
            />
          ) : (
            <EmptyState
              className="flex-1"
              icon={<Scroll size={42} strokeWidth={1.3} className="text-white/20" />}
              message="Выберите задание из журнала"
            />
          )}
        </PanelShell>
      </div>
    </motion.div>
  );
};

export default QuestsTab;
