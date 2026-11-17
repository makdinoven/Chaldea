import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import {
  announceSeaNotice,
  buyTicket,
  fetchCaptain,
  hireSailor,
  seaErrorMessage,
  sneakAboard,
} from '../../../../api/sea';
import { useCurrency } from '../../../../hooks/useCurrency';
import { useAppSelector } from '../../../../redux/store';
import type { CaptainView, SeaDestination, SeaPass, ShipPublic } from '../../../../types/sea';
import ModalShell from '../../../CommonComponents/ModalShell/ModalShell';
import RemainingText from '../../../CommonComponents/RemainingText';
import { NPC_DIALOGUE_HINT_CAPTAIN, isNpcDialogueGateError } from '../npcDialogueGate';

interface CaptainModalProps {
  npcId: number;
  npcName: string;
  npcAvatar: string | null;
  onClose: () => void;
}

/** What the confirmation window is about. */
type Pending =
  | { kind: 'ticket'; destination: SeaDestination }
  | { kind: 'sailor' }
  | { kind: 'stowaway' };

const PASS_KIND_LABELS: Record<string, string> = {
  ticket: 'Билет',
  sailor: 'Матрос',
  stowaway: 'Попытка пробраться зайцем',
};

const placeLine = (d: SeaDestination): string =>
  [d.region_name, d.country_name].filter((x): x is string => Boolean(x)).join(', ');

/** «Билет до «X»» / «Матрос до «X»» / «Заяц до «X»». */
export const seaPassTitle = (p: SeaPass): string => {
  const to = p.to_name ? `«${p.to_name}»` : 'следующего порта';
  if (p.kind === 'ticket') return `Билет до ${to}`;
  if (p.kind === 'sailor') return `Матрос до ${to}`;
  return `${PASS_KIND_LABELS.stowaway} (до ${to})`;
};

/** Status line of a ship: «У причала «X», отплытие через …» / «В море: зона, море → порт, прибытие через …». */
export const ShipStatusLine = ({ ship, onTimer }: { ship: ShipPublic; onTimer?: () => void }) => {
  if (ship.status === 'docked') {
    return (
      <span>
        У причала{ship.docked_port?.name ? ` «${ship.docked_port.name}»` : ''}
        {ship.is_active && ship.departs_at && (
          <>
            {', '}
            <RemainingText
              until={ship.departs_at}
              prefix="отплытие через"
              doneText="вот-вот отплывёт"
              onDone={onTimer}
              className="text-gold"
            />
          </>
        )}
        {ship.next_port?.name && ship.is_active ? ` → «${ship.next_port.name}»` : ''}
      </span>
    );
  }
  const zone = ship.current_zone;
  const where = zone ? [zone.name, zone.sea_name].filter(Boolean).join(', ') : 'открытое море';
  return (
    <span>
      В море: {where}
      {ship.next_port?.name ? ` → «${ship.next_port.name}»` : ''}
      {ship.arrives_at && (
        <>
          {', '}
          <RemainingText
            until={ship.arrives_at}
            prefix="прибытие ≈ через"
            doneText="вот-вот причалит"
            onDone={onTimer}
            className="text-gold"
          />
        </>
      )}
    </span>
  );
};

/**
 * FEAT-213 — the Captain of a ship (an NPC with the «captain» role): the route, next departure, fares to the next
 * stops, free seats and three ways aboard (ticket / sailor / stowaway), plus the character's own passes.
 * Works in the port and on the deck at sea («оплатить следующий участок, не сходя на берег»).
 * A ticket or a sailor job needs the «Диалог с НПС» post with the Captain; sneaking aboard does not.
 */
