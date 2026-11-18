import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { motion } from 'motion/react';
import { fetchCaravansHere, startCaravanRaid } from '../../../api/caravans';
import { inspectCaravan } from '../../../api/customs';
import { apiErrorMessage } from '../../../api/errors';
import { getMyParty, type Party } from '../../../api/squads';
import type { CaravanHere, CaravanHereState } from '../../../types/caravans';
import { battlePath } from '../../../utils/battlePath';

/**
 * FEAT-211 — «Торговый караван» block of the location page (feature file 3.17).
 *
 * Shows ONLY the goods group and the guard count of a physical caravan standing
 * here: origin, destination, route and value are never sent by the server and
 * never shown — players learn the roads themselves.
 */

interface CaravanSectionProps {
  locationId: number;
  /** The character, only when he stands in this location (else nothing is loaded). */
  characterId: number | null;
  /** Caravan ids the character holds an open «Налёт на караван» gate for. */
  gatedCaravanIds?: number[];
  /** The character is busy (battle, gathering, activity lock) — the block is dimmed and inert. */
  locked?: boolean;
  /** Reports the caravans here — the page offers them as post-gate targets. */
  onCaravansChange?: (caravans: CaravanHere[]) => void;
  /** Called after a failed raid attempt (the gate may have been consumed or expired). */
  onGatesStale?: () => void;
}

/** Reload period of the block — the caravan moves on every ~15–20 min. */
const POLL_MS = 60_000;
/** Countdown refresh — the text is in whole minutes. */
const TICK_MS = 15_000;
const SECONDS_PER_MINUTE = 60;

const STATE_LINE: Partial<Record<CaravanHereState, { text: string; cls: string }>> = {
  held: { text: 'Стоит в ожидании', cls: 'text-gold/90' },
  under_attack: { text: 'Идёт бой', cls: 'text-orange-300' },
  raided: { text: 'Уже ограблен', cls: 'text-white/50' },
};

/** FEAT-216: a legal caravan standing at the customs post (pays the duty and waits). */
const INSPECTION_CLS = 'text-gold/90';

/** FEAT-215: a caravan waiting for a ship / in a ship's hold has no road countdown. */
const SEA_LINE: Record<string, { text: string; cls: string }> = {
  waiting: { text: 'Ждёт корабль', cls: 'text-site-blue' },
  aboard: { text: 'В трюме корабля', cls: 'text-site-blue' },
};

const Spinner = () => <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />;

const WagonIcon = ({ className }: { className: string }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    className={className}
    fill="none"
    viewBox="0 0 24 24"
    stroke="currentColor"
    strokeWidth={2}
    aria-hidden
  >
    <path strokeLinecap="round" strokeLinejoin="round" d="M3 6h13v9H3zM16 9h3l2 3v3h-5" />
    <circle cx="7" cy="17.5" r="1.8" />
    <circle cx="17.5" cy="17.5" r="1.8" />
  </svg>
);

/** «Уйдёт примерно через N мин» from the seconds the server gave at `fetchedAt`. */
const departText = (sec: number | null, fetchedAt: number, now: number): string | null => {
  if (sec === null || sec === undefined) return null;
  const left = sec - Math.floor((now - fetchedAt) / 1000);
  if (left <= SECONDS_PER_MINUTE) return 'Вот-вот тронется в путь';
  return `Уйдёт примерно через ${Math.ceil(left / SECONDS_PER_MINUTE)} мин`;
};

/** Seconds left of a server countdown given at `fetchedAt`; null when the server sent none. */
const secondsLeft = (sec: number | null | undefined, fetchedAt: number, now: number): number | null => {
  if (sec === null || sec === undefined) return null;
  return Math.max(0, sec - Math.floor((now - fetchedAt) / 1000));
};

/** «На досмотре · ещё ~N мин» — the legal caravan's stop at the customs post. */
const inspectionText = (sec: number | null, fetchedAt: number, now: number): string => {
  const left = secondsLeft(sec, fetchedAt, now);
  if (left === null) return 'На досмотре';
  if (left <= SECONDS_PER_MINUTE) return 'На досмотре — вот-вот отпустят';
  return `На досмотре — ещё ~${Math.ceil(left / SECONDS_PER_MINUTE)} мин`;
};

