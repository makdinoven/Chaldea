import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { useBattleBar, type BattlePageBarProps } from "../../BattlePageBar/useBattleBar";
import TurnBanner from "./TurnBanner";
import ActionBar, { AutobattleControls } from "./ActionBar";
import Chronicle from "./Chronicle";

interface ArenaHudProps extends BattlePageBarProps {
  isSpectate: boolean;
  /** Renders the 3D scene; gets the moment of the latest critical hit for the dice. */
  renderArena: (critRollAt: number | null) => ReactNode;
  modeToggle: ReactNode;
  /** Pause / first-cycle / control / connection banners, shown under the turn banner. */
  notices: ReactNode;
}

// The table runs edge to edge under the HUD and stays solid top and bottom; at both ends
// it sinks into the same near-black, which then spills out past the arena and thins
// into the page — up behind the site header and down toward the footer, symmetrically.
const SHADOW_RGB = "5,4,7";
// Eased fall-off so the shadow never reads as a band with an edge on a bright background.
const SHADOW_STOPS = [
  [0.96, 0],
  [0.952, 10],
  [0.904, 20],
  [0.803, 30],
  [0.655, 40],
  [0.48, 50],
  [0.305, 60],
  [0.157, 70],
  [0.056, 80],
  [0.008, 90],
  [0.0, 100],
]
  .map(([a, at]) => `rgba(${SHADOW_RGB},${a}) ${at}%`)
  .join(", ");
const shadowSpill = (direction: "to top" | "to bottom"): CSSProperties => ({
  background: `linear-gradient(${direction}, ${SHADOW_STOPS})`,
});

/**
 * performance.now() of the last critical hit, read from the live turn's log. The turn
 * that is already on screen when the page opens never counts, so old crits don't replay.
 */
const useCriticalHitMoment = (bar: ReturnType<typeof useBattleBar>) => {
  const [at, setAt] = useState<number | null>(null);
  const lastSeenTurn = useRef<number | null>(null);
  const { turnLogs, activeTurnIndex, totalTurns } = bar;

  useEffect(() => {
    if (!turnLogs || activeTurnIndex !== totalTurns - 1) return;
    if (lastSeenTurn.current === null) {
      lastSeenTurn.current = activeTurnIndex;
      return;
    }
    if (activeTurnIndex <= lastSeenTurn.current) return;
    lastSeenTurn.current = activeTurnIndex;
    const crit = turnLogs.logs.some((log) =>
      log.events.some((e) => e.event === "damage" && e.critical && !e.dodged && !e.hit_chance_failed),
    );
    if (crit) setAt(performance.now());
  }, [turnLogs, activeTurnIndex, totalTurns]);

  return at;
};

// The full-bleed arena is exactly 100vw wide, which includes the scrollbar — clip
// the overflow on <html> while it is mounted so the page never scrolls sideways.
const useClipHorizontalOverflow = () => {
  useEffect(() => {
    const root = document.documentElement;
    const previous = root.style.overflowX;
    root.style.overflowX = "clip";
    return () => {
      root.style.overflowX = previous;
    };
  }, []);
};

