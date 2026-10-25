import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { clearDungeonCooldown, fetchDungeonStatus, type DungeonAdminStatus } from '../../../api/dungeons';

/*
  What keeps players out of a dungeon right now — the cooldown after a clear,
  a group inside — and the button that restores a cleared dungeon at once.
*/

const TICK_MS = 30_000;

const left = (seconds: number) => {
  const h = Math.floor(seconds / 3600);
  const m = Math.ceil((seconds % 3600) / 60);
  return h > 0 ? `${h} ч ${m} мин` : `${m} мин`;
};

const until = (seconds: number) =>
  new Date(Date.now() + seconds * 1000).toLocaleString('ru-RU', {
    day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit',
  });

const DungeonStatusControl = ({ dungeonId }: { dungeonId: number }) => {
  const [status, setStatus] = useState<DungeonAdminStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [restoring, setRestoring] = useState(false);

  const load = useCallback(async () => {
    try {
      setStatus(await fetchDungeonStatus(dungeonId));
      setError(null);
    } catch {
      setError('Не удалось узнать состояние подземелья');
    }
  }, [dungeonId]);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), TICK_MS);
    return () => clearInterval(timer);
  }, [load]);

  const restore = async () => {
    setRestoring(true);
    try {
      await clearDungeonCooldown(dungeonId);
      toast.success('Подземелье восстановлено — в него снова можно войти');
      await load();
    } catch {
      toast.error('Не удалось восстановить подземелье');
    } finally {
      setRestoring(false);
    }
  };

  if (error) return <p className="text-sm text-site-red">{error}</p>;
  if (!status) return <p className="text-sm text-white/40">Загрузка состояния...</p>;

  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4 flex-wrap">
      {status.is_on_cooldown ? (
        <span className="text-sm text-yellow-300/90">
          Откат после зачистки: восстановится {until(status.cooldown_remaining_seconds)} (через{' '}
          {left(status.cooldown_remaining_seconds)})
        </span>
      ) : (
        <span className="text-sm text-green-400">Подземелье восстановлено, войти можно</span>
      )}
      {status.occupied_session_id && (
        <span className="text-sm text-white/70">
          Внутри группа —{' '}
          <Link to="/admin/dungeons/sessions" className="site-link">
            забег #{status.occupied_session_id}
          </Link>
        </span>
      )}
      {status.is_on_cooldown && (
        <button
          type="button"
          onClick={() => void restore()}
          disabled={restoring}
          className="btn-blue !text-sm !px-4 !py-1.5 self-start disabled:opacity-50"
        >
          {restoring ? 'Восстановление...' : 'Восстановить сейчас'}
        </button>
      )}
    </div>
  );
};

export default DungeonStatusControl;