const CaravanSection = ({
  locationId,
  characterId,
  gatedCaravanIds = [],
  locked = false,
  onCaravansChange,
  onGatesStale,
}: CaravanSectionProps) => {
  const navigate = useNavigate();
  const [caravans, setCaravans] = useState<CaravanHere[]>([]);
  const [fetchedAt, setFetchedAt] = useState(() => Date.now());
  const [now, setNow] = useState(() => Date.now());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [party, setParty] = useState<Party | null>(null);
  const [attackingId, setAttackingId] = useState<number | null>(null);
  const [choosingId, setChoosingId] = useState<number | null>(null);
  /** FEAT-216: «Досмотреть» solo / with the group. */
  const [inspectChoosingId, setInspectChoosingId] = useState<number | null>(null);
  const [inspectingId, setInspectingId] = useState<number | null>(null);
  /** Toast only on the first load failure; the inline message stays after that. */
  const toastedRef = useRef(false);
  const reportRef = useRef(onCaravansChange);
  reportRef.current = onCaravansChange;

  const load = useCallback(async () => {
    if (!characterId) {
      setCaravans([]);
      setError(null);
      reportRef.current?.([]);
      return;
    }
    setLoading(true);
    try {
      const res = await fetchCaravansHere(characterId);
      // The server answers for the character's own location — ignore a stale answer for another page.
      const list = res.location_id === locationId ? res.caravans : [];
      setCaravans(list);
      setFetchedAt(Date.now());
      setError(null);
      toastedRef.current = false;
      reportRef.current?.(list);
    } catch (err) {
      const msg = apiErrorMessage(err, 'Не удалось загрузить караваны');
      setError(msg);
      if (!toastedRef.current) {
        toastedRef.current = true;
        toast.error(msg);
      }
    } finally {
      setLoading(false);
    }
  }, [characterId, locationId]);

  useEffect(() => {
    void load();
    if (!characterId) return undefined;
    const id = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(id);
  }, [load, characterId]);

  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), TICK_MS);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    if (!characterId) {
      setParty(null);
      return;
    }
    getMyParty(characterId)
      .then(setParty)
      .catch(() => setParty(null));
  }, [characterId]);

  // Same group rule as the mob attack: any co-located accepted squadmate.
  const canGroup =
    !!party &&
    party.members.some(
      (m) => m.status === 'accepted' && m.character_id !== characterId && m.current_location_id === locationId,
    );

  const attack = async (caravan: CaravanHere, group: boolean) => {
    if (!characterId) {
      toast.error('Выберите персонажа, чтобы напасть');
      return;
    }
    setChoosingId(null);
    setAttackingId(caravan.id);
    try {
      const res = await startCaravanRaid(caravan.id, { character_id: characterId, group });
      toast.success(group ? 'Налёт группой начинается!' : 'Налёт начинается!');
      navigate(battlePath(locationId, res.battle_id));
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Не удалось напасть на караван'));
      void load();
      onGatesStale?.();
    } finally {
      setAttackingId(null);
    }
  };

  const inspect = async (caravan: CaravanHere, group: boolean) => {
    if (!characterId) {
      toast.error('Выберите персонажа, чтобы досмотреть караван');
      return;
    }
    setInspectChoosingId(null);
    setInspectingId(caravan.id);
    try {
      const res = await inspectCaravan(caravan.id, { character_id: characterId, group });
      toast.success(group ? 'Досмотр группой начинается!' : 'Досмотр начинается!');
      navigate(battlePath(locationId, res.battle_id));
    } catch (err) {
      toast.error(apiErrorMessage(err, 'Не удалось начать досмотр каравана'));
      void load();
    } finally {
      setInspectingId(null);
    }
  };

  if (!characterId || (caravans.length === 0 && !error)) return null;

  /** FEAT-216 C5: only the alerted customs officer sees this, while his alert window is open. */
  const renderInspect = (c: CaravanHere) => {
    const left = secondsLeft(c.inspect_in_sec, fetchedAt, now);
    if (!c.can_inspect || (left !== null && left <= 0)) return null;
    const busy = inspectingId === c.id;
    const timer =
      left !== null ? (
        <span className="text-gold/80 text-[11px]">
          {left <= SECONDS_PER_MINUTE
            ? 'Караван вот-вот уйдёт'
            : `Ещё ~${Math.ceil(left / SECONDS_PER_MINUTE)} мин, чтобы досмотреть`}
        </span>
      ) : null;
    if (inspectChoosingId === c.id && !busy) {
      return (
        <div className="flex flex-col gap-1">
          <div className="flex flex-col sm:flex-row gap-2">
            <button type="button" onClick={() => void inspect(c, true)} className="btn-blue !text-xs !px-4 !py-2">
              Досмотреть с группой
            </button>
            <button
              type="button"
              onClick={() => void inspect(c, false)}
              className="px-4 py-2 rounded-[9px] border border-white/20 text-white/70 text-xs hover:bg-white/5 transition-colors duration-200"
            >
              Досмотреть одному
            </button>
            <button
              type="button"
              onClick={() => setInspectChoosingId(null)}
              className="px-3 py-2 text-white/50 text-xs hover:text-white transition-colors duration-200"
            >
              Отмена
            </button>
          </div>
          {timer}
        </div>
      );
    }
    return (
      <div className="flex flex-col gap-1">
        <button
          type="button"
          onClick={() => (canGroup ? setInspectChoosingId(c.id) : void inspect(c, false))}
          disabled={busy || inspectingId !== null || attackingId !== null}
          className="w-full sm:w-auto min-w-[140px] px-5 py-2 rounded-[9px] border border-gold/60 bg-gold/10 text-gold text-xs font-medium uppercase tracking-[0.04em] hover:bg-gold/20 transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center"
        >
          {busy ? <Spinner /> : 'Досмотреть'}
        </button>
        {timer}
      </div>
    );
  };

  const renderActions = (c: CaravanHere) => {
    if (!c.can_attack) {
      return c.reason ? <p className="text-white/45 text-xs leading-snug">{c.reason}</p> : null;
    }
    if (!gatedCaravanIds.includes(c.id)) {
      return (
        <div className="flex flex-col gap-1">
          <button
            type="button"
            disabled
            className="w-full sm:w-auto px-5 py-2 rounded-[9px] bg-site-red/90 text-white text-xs font-medium uppercase tracking-[0.04em] opacity-40 cursor-not-allowed"
          >
            Напасть
          </button>
          <span className="text-white/45 text-[11px]">Нужен боевой пост «Налёт на караван»</span>
        </div>
      );
    }
    const busy = attackingId === c.id;
    if (choosingId === c.id && !busy) {
      return (
        <div className="flex flex-col sm:flex-row gap-2">
          <button type="button" onClick={() => void attack(c, true)} className="btn-blue !text-xs !px-4 !py-2">
            Напасть группой
          </button>
          <button
            type="button"
            onClick={() => void attack(c, false)}
            className="px-4 py-2 rounded-[9px] border border-white/20 text-white/70 text-xs hover:bg-white/5 transition-colors duration-200"
          >
            Напасть одному
          </button>
          <button
            type="button"
            onClick={() => setChoosingId(null)}
            className="px-3 py-2 text-white/50 text-xs hover:text-white transition-colors duration-200"
          >
            Отмена
          </button>
        </div>
      );
    }
    return (
      <button
        type="button"
        onClick={() => (canGroup ? setChoosingId(c.id) : void attack(c, false))}
        disabled={busy || attackingId !== null}
        className="w-full sm:w-auto min-w-[140px] px-5 py-2 rounded-[9px] bg-site-red/90 text-white text-xs font-medium uppercase tracking-[0.04em] hover:brightness-110 transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center"
      >
        {busy ? <Spinner /> : 'Напасть'}
      </button>
    );
  };

  return (
    <section
      className={`bg-site-bg backdrop-blur-sm rounded-card border border-gold/20 shadow-card overflow-hidden ${
        locked ? 'pointer-events-none opacity-50' : ''
      }`}
    >
      <div className="flex items-center gap-2.5 px-4 sm:px-5 py-3.5 border-b border-white/[0.07]">
        <WagonIcon className="w-[18px] h-[18px] text-gold shrink-0" />
        <h2 className="gold-text text-[13px] font-medium uppercase tracking-[0.08em]">Торговые караваны</h2>
        {caravans.length > 0 && (
          <span className="bg-gold/20 text-gold text-[10px] font-bold px-2 py-0.5 rounded-full min-w-[20px] text-center">
            {caravans.length}
          </span>
        )}
        {loading && <div className="w-4 h-4 border-2 border-white/30 border-t-gold rounded-full animate-spin ml-auto" />}
      </div>

      {error && caravans.length === 0 ? (
        <div className="flex flex-col items-start gap-3 p-4 sm:p-5">
          <p className="text-site-red text-sm">{error}</p>
          <button type="button" onClick={() => void load()} className="btn-blue text-sm px-4 py-2">
            Повторить
          </button>
        </div>
      ) : (
        <motion.ul
          initial="hidden"
          animate="visible"
          variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.05 } } }}
          className="grid grid-cols-1 md:grid-cols-2 gap-2 p-3.5 sm:p-4"
        >
          {caravans.map((c) => {
            const stateLine = STATE_LINE[c.state];
            const seaLine = c.sea_stage ? SEA_LINE[c.sea_stage] : undefined;
            const depart = c.state === 'on_road' && !seaLine ? departText(c.departs_in_sec, fetchedAt, now) : null;
            const inspectAction = renderInspect(c);
            return (
              <motion.li
                key={c.id}
                variants={{ hidden: { opacity: 0, y: 10 }, visible: { opacity: 1, y: 0 } }}
                className="flex flex-col sm:flex-row sm:items-center gap-3 rounded-card border border-gold/15 bg-gold/[0.04] p-3 min-w-0"
              >
                <div className="flex flex-col gap-1 min-w-0 flex-1">
                  <span className="text-white text-sm font-medium break-words">
                    Торговый караван: {c.group_name || c.group_code}, охрана {c.guard_count}
                  </span>
                  {seaLine && <span className={`text-xs ${seaLine.cls}`}>{seaLine.text}</span>}
                  {stateLine && <span className={`text-xs ${stateLine.cls}`}>{stateLine.text}</span>}
                  {c.state === 'inspection' && (
                    <span className={`text-xs ${INSPECTION_CLS}`}>{inspectionText(c.departs_in_sec, fetchedAt, now)}</span>
                  )}
                  {depart && <span className="text-white/50 text-xs">{depart}</span>}
                </div>
                <div className="shrink-0 flex flex-col gap-2">
                  {inspectAction}
                  {renderActions(c)}
                </div>
              </motion.li>
            );
          })}
        </motion.ul>
      )}
      {error && caravans.length > 0 && <p className="text-site-red text-xs px-4 pb-3">{error}</p>}
    </section>
  );
};

export default CaravanSection;
