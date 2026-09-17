// FEAT-151 — «Задания» tab, master-detail redesign per Claude Design mock
// (journal on the left / detail on the right; single column below `lg`).
// Same locations-service API as the former QuestLogTab.
// FEAT-166 — «Задания» / «Детали» panels, 392px journal column, shared primitives.
import { useCallback, useEffect, useMemo, useState } from 'react';
import { motion } from 'motion/react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { BookOpen, Scroll } from 'lucide-react';
import { BASE_URL } from '../../../api/api';
import PanelShell, { PANEL_DESKTOP_HEIGHT_CLASS } from '../PanelShell';
import FilterChips, { type FilterChipItem } from '../shared/FilterChips';
import EmptyState from '../shared/EmptyState';
import ErrorState from '../shared/ErrorState';
import LoadingState from '../shared/LoadingState';
import PanelCounter from '../shared/PanelCounter';
import PanelScrollArea from '../shared/PanelScrollArea';
import PanelToolbar from '../shared/PanelToolbar';
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

  const readyChip = (className: string) => (
    <span
      className={`items-center gap-2 px-3 py-1 rounded-full border border-stat-energy/[0.35] bg-stat-energy/10 min-w-0 ${className}`}
    >
      <span className="w-2 h-2 shrink-0 rounded-full bg-stat-energy shadow-[0_0_8px_rgba(136,179,50,0.8)]" />
      <span className="text-[11px] font-medium text-stat-energy truncate">
        {readyText(readyCount)}
      </span>
    </span>
  );

  const counterText =
    typeFilter === 'all' ? `${quests.length}` : `${filteredQuests.length}/${quests.length}`;

  const renderJournal = () => {
    if (loading) return <LoadingState />;
    if (error && quests.length === 0) {
      return <ErrorState message={error} onRetry={fetchQuests} />;
    }
    if (quests.length === 0) {
      return (
        <EmptyState
          icon={<Scroll size={36} strokeWidth={1.3} className="text-white/20" />}
          message="Нет активных заданий"
          hint="Поговорите с НПС, чтобы получить задания"
        />
      );
    }
    if (filteredQuests.length === 0) {
      return (
        <EmptyState
          icon={<Scroll size={36} strokeWidth={1.3} className="text-white/20" />}
          message="Нет заданий выбранного типа"
        />
      );
    }
    return (
      <QuestJournalList
        quests={filteredQuests}
        selectedId={selectedId}
        onSelect={setSelectedId}
      />
    );
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="grid grid-cols-1 lg:grid-cols-[392px_1fr] gap-5 items-start"
    >
      {/* Journal panel: filters in the toolbar, list in the scroll area */}
      <PanelShell
        title="Задания"
        icon={<BookOpen size={18} strokeWidth={1.8} className="text-gold shrink-0" />}
        headerExtra={
          <div className="flex items-center gap-2.5 min-w-0">
            {!loading && readyCount > 0 && readyChip('hidden sm:flex')}
            {!loading && <PanelCounter>{counterText}</PanelCounter>}
          </div>
        }
        className={PANEL_DESKTOP_HEIGHT_CLASS}
        bodyClassName="flex-1 min-h-0 flex flex-col"
      >
        <PanelToolbar>
          {!loading && readyCount > 0 && readyChip('flex sm:hidden')}
          <FilterChips
            items={TYPE_FILTERS}
            active={typeFilter}
            onChange={setTypeFilter}
            className="w-full min-w-0"
          />
        </PanelToolbar>
        <PanelScrollArea>{renderJournal()}</PanelScrollArea>
      </PanelShell>

      {/* Detail panel — hidden below lg until a quest is selected */}
      <PanelShell
        title="Детали"
        icon={<Scroll size={18} strokeWidth={1.8} className="text-gold shrink-0" />}
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
    </motion.div>
  );
};

export default QuestsTab;