const CaptainModal = ({ npcId, npcName, npcAvatar, onClose }: CaptainModalProps) => {
  const characterId = useAppSelector((s) => s.user.character?.id ?? null) as number | null;
  const { format } = useCurrency();

  const [view, setView] = useState<CaptainView | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [gateHint, setGateHint] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const busyRef = useRef(false);

  const load = useCallback(async () => {
    if (!characterId) {
      setLoading(false);
      setLoadError('Нужен персонаж, чтобы говорить с капитаном');
      return;
    }
    setLoading(true);
    try {
      const res = await fetchCaptain(npcId, characterId);
      setView(res);
      setLoadError(null);
    } catch (err) {
      const text = seaErrorMessage(err, 'Не удалось поговорить с капитаном');
      setView(null);
      setLoadError(text);
      toast.error(text);
    } finally {
      setLoading(false);
    }
  }, [npcId, characterId]);

  useEffect(() => {
    void load();
  }, [load]);

  const run = async (p: Pending) => {
    if (busyRef.current || !characterId || !view) return;
    busyRef.current = true;
    setBusy(true);
    setActionError(null);
    const shipId = view.ship.id;
    try {
      if (p.kind === 'ticket') {
        const pass = await buyTicket(shipId, { character_id: characterId, npc_id: npcId, to_trip: p.destination.to_trip });
        toast.success(
          view.ship.status === 'sailing'
            ? `${seaPassTitle(pass)} куплен — оставайтесь на борту, он начнёт действовать в следующем порту`
            : `${seaPassTitle(pass)} куплен — поднимитесь на борт постом до отплытия`,
        );
      } else if (p.kind === 'sailor') {
        await hireSailor(shipId, { character_id: characterId, npc_id: npcId });
        toast.success('Вы наняты матросом — поднимитесь на борт и напишите пост на палубе до отплытия');
      } else {
        const res = await sneakAboard(shipId, characterId);
        toast(res.message || 'Вы пытаетесь незаметно пробраться на борт', { icon: '🕶️' });
      }
      setGateHint(false);
      setPending(null);
      // The location page refetches its details: the passage to the deck appears for the new pass holder.
      announceSeaNotice({ event: `own_${p.kind}`, ship_id: shipId, character_id: characterId });
      await load();
    } catch (err) {
      const text = seaErrorMessage(err, 'Не удалось договориться с капитаном');
      setActionError(text);
      setGateHint(isNpcDialogueGateError(err));
      toast.error(text);
      setPending(null);
      void load();
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const icon = (
    <div className="gold-outline relative w-9 h-9 rounded-full overflow-hidden bg-black/40 shrink-0">
      {npcAvatar ? (
        <img src={npcAvatar} alt={npcName} className="w-full h-full object-cover" />
      ) : (
        <div className="w-full h-full flex items-center justify-center text-lg" aria-hidden>
          ⚓
        </div>
      )}
    </div>
  );

  const hint = gateHint && <p className="text-white/60 text-xs sm:text-sm">{NPC_DIALOGUE_HINT_CAPTAIN}</p>;
  const ship = view?.ship ?? null;
  const currentStopPort = ship?.status === 'docked' ? ship.docked_port?.id : null;
  const nextStopPort = ship?.next_port?.id ?? null;

  return (
    <ModalShell open onClose={onClose} title={npcName} size="lg" icon={icon} dismissible={!busy}>
      {loading && !view ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
        </div>
      ) : !view || !ship ? (
        <div className="flex flex-col items-center gap-3 py-8 text-center">
          <p className="text-site-red text-sm">{loadError ?? 'Не удалось поговорить с капитаном'}</p>
          {characterId && (
            <button type="button" className="btn-line" onClick={() => void load()}>
              Повторить
            </button>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-4 min-w-0">
          {/* Ship and its state */}
          <section className="flex flex-col gap-2 min-w-0">
            <h3 className="gold-text text-base sm:text-lg font-medium break-words">Корабль «{ship.name}»</h3>
            <p className="text-white/80 text-sm break-words">
              <ShipStatusLine ship={ship} onTimer={() => void load()} />
            </p>
            {!ship.is_active && <p className="text-site-red text-xs sm:text-sm">Корабль сейчас не ходит.</p>}
            {ship.stops.length > 0 && (
              <div className="flex flex-wrap items-center gap-1.5 text-xs">
                <span className="text-white/45 shrink-0" title={ship.is_loop ? 'По кругу' : 'Туда и обратно'}>
                  {ship.is_loop ? '↻' : '⇄'} Маршрут:
                </span>
                {ship.stops.map((s, i) => {
                  const isCurrent = s.port_id === currentStopPort;
                  const isNext = s.port_id === nextStopPort;
                  return (
                    <span key={`${s.index}-${s.port_id}`} className="flex items-center gap-1.5 min-w-0">
                      {i > 0 && <span className="text-white/30">—</span>}
                      <span
                        className={`px-2 py-0.5 rounded-full border break-words ${
                          isCurrent
                            ? 'border-gold/60 text-gold bg-gold/10'
                            : isNext
                              ? 'border-site-blue/60 text-site-blue'
                              : 'border-white/10 text-white/60'
                        }`}
                      >
                        {s.port_name ?? `Порт #${s.port_id}`}
                      </span>
                    </span>
                  );
                })}
              </div>
            )}
            <p className="text-white/50 text-xs">
              У вас: <span className="text-gold">{format(view.balance)}</span>
            </p>
          </section>

          {/* Tickets */}
          <section className="flex flex-col gap-2">
            <h3 className="gold-text text-sm sm:text-base font-medium uppercase tracking-wide">Билеты</h3>
            {view.destinations.length === 0 ? (
              <p className="text-white/50 text-sm">Капитан сейчас не продаёт билеты.</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {view.destinations.map((d) => (
                  <li
                    key={`${d.to_trip}-${d.port_id}`}
                    className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3 rounded-card border border-white/10 bg-white/[0.03] px-3 py-2.5 min-w-0"
                  >
                    <div className="flex flex-col gap-0.5 min-w-0 flex-1">
                      <span className="text-white text-sm font-medium break-words">
                        до «{d.port_name ?? `Порт #${d.port_id}`}»
                        {placeLine(d) && <span className="text-white/50 font-normal"> · {placeLine(d)}</span>}
                      </span>
                      <span className="text-white/60 text-xs">
                        <span className="text-gold">{format(d.fare)}</span>
                        {' · '}
                        {d.eta ? (
                          <RemainingText until={d.eta} prefix="прибытие ≈ через" doneText="прибытие скоро" />
                        ) : (
                          'время прибытия неизвестно'
                        )}
                        {' · '}
                        <span className={d.seats_left > 0 ? 'text-stat-energy' : 'text-site-red'}>
                          {d.seats_left > 0 ? `мест: ${d.seats_left}` : 'мест нет'}
                        </span>
                      </span>
                      {!d.can_buy && d.reason && <span className="text-white/45 text-xs break-words">{d.reason}</span>}
                    </div>
                    <button
                      type="button"
                      className="btn-blue w-full sm:w-auto !px-5 shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
                      disabled={!d.can_buy || busy}
                      onClick={() => {
                        setActionError(null);
                        setPending({ kind: 'ticket', destination: d });
                      }}
                    >
                      Купить билет
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {/* Sailor job + stowaway */}
          <section className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div className="flex flex-col gap-2 rounded-card border border-white/10 bg-white/[0.03] px-3 py-2.5 min-w-0">
              <span className="text-white text-sm font-medium">Наняться матросом</span>
              <span className="text-white/60 text-xs">
                Бесплатно, на один рейс. До отплытия нужно подняться на палубу и написать там пост от{' '}
                {view.sailor.min_chars} символов — иначе вас высадят. Мест для матросов: {view.sailor.slots_left}.
              </span>
              {!view.sailor.can_hire && view.sailor.reason && (
                <span className="text-white/45 text-xs break-words">{view.sailor.reason}</span>
              )}
              <button
                type="button"
                className="btn-line w-full mt-auto disabled:opacity-40 disabled:cursor-not-allowed"
                disabled={!view.sailor.can_hire || busy}
                onClick={() => {
                  setActionError(null);
                  setPending({ kind: 'sailor' });
                }}
              >
                Наняться
              </button>
            </div>
            <div className="flex flex-col gap-2 rounded-card border border-white/10 bg-white/[0.03] px-3 py-2.5 min-w-0">
              <span className="text-white text-sm font-medium">Пробраться зайцем</span>
              <span className="text-white/60 text-xs">
                Без оплаты и без разговора с капитаном. При отплытии команда проверяет борт: поймают — высадят, и это
                преступление по законам края порта.
              </span>
              {!view.stowaway.can_try && view.stowaway.reason && (
                <span className="text-white/45 text-xs break-words">{view.stowaway.reason}</span>
              )}
              <button
                type="button"
                className="btn-line w-full mt-auto disabled:opacity-40 disabled:cursor-not-allowed"
                disabled={!view.stowaway.can_try || busy}
                onClick={() => {
                  setActionError(null);
                  setPending({ kind: 'stowaway' });
                }}
              >
                Рискнуть
              </button>
            </div>
          </section>

          {/* My passes */}
          <section className="flex flex-col gap-2">
            <h3 className="gold-text text-sm sm:text-base font-medium uppercase tracking-wide">Мои места</h3>
            {view.my_passes.length === 0 ? (
              <p className="text-white/50 text-sm">На этом корабле у вас нет места.</p>
            ) : (
              <ul className="flex flex-col gap-1.5">
                {view.my_passes.map((p) => (
                  <li
                    key={p.id}
                    className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-3 rounded-card border border-gold/30 bg-gold/[0.05] px-3 py-2 min-w-0"
                  >
                    <span className="text-white text-sm flex-1 break-words">
                      {seaPassTitle(p)}
                      {p.from_name && <span className="text-white/50"> · из «{p.from_name}»</span>}
                    </span>
                    <span className={`text-xs shrink-0 ${p.valid_now ? 'text-stat-energy' : 'text-white/50'}`}>
                      {p.valid_now
                        ? ship.status === 'docked'
                          ? 'на ближайший рейс'
                          : 'действует сейчас'
                        : 'начнёт действовать в следующем порту'}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            <p className="text-white/45 text-xs">
              На борт поднимаются постом из порта. Не успели до отплытия — билет сгорает, деньги не возвращаются.
            </p>
          </section>

          {actionError && <p className="text-site-red text-xs sm:text-sm">{actionError}</p>}
          {hint}
        </div>
      )}

      <ModalShell
        open={pending !== null}
        onClose={() => !busy && setPending(null)}
        title={
          pending?.kind === 'ticket'
            ? 'Купить билет?'
            : pending?.kind === 'sailor'
              ? 'Наняться матросом?'
              : 'Пробраться зайцем?'
        }
        size="sm"
        dismissible={!busy}
        footer={
          <>
            <button
              type="button"
              className="btn-line w-full sm:w-auto sm:max-w-[160px]"
              disabled={busy}
              onClick={() => setPending(null)}
            >
              Отмена
            </button>
            <button
              type="button"
              className="btn-blue w-full sm:w-auto"
              disabled={busy}
              onClick={() => pending && void run(pending)}
            >
              {busy ? 'Минутку...' : pending?.kind === 'ticket' ? 'Купить' : pending?.kind === 'sailor' ? 'Наняться' : 'Рискнуть'}
            </button>
          </>
        }
      >
        {pending?.kind === 'ticket' && (
          <ul className="flex flex-col gap-1.5 text-white/80 text-sm list-disc pl-5">
            <li>
              Билет до «{pending.destination.port_name ?? `Порт #${pending.destination.port_id}`}» стоит{' '}
              <span className="text-gold">{format(pending.destination.fare)}</span>.
            </li>
            <li>Поднимитесь на борт постом до отплытия — опоздавший теряет билет без возврата.</li>
            <li>Не сошли в порту назначения — за следующий участок нужно платить снова, иначе вас высадят.</li>
          </ul>
        )}
        {pending?.kind === 'sailor' && (
          <ul className="flex flex-col gap-1.5 text-white/80 text-sm list-disc pl-5">
            <li>Матрос плывёт бесплатно, но только один рейс.</li>
            <li>
              До отплытия нужно написать пост на палубе от {view?.sailor.min_chars ?? 0} символов (пост, которым вы
              поднялись на борт, тоже считается).
            </li>
            <li>Не написали — капитан высадит вас в порту.</li>
          </ul>
        )}
        {pending?.kind === 'stowaway' && (
          <ul className="flex flex-col gap-1.5 text-white/80 text-sm list-disc pl-5">
            <li>Вы проберётесь на палубу без билета — поднимитесь на борт постом до отплытия.</li>
            <li>При отплытии команда проверяет борт. Чем лучше вы скрываетесь, тем выше шанс остаться незамеченным.</li>
            <li className="text-site-red">Поймают — высадят на берег, а стража края порта узнает о преступлении.</li>
          </ul>
        )}
      </ModalShell>
    </ModalShell>
  );
};

export default CaptainModal;
