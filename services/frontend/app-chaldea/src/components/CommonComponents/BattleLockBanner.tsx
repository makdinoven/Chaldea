import { useNavigate } from 'react-router-dom';
import type { BattlePreview, BattlePreviewParticipant } from '../../api/battles';

interface BattleLockBannerProps {
  message: string;
  /** Bold headline above `message`. Omitted → `message` is the headline. */
  title?: string;
  /** Active battle id (from `useBattleLock`) — enables «Вернуться к бою». */
  battleId?: number | null;
  /** Battle preview (from `useBattlePreview`) — enables opponent/round info. */
  preview?: BattlePreview | null;
  /** Viewer's character id — resolves «ваш ход» vs «ход противника». */
  currentCharacterId?: number | null;
  /** Route fallback when the preview (and its location_id) is unavailable. */
  fallbackLocationId?: number | null;
}

interface TurnInfo {
  opponent: BattlePreviewParticipant | null;
  extraEnemies: number;
  turnLine: string | null;
}

const resolveTurnInfo = (
  preview: BattlePreview | null | undefined,
  currentCharacterId: number | null | undefined,
): TurnInfo => {
  if (!preview) return { opponent: null, extraEnemies: 0, turnLine: null };

  const aliveEnemies = preview.participants.filter(
    (p) => !p.is_ally && p.is_alive,
  );
  const opponent = aliveEnemies[0] ?? null;
  const extraEnemies = Math.max(0, aliveEnemies.length - 1);

  let turnLine: string | null = null;
  const currentEntry = preview.turn_order.find((t) => t.is_current);
  if (currentEntry) {
    const actor = preview.participants.find(
      (p) => p.participant_id === currentEntry.participant_id,
    );
    const isMyTurn =
      actor?.character_id != null &&
      currentCharacterId != null &&
      actor.character_id === currentCharacterId;
    turnLine = `Раунд ${preview.turn_number} · ${isMyTurn ? 'ваш ход' : 'ход противника'}`;
  } else {
    turnLine = `Раунд ${preview.turn_number}`;
  }

  return { opponent, extraEnemies, turnLine };
};

/**
 * In-battle lock banner (FEAT-152 A4, mock style). With only `message` it
 * renders the generic variant (used e.g. by the inventory tab). On the
 * location page it additionally shows the opponent mini-card, the round /
 * whose-turn line (from the battle preview) and a «Вернуться к бою» button;
 * when the preview fails, it gracefully degrades to the generic variant
 * while keeping the return button.
 */
const BattleLockBanner = ({
  message,
  title,
  battleId,
  preview,
  currentCharacterId,
  fallbackLocationId,
}: BattleLockBannerProps) => {
  const navigate = useNavigate();

  const { opponent, extraEnemies, turnLine } = resolveTurnInfo(
    preview,
    currentCharacterId,
  );

  const returnLocationId = preview?.location_id ?? fallbackLocationId ?? null;
  const canReturn = battleId != null && returnLocationId != null;

  return (
    <div
      role="status"
      className="rounded-card border border-site-red/45 bg-gradient-to-r from-site-red/25 to-site-red/5 p-3.5 sm:p-4 flex items-center gap-3 sm:gap-4 flex-wrap"
    >
      {/* Pulsing swords icon */}
      <span className="w-10 h-10 sm:w-11 sm:h-11 shrink-0 flex items-center justify-center rounded-card bg-site-red text-white animate-pulse">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="w-5 h-5 sm:w-6 sm:h-6"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
          aria-hidden="true"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M14.5 17.5L3 6V3h3l11.5 11.5" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M13 19l6-6" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M16 16l4 4" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 21l2-2" />
        </svg>
      </span>

      {/* Text */}
      <div className="flex flex-col gap-0.5 flex-1 min-w-[180px]">
        {title ? (
          <>
            <span className="text-white text-sm sm:text-[15px] font-medium">{title}</span>
            <span className="text-white/70 text-xs sm:text-[12.5px]">{message}</span>
          </>
        ) : (
          <span className="text-white text-sm sm:text-[15px] font-medium">{message}</span>
        )}
      </div>

      {/* Opponent mini-card (hidden when preview unavailable — graceful fallback) */}
      {opponent && (
        <div className="flex items-center gap-2.5 px-3 py-2 rounded-card bg-site-bg border border-site-red/30">
          <span className="w-8 h-8 sm:w-9 sm:h-9 shrink-0 rounded-card overflow-hidden bg-black/60 flex items-center justify-center">
            {opponent.avatar ? (
              <img
                src={opponent.avatar}
                alt={opponent.name}
                className="w-full h-full object-cover"
              />
            ) : (
              <span className="text-site-red text-sm font-medium">
                {opponent.name.charAt(0).toUpperCase()}
              </span>
            )}
          </span>
          <div className="flex flex-col gap-0.5 min-w-0">
            <span className="text-white text-xs sm:text-[12.5px] font-medium truncate">
              {opponent.name}
              {extraEnemies > 0 && (
                <span className="text-white/50 font-normal"> и ещё {extraEnemies}</span>
              )}
            </span>
            {turnLine && (
              <span className="text-white/50 text-[10px] sm:text-[11px]">{turnLine}</span>
            )}
          </div>
        </div>
      )}

      {/* Return to battle */}
      {canReturn && (
        <button
          type="button"
          onClick={() => navigate(`/location/${returnLocationId}/battle/${battleId}`)}
          className="flex items-center justify-center gap-2 shrink-0 w-full sm:w-auto px-5 py-2.5 rounded-card bg-site-red text-white text-sm font-medium hover:brightness-110 transition-all duration-200 ease-site"
        >
          Вернуться к бою
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="w-4 h-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2.4}
            aria-hidden="true"
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M5 12h14m-7-7l7 7-7 7" />
          </svg>
        </button>
      )}
    </div>
  );
};

export default BattleLockBanner;
