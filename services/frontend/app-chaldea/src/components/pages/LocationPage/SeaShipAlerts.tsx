import { Link } from 'react-router-dom';
import type { ShipPublic } from '../../../types/sea';
import { battlePath } from '../../../utils/battlePath';
import { formatServerDateTime, serverDateMs } from '../../../utils/serverDate';

const CLOCK: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit' };

/** True while the naive-UTC moment is still ahead (an unparsable / missing one counts as ahead). */
const isAhead = (raw: string | null | undefined): boolean => {
  const ms = serverDateMs(raw);
  return !Number.isFinite(ms) || ms <= 0 || ms > Date.now();
};

interface SeaShipAlertsProps {
  ship: ShipPublic;
  /** Show the links to the deck battles (the deck header); the Captain window only names the danger. */
  withBattleLinks?: boolean;
}

/**
 * FEAT-214 — the weather and the danger around a ship: a storm over its zone (until when), a departure postponed by
 * a storm, monsters on the deck with the links to the battle(s) and how long the ship holds for them.
 */
const SeaShipAlerts = ({ ship, withBattleLinks = false }: SeaShipAlertsProps) => {
  const storm = ship.storm && isAhead(ship.storm.ends_at) ? ship.storm : null;
  const postponed = ship.status === 'docked' && Boolean(ship.departure_postponed);
  const raid = ship.raid ?? null;
  if (!storm && !postponed && !raid) return null;

  const monster = raid?.monster_name ? `«${raid.monster_name}»` : 'морским чудовищем';
  const holdUntil = raid?.hold_until && isAhead(raid.hold_until) ? raid.hold_until : null;

  return (
    <div className="flex flex-col gap-1.5 min-w-0 text-xs sm:text-sm">
      {storm && (
        <p className="text-site-blue break-words">
          <span aria-hidden>⛈️ </span>
          Шторм{storm.zone_name ? ` в «${storm.zone_name}»` : ''} — до {formatServerDateTime(storm.ends_at, CLOCK)}
        </p>
      )}
      {postponed && <p className="text-gold-light break-words">Отплытие отложено из-за шторма</p>}
      {raid && (
        <div className="flex flex-col gap-1 rounded-card border border-site-red/40 bg-site-red/[0.06] px-3 py-2 min-w-0">
          <p className="text-site-red font-medium break-words">
            <span aria-hidden>⚔️ </span>
            На палубе бой с {monster}!
          </p>
          {withBattleLinks &&
            (raid.battles.length > 0 ? (
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                {raid.battles.map((b, i) => (
                  <Link key={b.battle_id} to={battlePath(ship.deck_location_id, b.battle_id)} className="site-link">
                    {raid.battles.length > 1 ? `К бою ${i + 1}` : 'К бою'} (#{b.battle_id})
                  </Link>
                ))}
              </div>
            ) : (
              <p className="text-white/60">Чудовища поднимаются на борт — бой вот-вот начнётся.</p>
            ))}
          {holdUntil && (
            <p className="text-white/60 break-words">
              Корабль стоит, пока идёт бой (до {formatServerDateTime(holdUntil, CLOCK)})
            </p>
          )}
        </div>
      )}
    </div>
  );
};

export default SeaShipAlerts;
