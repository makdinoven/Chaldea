import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { fetchSmugglerCaravans, hireEscort } from '../../../../api/caravanEscort';
import { apiErrorMessage } from '../../../../api/errors';
import { useCurrency } from '../../../../hooks/useCurrency';
import { getMe } from '../../../../redux/slices/userSlice';
import { useAppDispatch } from '../../../../redux/store';
import type { CaravaneerCaravan, SmugglerView } from '../../../../types/caravanEscort';
import ModalShell from '../../../CommonComponents/ModalShell/ModalShell';
import RemainingText from '../../../CommonComponents/RemainingText';
import { NPC_DIALOGUE_HINT_FENCE, isNpcDialogueGateError } from '../npcDialogueGate';

interface SmugglerSectionProps {
  npcId: number;
  characterId: number;
  /** Reports a hire in progress (the fence window must not be closed meanwhile). */
  onBusyChange?: (busy: boolean) => void;
  /** Closes the fence window once the smuggler has been led to his caravan. */
  onHired: () => void;
}

/** Caravan id → the moment it leaves the gate (the server sends seconds; fixed at load time). */
type DepartMap = Record<number, Date | null>;

const departures = (caravans: CaravaneerCaravan[]): DepartMap => {
  const now = Date.now();
  return Object.fromEntries(
    caravans.map((c) => [c.id, c.departs_in_sec != null ? new Date(now + c.departs_in_sec * 1000) : null]),
  );
};

/**
 * FEAT-216 C7/C8 — «Охрана контрабанды» at the fence: secret-cargo caravans preparing at the trade gate of the fence's
 * region. Hiring moves the smuggler to the caravan; pay is higher than ordinary escorting, but a lost fight with the
 * customs or the guard means a «Контрабанда» crime. The wording «тайный груз» is shown only here, to the smuggler.
 */
