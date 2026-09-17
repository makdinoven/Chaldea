// ProfilePage TitlesTab — redesigned per Claude Design mock (FEAT-151),
// moved into a PanelShell with toolbar + scroll area (FEAT-166).
// Keeps condition progress bars on locked titles, XP-reward badges and
// select/unselect actions (user decision); Все/Полученные/Закрытые filters.
import { useEffect, useMemo, useState } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import { Award, Lock, Star } from 'lucide-react';
import { fetchCharacterTitles, setActiveTitle, unsetActiveTitle } from '../../../api/titles';
import type { CharacterTitle } from '../../../types/titles';
import { useAppSelector } from '../../../redux/store';
import PanelShell, { PANEL_DESKTOP_HEIGHT_CLASS } from '../PanelShell';
import FilterChips, { type FilterChipItem } from '../shared/FilterChips';
import EmptyState from '../shared/EmptyState';
import ErrorState from '../shared/ErrorState';
import LoadingState from '../shared/LoadingState';
import PanelCounter from '../shared/PanelCounter';
import PanelScrollArea from '../shared/PanelScrollArea';
import PanelToolbar from '../shared/PanelToolbar';
import TitleCard from './TitleCard';

type TitleFilter = 'all' | 'unlocked' | 'locked';

/* ── Props ── */

interface TitlesTabProps {
  characterId: number;
}

/* ── Component ── */

const TitlesTab = ({ characterId }: TitlesTabProps) => {
  const [titles, setTitles] = useState<CharacterTitle[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState<number | null>(null);
  const [filter, setFilter] = useState<TitleFilter>('all');

  const activeTitle = useAppSelector((state) => state.profile.character?.active_title ?? null);

  const loadTitles = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchCharacterTitles(characterId);
      setTitles(data);
    } catch {
      const msg = 'Не удалось загрузить титулы';
      setError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadTitles();
  }, [characterId]);

  const handleSetActive = async (titleId: number) => {
    setActionLoading(titleId);
    try {
      await setActiveTitle(characterId, titleId);
      toast.success('Титул установлен');
      await loadTitles();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Ошибка при установке титула';
      toast.error(msg);
    } finally {
      setActionLoading(null);
    }
  };

  const handleUnsetActive = async () => {
    setActionLoading(-1);
    try {
      await unsetActiveTitle(characterId);
      toast.success('Активный титул снят');
      await loadTitles();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Ошибка при снятии титула';
      toast.error(msg);
    } finally {
      setActionLoading(null);
    }
  };

  const unlockedCount = useMemo(() => titles.filter((t) => t.is_unlocked).length, [titles]);

  const filterItems: FilterChipItem[] = useMemo(
    () => [
      { key: 'all', label: 'Все', count: titles.length },
      { key: 'unlocked', label: 'Полученные', count: unlockedCount },
      { key: 'locked', label: 'Закрытые', count: titles.length - unlockedCount },
    ],
    [titles.length, unlockedCount]
  );

  const filteredTitles = useMemo(() => {
    if (filter === 'unlocked') return titles.filter((t) => t.is_unlocked);
    if (filter === 'locked') return titles.filter((t) => !t.is_unlocked);
    return titles;
  }, [titles, filter]);

  const tabMotion = {
    initial: { opacity: 0, y: 10 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.3, ease: 'easeOut' as const },
  };

  const panelIcon = <Award size={18} strokeWidth={1.8} className="text-gold shrink-0" />;

  if (loading) {
    return (
      <motion.div {...tabMotion}>
        <PanelShell title="Титулы" icon={panelIcon}>
          <LoadingState />
        </PanelShell>
      </motion.div>
    );
  }

  if (error && titles.length === 0) {
    return (
      <motion.div {...tabMotion}>
        <PanelShell title="Титулы" icon={panelIcon}>
          <ErrorState message={error} />
        </PanelShell>
      </motion.div>
    );
  }

  return (
    <motion.div {...tabMotion}>
      <PanelShell
        title="Титулы"
        icon={panelIcon}
        headerExtra={
          <PanelCounter>
            {unlockedCount}/{titles.length}
          </PanelCounter>
        }
        className={PANEL_DESKTOP_HEIGHT_CLASS}
        bodyClassName="flex-1 min-h-0 flex flex-col"
      >
        <PanelToolbar>
          <FilterChips
            items={filterItems}
            active={filter}
            onChange={(key) => setFilter(key as TitleFilter)}
            className="min-w-0 max-w-full"
          />
        </PanelToolbar>

        <PanelScrollArea>
          {/* Cards grid / empty states */}
          {titles.length === 0 ? (
            <EmptyState
              icon={<Star size={32} strokeWidth={1.5} className="text-white/20" />}
              message="Нет доступных титулов"
            />
          ) : filteredTitles.length === 0 ? (
            <EmptyState
              icon={
                filter === 'locked' ? (
                  <Lock size={32} strokeWidth={1.5} className="text-white/20" />
                ) : (
                  <Star size={32} strokeWidth={1.5} className="text-white/20" />
                )
              }
              message={
                filter === 'locked'
                  ? 'Все титулы уже получены'
                  : 'Нет титулов по выбранному фильтру'
              }
            />
          ) : (
            <motion.div
              initial="hidden"
              animate="visible"
              variants={{
                hidden: {},
                visible: { transition: { staggerChildren: 0.04 } },
              }}
              className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4"
            >
              {filteredTitles.map((title) => (
                <TitleCard
                  key={title.id_title}
                  title={title}
                  isActive={activeTitle === title.name}
                  actionLoading={actionLoading}
                  onSetActive={handleSetActive}
                  onUnsetActive={handleUnsetActive}
                />
              ))}
            </motion.div>
          )}
        </PanelScrollArea>
      </PanelShell>
    </motion.div>
  );
};

export default TitlesTab;
