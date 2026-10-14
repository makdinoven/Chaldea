import CountdownTimer from "../../BattlePageBar/CountdownTimer/CountdownTimer";
import AvatarCircle from "../../BattlePageBar/AvatarCircle";
import HudFrame from "./HudFrame";

interface QueueEntry {
  pid: number;
  name?: string;
  avatar?: string | null;
  side: "ally" | "enemy";
}

interface TurnBannerProps {
  actorName: string;
  turnNumber: number;
  endsAt: number;
  status: "mine" | "enemy" | "spectate" | "paused";
  currentActor: number;
  queue: QueueEntry[];
}

const STATUS = {
  mine: { text: "Ваш ход", className: "text-site-blue" },
  enemy: { text: "Ход противника", className: "text-site-red/90" },
  spectate: { text: "Наблюдение", className: "text-white/60" },
  paused: { text: "Бой приостановлен", className: "text-gold" },
} as const;

const HourglassIcon = () => (
  <svg viewBox="0 0 16 20" className="h-3.5 w-3 fill-none stroke-gold-dark" strokeWidth="1.4" aria-hidden>
    <path d="M2 1h12M2 19h12M3 1c0 5 10 5 10 9s-10 4-10 9M13 1c0 5-10 5-10 9s10 4 10 9" />
  </svg>
);

const TurnBanner = ({ actorName, turnNumber, endsAt, status, currentActor, queue }: TurnBannerProps) => (
  <HudFrame className="px-4 py-1.5 text-center sm:min-w-[260px] sm:px-7 sm:py-3">
    <div className="hidden items-center justify-center gap-2.5 text-[10px] uppercase tracking-[0.25em] text-gold-dark sm:flex sm:text-xs">
      <span className="h-px w-6 bg-gradient-to-r from-transparent to-gold-dark sm:w-10" />
      Ход {turnNumber}
      <span className="h-px w-6 bg-gradient-to-l from-transparent to-gold-dark sm:w-10" />
    </div>
    <p className="gold-text truncate text-sm font-medium uppercase leading-tight sm:mt-0.5 sm:text-2xl">
      {actorName}
    </p>
    <div className="mt-0.5 flex items-center justify-center gap-3 text-[11px] uppercase tracking-wide sm:text-xs">
      <span className={STATUS[status].className}>{STATUS[status].text}</span>
      <span className="h-3 w-px bg-white/20" />
      <span className="flex items-center gap-1.5 tabular-nums normal-case text-white/85 [&_span]:!text-[13px] sm:[&_span]:!text-[15px]">
        <HourglassIcon />
        <CountdownTimer startMilliseconds={endsAt} />
      </span>
    </div>
    {queue.length > 1 && (
      <div className="mt-2 hidden items-center justify-center gap-1 sm:flex">
        {queue.map((q, i) => (
          <div key={`${q.pid}-${i}`} className="flex items-center gap-1">
            <AvatarCircle
              avatar={q.avatar}
              name={q.name}
              size={q.pid === currentActor ? 30 : 24}
              active={q.pid === currentActor}
              side={q.side}
              title={q.name}
            />
            {i < queue.length - 1 && <span className="text-[10px] text-gold-dark/60">›</span>}
          </div>
        ))}
      </div>
    )}
  </HudFrame>
);

export default TurnBanner;
