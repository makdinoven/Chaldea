import { useEffect, useState } from 'react';
import {
  fetchHomeLeaderboards,
  type HomeLeaderboards,
  type LeaderboardEntry,
} from '../../../api/homeStats';
import statsBg from '../../../assets/stats_bg.png';
import statsUserImg from '../../../assets/stats_user_img.png';

interface BoardConfig {
  key: keyof HomeLeaderboards;
  title: string;
}

const BOARDS: BoardConfig[] = [
  { key: 'symbols_daily', title: 'Символов за сутки' },
  { key: 'pvp', title: 'PvP-очки' },
  { key: 'pve', title: 'PvE-очки' },
];

const formatValue = (value: number) => value.toLocaleString('ru-RU');

const UserRow = ({ entry, rank }: { entry: LeaderboardEntry; rank: number }) => (
  <div className="flex items-center gap-3">
    <span className="text-white/40 text-sm w-4 shrink-0 text-right tabular-nums">{rank}</span>
    <img
      src={entry.avatar || statsUserImg}
      onError={(e) => {
        (e.currentTarget as HTMLImageElement).src = statsUserImg;
      }}
      alt={entry.name}
      className="w-10 h-10 rounded-full object-cover shrink-0 bg-white/5"
    />
    <div className="flex flex-col min-w-0">
      <span className="text-gold text-base leading-tight truncate">{entry.name}</span>
      <span className="gold-text text-base leading-tight tabular-nums">
        {formatValue(entry.value)}
      </span>
    </div>
  </div>
);

const Board = ({ title, entries }: { title: string; entries: LeaderboardEntry[] }) => (
  <div className="flex flex-col items-center gap-6">
    <h3 className="text-gold text-lg sm:text-xl font-normal text-center">{title}</h3>
    {entries.length === 0 ? (
      <p className="text-white/40 text-sm">Пока пусто</p>
    ) : (
      <div className="flex flex-col gap-5 w-full max-w-[220px]">
        {entries.map((entry, i) => (
          <UserRow key={entry.character_id} entry={entry} rank={i + 1} />
        ))}
      </div>
    )}
  </div>
);

const Stats = () => {
  const [data, setData] = useState<HomeLeaderboards | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    setLoading(true);
    setError(null);
    fetchHomeLeaderboards(3)
      .then(setData)
      .catch(() => setError('Не удалось загрузить статистику'))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  return (
    <div className="gray-bg rounded-card overflow-hidden">
      {/* Gilded header */}
      <div
        style={{ backgroundImage: `url(${statsBg})` }}
        className="relative flex items-center justify-center py-8 bg-cover bg-center bg-no-repeat"
      >
        <div className="absolute inset-0 bg-black/60" />
        <h2 className="relative z-[1] gold-text text-3xl sm:text-4xl font-medium tracking-[0.02em] text-center">
          Статистика
        </h2>
      </div>

      {/* Body */}
      <div className="px-5 sm:px-8 py-6 sm:py-8">
        {loading ? (
          <p className="text-white/50 text-sm text-center py-6">Загрузка...</p>
        ) : error ? (
          <div className="flex flex-col items-center gap-3 py-6">
            <p className="text-site-red text-sm">{error}</p>
            <button onClick={load} className="btn-blue text-sm px-5 py-2">
              Повторить
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-10 sm:gap-6">
            {BOARDS.map((board) => (
              <Board key={board.key} title={board.title} entries={data?.[board.key] ?? []} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default Stats;
