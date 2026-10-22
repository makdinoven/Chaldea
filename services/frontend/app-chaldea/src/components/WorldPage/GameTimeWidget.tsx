import { useEffect, useState } from 'react';
import {
  Droplet,
  Sun,
  Wind,
  CloudSnow,
  Zap,
  Award,
  Moon,
  Star,
} from 'react-feather';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { selectGameTimePublic } from '../../redux/slices/gameTimeSlice';
import { fetchGameTime } from '../../redux/actions/gameTimeActions';
import {
  computeGameTime,
  SEGMENT_LABELS,
  GameTimeResult,
} from '../../utils/gameTime';
import { serverDateMs } from '../../utils/serverDate';

const ICON_MAP: Record<string, typeof Sun> = {
  spring: Droplet,
  summer: Sun,
  autumn: Wind,
  winter: CloudSnow,
  beltane: Zap,
  lughnasad: Award,
  samhain: Moon,
  imbolc: Star,
};

const REFRESH_INTERVAL_MS = 60_000;

interface GameTimeWidgetProps {
  /** One line with no rule under it, for a toolbar; otherwise a block for a side panel. */
  inline?: boolean;
}

const GameTimeWidget = ({ inline = false }: GameTimeWidgetProps) => {
  const dispatch = useAppDispatch();
  const { epoch, offsetDays, serverTime, loading, error } =
    useAppSelector(selectGameTimePublic);

  const [gameTime, setGameTime] = useState<GameTimeResult | null>(null);

  // Fetch game time config on mount
  useEffect(() => {
    dispatch(fetchGameTime());
  }, [dispatch]);

  // Compute game time from fetched data, re-compute every 60s
  useEffect(() => {
    if (!epoch || !serverTime) return;

    // FEAT-161: the tick and the first render must share one reference frame.
    // Previously the first render used the raw `server_time` while every tick
    // used `new Date().toISOString()` — the server's clock vs. the browser's —
    // so the displayed in-game day could jump a minute after load. We now
    // advance the *server* instant by the real time elapsed since we received
    // it, which makes the tick at elapsed = 0 identical to the first render
    // and immune to any client/server clock skew.
    const serverBaseMs = serverDateMs(serverTime);
    const receivedAtMs = Date.now();

    const compute = () => {
      const elapsedMs = Date.now() - receivedAtMs;
      const reference = new Date(serverBaseMs + elapsedMs).toISOString();
      setGameTime(computeGameTime(epoch, offsetDays, reference));
    };

    compute();

    const interval = setInterval(compute, REFRESH_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [epoch, offsetDays, serverTime]);

  if (loading) {
    if (inline) return <div className="h-4 w-40 rounded bg-white/10 animate-pulse" />;
    return (
      <div className="border-b border-white/10 pb-3 mb-3">
        <div className="flex items-center gap-2">
          <div className="w-[18px] h-[18px] rounded-full bg-white/10 animate-pulse" />
          <div className="h-4 w-20 rounded bg-white/10 animate-pulse" />
        </div>
        <div className="h-3 w-32 rounded bg-white/10 animate-pulse mt-1.5" />
      </div>
    );
  }

  if (error || !gameTime) {
    return null;
  }

  const Icon = ICON_MAP[gameTime.segmentName] || Sun;
  const label = SEGMENT_LABELS[gameTime.segmentName] || gameTime.segmentName;
  const when = gameTime.isTransition
    ? `${gameTime.year}-й год`
    : `${gameTime.week}-я неделя, ${gameTime.year}-й год`;

  if (inline) {
    return (
      <div className="flex items-center gap-2 min-w-0 text-sm">
        <Icon size={16} className="text-gold shrink-0" />
        <span className="gold-text font-medium shrink-0">{label}</span>
        <span className="text-white/60 truncate">{when}</span>
      </div>
    );
  }

  return (
    <div className="border-b border-white/10 pb-3 mb-3">
      <div className="flex items-center gap-2">
        <Icon size={18} className="text-gold shrink-0" />
        <span className="gold-text text-base font-medium">{label}</span>
      </div>
      <p className="text-white/60 text-sm mt-0.5 ml-[26px]">{when}</p>
    </div>
  );
};

export default GameTimeWidget;
