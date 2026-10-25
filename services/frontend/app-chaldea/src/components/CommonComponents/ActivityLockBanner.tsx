/**
 * ActivityLockBanner (FEAT-175).
 *
 * Compact site-wide strip under the header while the selected character is
 * locked by a dungeon run («Персонаж в подземелье — вернуться к забегу») or
 * knocked out after a wipe («Персонаж без сознания до HH:MM», local time).
 * Hidden on the page of the very run it points to, and on that run's battle page.
 */
import { Link, useLocation } from 'react-router-dom';
import useActivityLock from '../../hooks/useActivityLock';

/** The battle page (not watching someone else's): /location/:id/battle/:id. */
const BATTLE_PAGE = /^\/location\/\d+\/battle\/\d+\/?$/;

const ActivityLockBanner = () => {
  const lock = useActivityLock();
  const { pathname } = useLocation();

  if (!lock.locked) return null;

  if (lock.reason === 'dungeon') {
    const sessionPath = lock.dungeonSessionId ? `/dungeon-session/${lock.dungeonSessionId}` : null;
    if (sessionPath && pathname === sessionPath) return null;
    // A character locked in a run fights only the run's battles: no need to send them back from there.
    if (BATTLE_PAGE.test(pathname)) return null;
    return (
      <div
        role="status"
        className="mb-4 rounded-card border border-rarity-epic/40 bg-site-bg backdrop-blur-sm px-3 py-2.5 sm:px-4 flex flex-wrap items-center gap-x-3 gap-y-2"
      >
        <span className="text-lg leading-none shrink-0" aria-hidden>🏰</span>
        <span className="text-white text-sm flex-1 min-w-[180px]">
          Персонаж в подземелье — действия снаружи недоступны
        </span>
        {sessionPath && (
          <Link to={sessionPath} className="btn-blue text-xs sm:text-sm px-4 py-1.5 shrink-0">
            Вернуться к забегу
          </Link>
        )}
      </div>
    );
  }

  return (
    <div
      role="status"
      className="mb-4 rounded-card border border-site-red/40 bg-site-bg backdrop-blur-sm px-3 py-2.5 sm:px-4 flex flex-wrap items-center gap-x-3 gap-y-1"
    >
      <span className="text-lg leading-none shrink-0" aria-hidden>💫</span>
      <div className="flex flex-col min-w-0 flex-1">
        <span className="text-white text-sm">{lock.message}</span>
        <span className="text-white/50 text-xs">
          Группу вынесли из подземелья. Пока персонаж не очнётся, действовать им нельзя.
        </span>
      </div>
    </div>
  );
};

export default ActivityLockBanner;