const SmugglerSection = ({ npcId, characterId, onBusyChange, onHired }: SmugglerSectionProps) => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const { format } = useCurrency();

  const [view, setView] = useState<SmugglerView | null>(null);
  const [departAt, setDepartAt] = useState<DepartMap>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [gateHint, setGateHint] = useState(false);
  const [confirm, setConfirm] = useState<CaravaneerCaravan | null>(null);
  const [hiring, setHiring] = useState(false);
  const [hireError, setHireError] = useState<string | null>(null);
  const hiringRef = useRef(false);
  const busyRef = useRef(onBusyChange);
  busyRef.current = onBusyChange;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetchSmugglerCaravans(npcId, characterId);
      setView(res);
      setDepartAt(departures(res.caravans ?? []));
      setLoadError(null);
      setGateHint(false);
    } catch (err) {
      const text = apiErrorMessage(err, 'Не удалось узнать о тайных караванах');
      setView(null);
      setLoadError(text);
      setGateHint(isNpcDialogueGateError(err));
      toast.error(text);
    } finally {
      setLoading(false);
    }
  }, [npcId, characterId]);

  useEffect(() => {
    void load();
  }, [load]);

  const setBusy = (busy: boolean) => {
    hiringRef.current = busy;
    setHiring(busy);
    busyRef.current?.(busy);
  };

  const hire = async (caravan: CaravaneerCaravan) => {
    if (hiringRef.current) return;
    setBusy(true);
    setHireError(null);
    try {
      const job = await hireEscort(caravan.id, { character_id: characterId, npc_id: npcId });
      toast.success(`Вы наняты в охрану каравана «${caravan.group_name ?? caravan.group_code}»`);
      setConfirm(null);
      await dispatch(getMe());
      setBusy(false);
      onHired();
      if (job.current_location_id != null) navigate(`/location/${job.current_location_id}`);
    } catch (err) {
      const text = apiErrorMessage(err, 'Не удалось наняться в охрану');
      setHireError(text);
      setGateHint(isNpcDialogueGateError(err));
      toast.error(text);
      setConfirm(null);
      setBusy(false);
      void load();
    }
  };

  const hint = gateHint && <p className="text-white/60 text-xs sm:text-sm">{NPC_DIALOGUE_HINT_FENCE}</p>;

  if (loading && !view) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
      </div>
    );
  }

  if (!view) {
    return (
      <div className="flex flex-col items-center gap-3 py-8 text-center">
        <p className="text-site-red text-sm">{loadError ?? 'Не удалось узнать о тайных караванах'}</p>
        {hint}
        <button type="button" className="btn-line" onClick={() => void load()}>
          Повторить
        </button>
      </div>
    );
  }

  const caravans = view.caravans ?? [];

  return (
    <div className="flex flex-col gap-4 min-w-0">
      <p className="text-white/60 text-xs sm:text-sm">
        Скупщик тайком нанимает охрану к караванам с тайным грузом — запрещённым там, куда он едет. Такой караван
        обходит таможенные посты, и платят за охрану больше обычного. Но если его заметят таможенники или стража и вы
        проиграете бой, груз конфискуют, а вам запишут преступление «Контрабанда».
      </p>

      {view.gate_location_name && (
        <p className="text-white/70 text-xs sm:text-sm break-words">
          Караваны собираются у ворот: <span className="text-gold">{view.gate_location_name}</span>. После найма вы
          сразу окажетесь у каравана.
        </p>
      )}

      {view.my_escort_caravan_id != null && (
        <p className="rounded-card border border-gold/40 bg-gold/[0.06] px-3 py-2 text-white text-sm">
          Вы уже в охране каравана.
        </p>
      )}

      {!view.seats_enabled && <p className="text-white/60 text-sm">Сейчас скупщик никого не нанимает.</p>}

      <section className="flex flex-col gap-2">
        <h3 className="gold-text text-sm sm:text-base font-medium uppercase tracking-wide">Тайный груз</h3>
        {caravans.length === 0 ? (
          <p className="text-white/50 text-sm">Сейчас тайных караванов нет. Загляните позже.</p>
        ) : (
          <ul className="flex flex-col gap-2">
            {caravans.map((c) => (
              <li
                key={c.id}
                className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-3 rounded-card border border-white/10 bg-white/[0.03] px-3 py-2.5 min-w-0"
              >
                <div className="flex flex-col gap-0.5 min-w-0 flex-1">
                  <span className="text-white text-sm font-medium break-words">
                    Караван: {c.group_name ?? c.group_code}
                  </span>
                  <span className="text-white/60 text-xs">
                    {departAt[c.id] ? (
                      <RemainingText until={departAt[c.id]} prefix="отправится через" doneText="вот-вот тронется" />
                    ) : (
                      'вот-вот тронется'
                    )}
                    {' · '}
                    <span className={c.has_seats ? 'text-stat-energy' : 'text-site-red'}>
                      {c.has_seats ? 'есть места' : 'мест нет'}
                    </span>
                    {' · плата ~'}
                    <span className="text-gold">{format(c.pay_estimate)}</span>
                  </span>
                  {!c.can_hire && c.reason && <span className="text-white/45 text-xs break-words">{c.reason}</span>}
                </div>
                <button
                  type="button"
                  className="btn-blue w-full sm:w-auto !px-5 shrink-0"
                  disabled={!c.can_hire || hiring}
                  onClick={() => {
                    setHireError(null);
                    setConfirm(c);
                  }}
                >
                  Наняться
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {hireError && <p className="text-site-red text-xs sm:text-sm">{hireError}</p>}
      {hint}

      <ModalShell
        open={confirm !== null}
        onClose={() => !hiring && setConfirm(null)}
        title="Охранять тайный груз?"
        size="sm"
        dismissible={!hiring}
        footer={
          <>
            <button
              type="button"
              className="btn-line w-full sm:w-auto sm:max-w-[160px]"
              disabled={hiring}
              onClick={() => setConfirm(null)}
            >
              Отмена
            </button>
            <button
              type="button"
              className="btn-blue w-full sm:w-auto"
              disabled={hiring}
              onClick={() => confirm && void hire(confirm)}
            >
              {hiring ? 'Нанимаемся...' : 'Наняться'}
            </button>
          </>
        }
      >
        <ul className="flex flex-col gap-1.5 text-white/80 text-sm list-disc pl-5">
          <li>Вас сразу отведут к каравану у торговых ворот.</li>
          <li>Пока вы в охране, ходить, писать посты и торговать нельзя — вы едете вместе с караваном.</li>
          <li>Нападут налётчики, таможенники или стража — сражаетесь сами, автобоя нет.</li>
          <li>Проиграете таможне или страже — груз конфискуют, оплаты не будет, а вам запишут «Контрабанду».</li>
          <li>Плата — при доставке; отобьётесь — надбавка.</li>
        </ul>
      </ModalShell>
    </div>
  );
};

export default SmugglerSection;
