/**
 * GatheringLockBanner (FEAT-128, restyled in FEAT-152).
 *
 * Top-of-page banner shown while the supplied character has an in-flight
 * resource-gathering session. Shares the visual language of the redesigned
 * `BattleLockBanner` (icon block + title/subtitle + action button) with a
 * green (stat-energy) accent, and keeps:
 *
 *  - a live MM:SS countdown driven by the client-side ticker in
 *    `useGatheringLock`
 *  - an "Отменить" button that dispatches the `cancelGathering` thunk
 *  - inline display of any cancel error in Russian (per CLAUDE.md
 *    "Frontend Error Display")
 *
 * Per CLAUDE.md: TypeScript strict, no `React.FC`, mobile-responsive
 * (works at 360px width).
 */
import { useState } from 'react';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  cancelGathering,
  selectActiveSession,
  selectGatheringIsCancelling,
} from '../../redux/slices/gatheringSlice';
import useGatheringLock from '../../hooks/useGatheringLock';

interface GatheringLockBannerProps {
  characterId: number;
}

const formatMmSs = (totalSeconds: number): string => {
  const safe = Math.max(0, Math.floor(totalSeconds));
  const minutes = Math.floor(safe / 60);
  const seconds = safe % 60;
  const mm = String(minutes).padStart(2, '0');
  const ss = String(seconds).padStart(2, '0');
  return `${mm}:${ss}`;
};

const GatheringLockBanner = ({ characterId }: GatheringLockBannerProps) => {
  const dispatch = useAppDispatch();
  const { isGathering, remainingSeconds, locationId } =
    useGatheringLock(characterId);
  // We need the node id for the cancel route — pull it directly from the
  // active session in Redux (the hook only exposes locationId for now).
  const activeSession = useAppSelector(selectActiveSession);
  const isCancelling = useAppSelector(selectGatheringIsCancelling);
  const [cancelError, setCancelError] = useState<string | null>(null);

  if (!isGathering || !activeSession || !locationId) {
    return null;
  }

  const handleCancel = async (): Promise<void> => {
    setCancelError(null);
    const result = await dispatch(
      cancelGathering({
        locationId,
        nodeId: activeSession.node_id,
        characterId,
      }),
    );
    if (cancelGathering.rejected.match(result)) {
      setCancelError(
        result.payload ?? 'Не удалось отменить добычу. Попробуйте ещё раз.',
      );
    }
  };

  return (
    <div
      role="status"
      aria-live="polite"
      className="rounded-card border border-stat-energy/40 bg-gradient-to-r from-stat-energy/20 to-stat-energy/5 p-3.5 sm:p-4 flex flex-col gap-2"
    >
      <div className="flex items-center gap-3 sm:gap-4 flex-wrap">
        {/* Pulsing pickaxe-style icon block */}
        <span className="w-10 h-10 sm:w-11 sm:h-11 shrink-0 flex items-center justify-center rounded-card bg-stat-energy/80 text-white animate-pulse">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="w-5 h-5 sm:w-6 sm:h-6"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
            aria-hidden="true"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        </span>

        <div className="flex flex-col gap-0.5 flex-1 min-w-[180px]">
          <span className="text-white text-sm sm:text-[15px] font-medium">
            Идёт добыча ресурсов
          </span>
          <span className="text-white/70 text-xs sm:text-[12.5px]">
            {`Осталось ${formatMmSs(remainingSeconds)} — до завершения действия заблокированы.`}
          </span>
        </div>

        <button
          type="button"
          onClick={handleCancel}
          disabled={isCancelling}
          className="btn-line text-xs sm:text-sm px-4 py-2 shrink-0 w-full sm:w-auto disabled:opacity-50 disabled:cursor-not-allowed"
          aria-label="Отменить добычу"
        >
          {isCancelling ? 'Отмена…' : 'Отменить'}
        </button>
      </div>

      {cancelError && (
        <div
          role="alert"
          className="text-xs sm:text-sm text-site-red break-words"
        >
          {cancelError}
        </div>
      )}
    </div>
  );
};

export default GatheringLockBanner;