const ArenaHud = ({ isSpectate, renderArena, modeToggle, notices, ...barProps }: ArenaHudProps) => {
  useClipHorizontalOverflow();
  const bar = useBattleBar(barProps);
  const [chronicleOpen, setChronicleOpen] = useState(false);
  const critRollAt = useCriticalHitMoment(bar);
  const { turn, runtimeData, isPaused } = barProps;

  const status = isPaused
    ? "paused"
    : isSpectate
      ? "spectate"
      : turn.isOpponentTurn
        ? "enemy"
        : "mine";

  const queue = bar.turnQueue.map((pid) => {
    const p = bar.participantById.get(pid);
    return { pid, name: p?.name, avatar: p?.avatar, side: bar.sideOf(pid) };
  });

  const autoProps = {
    bar,
    isAutoBattleOn: barProps.isAutoBattleOn,
    toggleAutobattle: barProps.toggleAutobattle,
    autobattleMode: barProps.autobattleMode,
    setAutobattleMode: barProps.setAutobattleMode,
  };

  return (
    <div className="relative ml-[calc(50%-50vw)] w-screen text-white">
      <div className="relative h-[56vh] min-h-[380px] lg:h-[calc(100vh-190px)] lg:min-h-[560px]">
        {/* The table of fates sits in a pool of darkness that thins out into the page. */}
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(ellipse_72%_78%_at_50%_42%,rgba(4,4,7,0.94)_0%,rgba(4,4,7,0.8)_50%,transparent_85%)] " />
        {/* Shadow spilling up past the arena, behind the site header */}
        <div className="pointer-events-none absolute inset-x-0 bottom-full h-48" style={shadowSpill("to top")} />
        <div className="absolute inset-0">{renderArena(critRollAt)}</div>
        {/* Both ends of the table sink into shadow instead of turning see-through */}
        <div
          className="pointer-events-none absolute inset-x-0 top-0 h-16"
          style={{ background: `linear-gradient(to top, transparent, rgba(${SHADOW_RGB},0.96))` }}
        />
        <div
          className="pointer-events-none absolute inset-x-0 bottom-0 h-16"
          style={{ background: `linear-gradient(to bottom, transparent, rgba(${SHADOW_RGB},0.96))` }}
        />

        <div className="absolute left-3 top-1 z-10 sm:left-6 sm:top-3">{modeToggle}</div>

        <div className="pointer-events-none absolute inset-x-0 top-9 flex flex-col items-center gap-2 px-3 sm:top-3 lg:inset-x-auto lg:bottom-4 lg:left-6 lg:top-14 lg:w-[260px] lg:items-stretch lg:px-0">
          <div className="pointer-events-auto max-w-full">
            <TurnBanner
              actorName={turn.currentCharacterParticipant.characterName}
              turnNumber={turn.turn_number + 1}
              endsAt={turn.endsAt}
              status={status}
              currentActor={runtimeData.current_actor}
              queue={queue}
            />
          </div>
          <div className="pointer-events-auto flex w-full max-w-md flex-col items-stretch [&>*]:!mb-0 [&>*]:!px-4 [&>*]:!py-1.5 [&>*]:shadow-card [&_p]:!text-xs sm:[&_p]:!text-sm [&>*+*]:mt-1.5">
            {notices}
          </div>
          {!isSpectate && (
            <div className="pointer-events-auto hidden lg:block">
              <ActionBar bar={bar} turnData={barProps.turnData} onPassTurn={barProps.setTurn} layout="column" {...autoProps} />
            </div>
          )}
        </div>

        <div className="absolute bottom-6 right-6 top-6 hidden w-[320px] flex-col lg:flex xl:w-[360px]">
          <Chronicle bar={bar} className="max-h-full" />
        </div>

      </div>

      {/* The table's shadow spills below the arena and thins out into the page and footer */}
      <div className="pointer-events-none h-24 lg:h-48" style={shadowSpill("to bottom")} />

      {/* Phone / tablet: controls pinned to the bottom of the screen */}
      <div className="h-[170px] lg:hidden" />
      <div className="fixed inset-x-0 bottom-0 z-40 border-t border-gold-dark/30 bg-[linear-gradient(180deg,rgba(20,16,12,0.92),rgba(8,8,10,0.97))] px-2 pb-[max(8px,env(safe-area-inset-bottom))] pt-2 lg:hidden">
        {!isSpectate && (
          <ActionBar bar={bar} turnData={barProps.turnData} onPassTurn={barProps.setTurn} layout="compact" {...autoProps} />
        )}
        <div className="mt-2 flex items-center justify-between gap-2">
          {!isSpectate ? <AutobattleControls {...autoProps} dense /> : <span />}
          <button
            type="button"
            onClick={() => setChronicleOpen(true)}
            className="chip-outline shrink-0 rounded-full px-2.5 py-1 text-[10px] uppercase tracking-wide"
          >
            Летопись
          </button>
        </div>
      </div>

      {chronicleOpen && (
        <div className="fixed inset-0 z-50 flex flex-col justify-end lg:hidden">
          <button
            type="button"
            aria-label="Закрыть летопись"
            onClick={() => setChronicleOpen(false)}
            className="absolute inset-0 bg-black/75 backdrop-blur-md"
          />
          <div className="relative h-[72vh] animate-fade-in px-2 pb-2">
            <button
              type="button"
              onClick={() => setChronicleOpen(false)}
              className="absolute right-5 top-3 z-10 text-lg leading-none text-white/60 hover:text-white"
              aria-label="Закрыть"
            >
              ×
            </button>
            <Chronicle bar={bar} className="h-full" />
          </div>
        </div>
      )}

      {bar.renderPicker()}
    </div>
  );
};

export default ArenaHud;
