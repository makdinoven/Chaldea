import { useEffect, useRef } from "react";
import AvatarCircle from "../../BattlePageBar/AvatarCircle";
import type { BattleBarState } from "../../BattlePageBar/useBattleBar";
import HudFrame from "./HudFrame";

interface ChronicleProps {
  bar: BattleBarState;
  className?: string;
}

/** "Летопись боя": turn history strip plus the log of the selected turn. */
const Chronicle = ({ bar, className = "" }: ChronicleProps) => {
  const historyRef = useRef<HTMLDivElement>(null);
  const following = !bar.showJumpToLatest;

  useEffect(() => {
    const el = historyRef.current;
    if (el && following) el.scrollLeft = el.scrollWidth;
  }, [bar.totalTurns, following]);

  const turnNo = bar.activeTurnIndex + 1;

  return (
    <HudFrame className={`flex min-h-0 flex-col ${className}`} innerClassName="flex min-h-0 flex-1 flex-col">
      <div className="flex min-h-0 flex-1 flex-col gap-3 px-4 py-4">
        <div className="flex items-center gap-2">
          <span className="h-px flex-1 bg-gradient-to-r from-transparent to-gold-dark/70" />
          <h3 className="gold-text text-sm font-medium uppercase tracking-[0.2em]">Летопись боя</h3>
          <span className="h-px flex-1 bg-gradient-to-l from-transparent to-gold-dark/70" />
        </div>

        {bar.totalTurns > 0 && (
          <div
            ref={historyRef}
            className="gold-scrollbar flex shrink-0 gap-2 overflow-x-auto px-1 pb-2 pt-1"
          >
            {Array.from({ length: bar.totalTurns }, (_, idx) => {
              const pid = bar.actorOfTurn(idx);
              const p = pid != null ? bar.participantById.get(pid) : undefined;
              return (
                <AvatarCircle
                  key={idx}
                  avatar={p?.avatar}
                  name={p?.name}
                  size={30}
                  badge={idx + 1}
                  active={idx === bar.activeTurnIndex}
                  side={pid != null ? bar.sideOf(pid) : undefined}
                  onClick={() => bar.selectTurn(idx)}
                  title={`Ход ${idx + 1}${p?.name ? ` · ${p.name}` : ""}`}
                />
              );
            })}
          </div>
        )}

        <div className="flex items-baseline justify-between gap-2 border-b border-gold-dark/25 pb-1.5">
          <p className="text-xs uppercase tracking-wide text-white/70">
            {turnNo > 0 ? (
              <>
                Ход {turnNo}
                {bar.activeTurnActorName && (
                  <span className="gold-text ml-1.5 normal-case">· {bar.activeTurnActorName}</span>
                )}
              </>
            ) : (
              "Бой только начался"
            )}
          </p>
          {bar.showJumpToLatest && (
            <button
              type="button"
              onClick={bar.jumpToLatest}
              className="shrink-0 text-[11px] text-site-blue transition-colors duration-200 hover:text-gold"
            >
              К последнему
            </button>
          )}
        </div>

        <ul className="gold-scrollbar -mr-2 flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-2">
          {bar.turnLogs?.logs.map((log, index) => (
            <li key={`${bar.activeTurnIndex}-${index}`} className="flex animate-fade-in flex-col gap-1.5 text-xs leading-relaxed text-[#e8dcc8]">
              {log.events.map((event, i) => {
                const line = bar.formatBattleEvent(event);
                if (!line) return null;
                return (
                  <div key={i} className="flex gap-2">
                    <span className="mt-[7px] h-1 w-1 shrink-0 rotate-45 bg-gold-dark/70" />
                    <div className="min-w-0 flex-1">{line}</div>
                  </div>
                );
              })}
              <div className="mt-1 flex items-center justify-between text-[10px] text-white/40">
                {bar.isOwnAutobattleTurn ? <span className="gold-text uppercase">Автобой</span> : <span />}
                <span>{bar.formatLogTime(log.timestamp)}</span>
              </div>
              {bar.isTurnLikeTextShown && bar.isOwnAutobattleTurn && (
                <p className="text-[11px] text-white/70">
                  Понравился ли вам ход?{" "}
                  <button type="button" onClick={() => bar.rateTurn(log, true)} className="font-medium text-site-blue underline">
                    Да
                  </button>{" "}
                  <button type="button" onClick={() => bar.rateTurn(log, false)} className="font-medium text-site-red underline">
                    Нет
                  </button>
                </p>
              )}
            </li>
          ))}
          {bar.turnLogs && bar.turnLogs.logs.length === 0 && (
            <li className="text-xs text-white/40">Записей пока нет</li>
          )}
        </ul>
      </div>
    </HudFrame>
  );
};

export default Chronicle;
