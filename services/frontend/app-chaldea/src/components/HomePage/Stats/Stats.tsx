import { useEffect, useState } from 'react';
import {
  fetchHomeLeaderboards,
  HOME_LEADERBOARDS_LIMIT,
  type HomeLeaderboards,
} from '../../../api/homeStats';
import statsBg from '../../../assets/stats_bg.png';
import Podium from './Podium';
import RankRow from './RankRow';

interface BoardConfig {
  key: keyof HomeLeaderboards;
  title: string;
}

const BOARDS: BoardConfig[] = [
  { key: 'symbols_daily', title: 'Символов за сутки' },
  { key: 'pvp', title: 'PvP-очки' },
  { key: 'pve', title: 'PvE-очки' },
];

const PODIUM_SIZE = 3;

/**
 * Hall of Fame («Зал славы») card: banner with the active-board title and pill
 * tabs, podium for the top-3 and a list for the remaining ranks.
 * Single fetch (all 3 boards, limit 6); tab switching is client-side.
 */
const Stats = () => {
  const [data, setData] = useState<HomeLeaderboards | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeKey, setActiveKey] = useState<keyof HomeLeaderboards>('symbols_daily');

  const load = () => {
    setLoading(true);
    setError(null);
    fetchHomeLeaderboards(HOME_LEADERBOARDS_LIMIT)
      .then(setData)
      .catch(() => setError('Не удалось загрузить статистику'))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const activeBoard = BOARDS.find((b) => b.key === activeKey) ?? BOARDS[0];
  const entries = data?.[activeBoard.key] ?? [];
  const podiumEntries = entries.slice(0, PODIUM_SIZE);
  const restEntries = entries.slice(PODIUM_SIZE);

  return (
    <div className="gray-bg rounded-card overflow-hidden">
      {/* Banner: background image + active board title + pill tabs */}
      <div
        style={{ backgroundImage: `url(${statsBg})` }}
        className="relative bg-cover bg-[center_top] bg-no-repeat px-4 pt-7 sm:px-8"
      >
        <div className="absolute inset-0 bg-gradient-to-b from-black/55 to-site-bg" />
        <div className="relative flex flex-col items-center gap-5">
          <h2 className="gold-text text-center text-3xl font-medium tracking-[0.02em] sm:text-4xl">
            {activeBoard.title}
          </h2>
          <div className="flex flex-wrap justify-center gap-2" role="tablist">
            {BOARDS.map((board) => {
              const isActive = board.key === activeBoard.key;
              return (
                <button
                  key={board.key}
                  type="button"
                  role="tab"
                  aria-selected={isActive}
                  onClick={() => setActiveKey(board.key)}
                  className={`rounded-full border px-4 py-2 text-xs font-medium uppercase tracking-[0.06em] transition-all duration-200 ease-site sm:px-5 ${
                    isActive
                      ? 'border-gold/50 bg-gradient-to-b from-gold/20 to-gold/5 text-gold-light'
                      : 'border-white/10 bg-white/5 text-white/60 hover:text-site-blue'
                  }`}
                >
                  {board.title}
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Body: loading / error / empty / podium + rest list */}
      {loading ? (
        <p className="py-12 text-center text-sm text-white/50">Загрузка...</p>
      ) : error ? (
        <div className="flex flex-col items-center gap-3 py-12">
          <p className="text-sm text-site-red">{error}</p>
          <button onClick={load} className="btn-blue px-5 py-2 text-sm">
            Повторить
          </button>
        </div>
      ) : entries.length === 0 ? (
        <p className="py-12 text-center text-sm text-white/40">Пока пусто</p>
      ) : (
        <>
          <Podium entries={podiumEntries} />
          {restEntries.length > 0 && (
            <div className="mx-auto flex w-full max-w-[760px] flex-col gap-0.5 px-3 pb-6 pt-2 sm:px-6">
              {restEntries.map((entry, i) => (
                <RankRow key={entry.character_id} entry={entry} rank={PODIUM_SIZE + i + 1} />
              ))}
            </div>
          )}
          {restEntries.length === 0 && <div className="pb-6" />}
        </>
      )}
    </div>
  );
};

export default Stats;
