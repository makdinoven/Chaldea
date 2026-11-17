import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { fetchDeck, onSeaNotice, seaErrorMessage } from '../../../api/sea';
import type { DeckView, SeaPass } from '../../../types/sea';
import { ShipStatusLine, seaPassTitle } from './CaptainModal/CaptainModal';

interface ShipDeckHeaderProps {
  /** The deck location. */
  locationId: number;
  shipId: number;
  characterId: number;
  /** The character stands on this deck (his passes and warnings are shown only then). */
  isCharacterHere: boolean;
  /** The ship docked / sailed — the page refetches its details (the disembark passage opens / closes). */
  onShipStatusChange?: () => void;
}

const POLL_MS = 30_000;

/** A pass line on the deck: what the character's place is and when it ends. */
const passLine = (p: SeaPass, docked: boolean, sailorMinChars: number): string => {
  if (p.kind === 'sailor' && docked && p.valid_now) {
    return `${seaPassTitle(p)} — до отплытия нужен пост на палубе от ${sailorMinChars} символов`;
  }
  if (p.kind === 'stowaway') return `${seaPassTitle(p)} — команда проверит борт при отплытии`;
  if (!p.valid_now) return `${seaPassTitle(p)} — начнёт действовать в следующем порту`;
  return seaPassTitle(p);
};

/**
 * FEAT-213 — the head of a ship's deck (the deck is an ordinary location): the ship, its Captain, where it is
 * («У причала X» / «В море: зона, море → порт»), departure or arrival countdown, ships nearby, the character's own
 * place aboard and a warning when he has none for the next trip. Polls every 30 s, on a countdown end and on
 * `ws_type="sea"` notices of this ship.
 */
const ShipDeckHeader = ({ locationId, shipId, characterId, isCharacterHere, onShipStatusChange }: ShipDeckHeaderProps) => {
  const [view, setView] = useState<DeckView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const errorShownRef = useRef(false);
  const statusRef = useRef<string | null>(null);
  const onChangeRef = useRef(onShipStatusChange);
  onChangeRef.current = onShipStatusChange;

  const load = useCallback(async () => {
    try {
      const res = await fetchDeck(locationId, characterId);
      setView(res);
      setError(null);
      errorShownRef.current = false;
      const status = `${res.ship.status}:${res.ship.docked_port?.id ?? ''}`;
      if (statusRef.current !== null && statusRef.current !== status) onChangeRef.current?.();
      statusRef.current = status;
    } catch (err) {
      const text = seaErrorMessage(err, 'Не удалось узнать, где корабль');
      setError(text);
      if (!errorShownRef.current) {
        errorShownRef.current = true;
        toast.error(text);
      }
    }
  }, [locationId, characterId]);

  useEffect(() => {
    statusRef.current = null;
    void load();
    const timer = window.setInterval(() => {
      if (document.visibilityState === 'visible') void load();
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [load]);

  useEffect(
    () =>
      onSeaNotice((data) => {
        if (data.ship_id == null || data.ship_id === shipId) void load();
      }),
    [load, shipId],
  );

  if (!view) {
    return error ? (
      <div className="flex flex-col sm:flex-row sm:items-center gap-2 rounded-card bg-site-bg backdrop-blur-sm border border-white/10 px-4 py-3">
        <p className="text-site-red text-sm flex-1">{error}</p>
        <button type="button" className="btn-line w-full sm:w-auto" onClick={() => void load()}>
          Повторить
        </button>
      </div>
    ) : null;
  }

  const { ship } = view;
  const docked = ship.status === 'docked';
  const passes = view.my_passes;
  const hasNextTrip = docked
    ? passes.some((p) => p.valid_now)
    : passes.some((p) => !p.valid_now) ||
      passes.some((p) => p.valid_now && ship.next_port != null && p.to_port_id !== ship.next_port.id);
  const warning = !isCharacterHere
    ? null
    : docked
      ? hasNextTrip || !ship.is_active
        ? null
        : 'У вас нет места на следующий рейс — при отплытии вас высадят. Купите билет у капитана или сойдите на берег.'
      : hasNextTrip
        ? null
        : `Ваше место заканчивается${ship.next_port?.name ? ` в «${ship.next_port.name}»` : ' в следующем порту'} — чтобы плыть дальше, купите у капитана следующий участок, иначе при отплытии вас высадят.`;

  return (
    <section className="flex flex-col gap-2.5 rounded-card bg-site-bg backdrop-blur-sm border border-gold-dark/30 shadow-card px-3 sm:px-5 py-3 sm:py-4 min-w-0">
      <div className="flex items-start gap-3 min-w-0">
        <span
          className="w-10 h-10 shrink-0 flex items-center justify-center rounded-[10px] bg-gold/10 border border-gold-dark/30 text-xl"
          aria-hidden
        >
          ⚓
        </span>
        <div className="flex flex-col gap-1 min-w-0 flex-1">
          <h2 className="gold-text text-base sm:text-lg font-medium break-words">Корабль «{ship.name}»</h2>
          <p className="text-white/80 text-xs sm:text-sm break-words">
            <ShipStatusLine ship={ship} onTimer={() => void load()} />
          </p>
          {!ship.is_active && (
            <p className="text-site-red text-xs sm:text-sm">Корабль сейчас не ходит — сойти можно у причала.</p>
          )}
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-white/60">
        <span className="flex items-center gap-1.5 min-w-0">
          Капитан:
          {ship.captain ? (
            <span className="flex items-center gap-1.5 text-white min-w-0">
              {ship.captain.avatar && (
                <img src={ship.captain.avatar} alt="" className="w-5 h-5 rounded-full object-cover shrink-0" />
              )}
              <span className="truncate">{ship.captain.name ?? '—'}</span>
            </span>
          ) : (
            <span className="text-white/45">капитана нет</span>
          )}
        </span>
        <span>На борту: {view.passengers_count}</span>
      </div>

      {view.ships_nearby.length > 0 && (
        <ul className="flex flex-col gap-0.5 text-xs sm:text-sm text-site-blue">
          {view.ships_nearby.map((s) => (
            <li key={s.id} className="break-words">
              {docked ? `Рядом у причала — корабль «${s.name}»` : `Вдали виден корабль «${s.name}»`}
            </li>
          ))}
        </ul>
      )}

      {isCharacterHere && passes.length > 0 && (
        <ul className="flex flex-col gap-0.5 text-xs sm:text-sm text-stat-energy">
          {passes.map((p) => (
            <li key={p.id} className="break-words">
              {passLine(p, docked, view.sailor_post_min_chars)}
            </li>
          ))}
        </ul>
      )}
      {warning && <p className={`text-xs sm:text-sm ${docked ? 'text-site-red' : 'text-gold-light'}`}>{warning}</p>}
    </section>
  );
};

export default ShipDeckHeader;
