/**
 * GatheringLockBanner (FEAT-128).
 *
 * Top-of-page banner shown while the supplied character has an in-flight
 * resource-gathering session. Mirrors the visual language of
 * `BattleLockBanner` (Tailwind only, gold-outline + warning icon) and adds:
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
      className="gold-outline rounded-card p-3 sm:p-4 bg-yellow-900/20 flex flex-col gap-2"
    >
      <div className="flex items-center gap-3 flex-wrap">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="w-5 h-5 sm:w-6 sm:h-6 text-gold shrink-0"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
          aria-hidden="true"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4.5c-.77-.833-2.694-.833-3.464 0L3.34 16.5c-.77.833.192 2.5 1.732 2.5z"
          />
        </svg>

        <span className="gold-text text-sm sm:text-base font-medium flex-1 min-w-0 break-words">
          {`Идёт добыча: осталось ${formatMmSs(remainingSeconds)}`}
        </span>

        <button
          type="button"
          onClick={handleCancel}
          disabled={isCancelling}
          className="btn-line text-xs sm:text-sm px-3 py-1.5 shrink-0 disabled:opacity-50 disabled:cursor-not-allowed"
          aria-label="Отменить добычу"
        >
          {isCancelling ? 'Отмена…' : 'Отменить'}
        </button>
      </div>

      {cancelError && (
        <div
          role="alert"
          className="text-xs sm:text-sm text-red-400 break-words"
        >
          {cancelError}
        </div>
      )}
    </div>
  );
};

export default GatheringLockBanner;
