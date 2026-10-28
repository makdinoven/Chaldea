/**
 * ActivityLockBanner (FEAT-175).
 *
 * Compact site-wide strip under the header while the selected character is
 * locked by a dungeon run («Персонаж в подземелье — вернуться к забегу») or
 * knocked out after a wipe («Персонаж без сознания до HH:MM», local time), or
 * asleep in a house bedroom (FEAT-180, «Персонаж спит» + «Проснуться»), or
 * reading in a house library (stage 6b, «Персонаж читает» + «Закончить чтение»).
 * Hidden on the page of the very run it points to, and on that run's battle page.
 */
import { useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import toast from 'react-hot-toast';
import useActivityLock from '../../hooks/useActivityLock';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { getMe } from '../../redux/slices/userSlice';
import { stopReading, stopReadingText, wakeUp } from '../../api/houses';
import { apiErrorMessage } from '../../api/errors';

/** The battle page (not watching someone else's): /location/:id/battle/:id. */
const BATTLE_PAGE = /^\/location\/\d+\/battle\/\d+\/?$/;

const ActivityLockBanner = () => {
  const lock = useActivityLock();
  const { pathname } = useLocation();
  const dispatch = useAppDispatch();
  const characterId = useAppSelector((state) => state.user.character?.id ?? null);
  const [waking, setWaking] = useState(false);

  if (!lock.locked) return null;

  if (lock.reason === 'reading') {
    const stop = async () => {
      if (characterId == null) return;
      setWaking(true);
      try {
        const r = await stopReading(characterId);
        if (r.value > 0) toast.success(stopReadingText(r));
        else toast(stopReadingText(r));
        await dispatch(getMe());
      } catch (e) {
        toast.error(apiErrorMessage(e, 'Не удалось закончить чтение'));
      } finally {
        setWaking(false);
      }
    };
    return (
      <div
        role="status"
        className="mb-4 rounded-card border border-gold-dark/40 bg-site-bg backdrop-blur-sm px-3 py-2.5 sm:px-4 flex flex-wrap items-center gap-x-3 gap-y-2"
      >
        <span className="text-lg leading-none shrink-0" aria-hidden>📖</span>
        <div className="flex flex-col min-w-[180px] flex-1">
          <span className="text-white text-sm">{lock.message}</span>
          <span className="text-white/50 text-xs">
            Каждый полный час чтения — +1 % ко всему опыту на 24 ч после окончания. Пока персонаж читает, действовать им нельзя.
          </span>
        </div>
        {characterId != null && (
          <button type="button" onClick={() => void stop()} disabled={waking}
            className="btn-blue text-xs sm:text-sm px-4 py-1.5 shrink-0 disabled:opacity-50">
            {waking ? 'Закрываем книгу...' : 'Закончить чтение'}
          </button>
        )}
      </div>
    );
  }

  if (lock.reason === 'asleep') {
    const wake = async () => {
      if (characterId == null) return;
      setWaking(true);
      try {
        await wakeUp(characterId);
        toast.success('Персонаж проснулся');
        await dispatch(getMe());
      } catch (e) {
        toast.error(apiErrorMessage(e, 'Не удалось разбудить персонажа'));
      } finally {
        setWaking(false);
      }
    };
    return (
      <div
        role="status"
        className="mb-4 rounded-card border border-site-blue/40 bg-site-bg backdrop-blur-sm px-3 py-2.5 sm:px-4 flex flex-wrap items-center gap-x-3 gap-y-2"
      >
        <span className="text-lg leading-none shrink-0" aria-hidden>💤</span>
        <div className="flex flex-col min-w-[180px] flex-1">
          <span className="text-white text-sm">{lock.message}</span>
          <span className="text-white/50 text-xs">
            Во сне восстановление идёт быстрее, но действовать персонажем нельзя, пока он не проснётся.
          </span>
        </div>
        {characterId != null && (
          <button type="button" onClick={() => void wake()} disabled={waking}
            className="btn-blue text-xs sm:text-sm px-4 py-1.5 shrink-0 disabled:opacity-50">
            {waking ? 'Пробуждение...' : 'Проснуться'}
          </button>
        )}
      </div>
    );
  }

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
