import { useCallback, useEffect, useState } from 'react';
import { BookOpen } from 'lucide-react';
import { fetchFactionHistory, type FactionHistoryItem } from '../../../api/factions';
import { apiErrorMessage } from '../../../api/errors';
import { formatRelativeTime } from '../../../utils/serverDate';
import PanelShell, { PANEL_DESKTOP_HEIGHT_CLASS } from '../PanelShell';
import EmptyState from '../shared/EmptyState';
import ErrorState from '../shared/ErrorState';
import LoadingState from '../shared/LoadingState';
import PanelCounter from '../shared/PanelCounter';
import ProfileCard from '../shared/ProfileCard';

const PAGE_SIZE = 20;

const deltaClass = (delta: number | null): string => {
  if (delta == null || delta === 0) return 'text-white/40';
  return delta > 0 ? 'text-gold' : 'text-site-red';
};

const HistoryRow = ({ item }: { item: FactionHistoryItem }) => (
  <ProfileCard className="p-3 flex flex-col gap-0.5">
    <p className="text-white text-sm leading-relaxed break-words">{item.text}</p>
    <p className="text-white/40 text-xs flex flex-wrap gap-x-2">
      <span>{formatRelativeTime(item.created_at, { style: 'long', yesterday: true })}</span>
      {item.points_after != null && !!item.points_delta && (
        <span className={deltaClass(item.points_delta)}>
          {item.points_delta ? `${item.points_delta > 0 ? '+' : '−'}${Math.abs(item.points_delta)} · ` : ''}
          теперь очков: {item.points_after}
        </span>
      )}
    </p>
  </ProfileCard>
);

/** Faction journal (owner only): joins, ranks, points, warnings, expulsions. */
const FactionHistory = ({ characterId, reloadKey }: { characterId: number; reloadKey: number }) => {
  const [items, setItems] = useState<FactionHistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(
    async (next: number) => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchFactionHistory(characterId, next, PAGE_SIZE);
        setItems((prev) => (next === 1 ? data.items : [...prev, ...data.items]));
        setTotal(data.total);
        setPage(next);
      } catch (err) {
        setError(apiErrorMessage(err, 'Не удалось загрузить журнал фракций'));
      } finally {
        setLoading(false);
      }
    },
    [characterId],
  );

  useEffect(() => {
    void load(1);
  }, [load, reloadKey]);

  const hasMore = items.length < total;

  return (
    <PanelShell
      title="Журнал"
      icon={<BookOpen size={18} strokeWidth={1.8} className="text-gold shrink-0" />}
      headerExtra={!error && total > 0 ? <PanelCounter>{items.length}/{total}</PanelCounter> : undefined}
      className={`lg:w-[40%] lg:shrink-0 ${PANEL_DESKTOP_HEIGHT_CLASS}`}
    >
      {loading && items.length === 0 ? (
        <LoadingState />
      ) : error && items.length === 0 ? (
        <ErrorState message={error} onRetry={() => void load(1)} />
      ) : items.length === 0 ? (
        <EmptyState
          icon={<BookOpen size={32} strokeWidth={1.5} className="text-white/20" />}
          message="Записей пока нет"
          hint="Здесь появятся вступления, звания и очки фракций"
        />
      ) : (
        <div className="flex flex-col gap-2">
          {items.map((item) => (
            <HistoryRow key={item.id} item={item} />
          ))}
          {error && <p className="text-site-red text-xs text-center">{error}</p>}
          {hasMore && (
            <div className="flex justify-center pt-1">
              <button
                type="button"
                onClick={() => void load(page + 1)}
                disabled={loading}
                className="btn-line w-full sm:w-auto px-6 py-2 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? 'Загрузка...' : 'Загрузить ещё'}
              </button>
            </div>
          )}
        </div>
      )}
    </PanelShell>
  );
};

export default FactionHistory;
