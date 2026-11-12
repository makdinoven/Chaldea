import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { fetchCaravaneer, hireEscort } from '../../../../api/caravanEscort';
import { apiErrorMessage } from '../../../../api/errors';
import { useCurrency } from '../../../../hooks/useCurrency';
import { getMe } from '../../../../redux/slices/userSlice';
import { useAppDispatch, useAppSelector } from '../../../../redux/store';
import type { CaravaneerCaravan, CaravaneerView } from '../../../../types/caravanEscort';
import CaravanEscortModal from '../../../CaravanEscort/CaravanEscortModal';
import ModalShell from '../../../CommonComponents/ModalShell/ModalShell';
import RemainingText from '../../../CommonComponents/RemainingText';
import { NPC_DIALOGUE_HINT_CARAVANEER, isNpcDialogueGateError } from '../npcDialogueGate';

interface CaravaneerModalProps {
  npcId: number;
  npcName: string;
  npcAvatar: string | null;
  onClose: () => void;
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
 * FEAT-212 — «Караванщик» NPC at a trade gate: caravans getting ready to leave from here, and «Наняться в охрану».
 * Shows only «есть места» / «мест нет» (never how many players are inside — PM decision 1).
 */
const CaravaneerModal = ({ npcId, npcName, npcAvatar, onClose }: CaravaneerModalProps) => {
  const dispatch = useAppDispatch();
  const characterId = useAppSelector((s) => s.user.character?.id ?? null) as number | null;
  const { format } = useCurrency();

  const [view, setView] = useState<CaravaneerView | null>(null);
  const [departAt, setDepartAt] = useState<DepartMap>({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [gateHint, setGateHint] = useState(false);
  const [confirm, setConfirm] = useState<CaravaneerCaravan | null>(null);
  const [hiring, setHiring] = useState(false);
  const [hireError, setHireError] = useState<string | null>(null);
  const [escortOpen, setEscortOpen] = useState(false);
  const hiringRef = useRef(false);

  const load = useCallback(async () => {
    if (!characterId) {
      setLoading(false);
      setLoadError('Нужен персонаж, чтобы наняться в охрану');
      return;
    }
    setLoading(true);
    try {
      const res = await fetchCaravaneer(npcId, characterId);
      setView(res);
      setDepartAt(departures(res.caravans ?? []));
      setLoadError(null);
      setGateHint(false);
    } catch (err) {
      const text = apiErrorMessage(err, 'Не удалось открыть караванщика');
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

  const hire = async (caravan: CaravaneerCaravan) => {
    if (hiringRef.current || !characterId) return;
    hiringRef.current = true;
    setHiring(true);
    setHireError(null);
    try {
      await hireEscort(caravan.id, { character_id: characterId, npc_id: npcId });
      toast.success(`Вы наняты в охрану каравана «${caravan.group_name ?? caravan.group_code}»`);
      setConfirm(null);
      await dispatch(getMe());
      setEscortOpen(true);
    } catch (err) {
      const text = apiErrorMessage(err, 'Не удалось наняться в охрану');
      setHireError(text);
      setGateHint(isNpcDialogueGateError(err));
      toast.error(text);
      setConfirm(null);
      void load();
    } finally {
      hiringRef.current = false;
      setHiring(false);
    }
  };

  if (escortOpen && characterId) {
    return <CaravanEscortModal characterId={characterId} onClose={onClose} />;
  }

  const icon = (
    <div className="gold-outline relative w-9 h-9 rounded-full overflow-hidden bg-black/40 shrink-0">
      {npcAvatar ? (
        <img src={npcAvatar} alt={npcName} className="w-full h-full object-cover" />
      ) : (
        <div className="w-full h-full flex items-center justify-center text-lg" aria-hidden>
          🐫
        </div>
      )}
    </div>
  );

  const hint = gateHint && <p className="text-white/60 text-xs sm:text-sm">{NPC_DIALOGUE_HINT_CARAVANEER}</p>;
  const caravans = view?.caravans ?? [];

  return (
    <ModalShell open onClose={onClose} title={npcName} size="lg" icon={icon} dismissible={!hiring}>
      {loading && !view ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
        </div>
      ) : !view ? (
        <div className="flex flex-col items-center gap-3 py-8 text-center">
          <p className="text-site-red text-sm">{loadError ?? 'Не удалось открыть караванщика'}</p>
          {hint}
          {characterId && (
            <button type="button" className="btn-line" onClick={() => void load()}>
              Повторить
            </button>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-4 min-w-0">
          <p className="text-white/60 text-xs sm:text-sm">
            Караванщик набирает охрану к караванам, которые собираются в путь из этих ворот. Охранник едет внутри
            каравана, его никто не видит; при налёте он неожиданно для налётчиков встаёт на защиту вместе со стражей.
          </p>

          {view.my_escort_caravan_id != null && (
            <div className="flex flex-col sm:flex-row sm:items-center gap-2 rounded-card border border-gold/40 bg-gold/[0.06] px-3 py-2">
              <span className="text-white text-sm flex-1">Вы уже в охране каравана.</span>
              <button type="button" className="btn-blue text-sm !px-5" onClick={() => setEscortOpen(true)}>
                Открыть караван
              </button>
            </div>
          )}

          {!view.seats_enabled && <p className="text-white/60 text-sm">Караванщик сейчас не нанимает охрану.</p>}

          <section className="flex flex-col gap-2">
            <h3 className="gold-text text-sm sm:text-base font-medium uppercase tracking-wide">Готовятся к отправке</h3>
            {caravans.length === 0 ? (
              <p className="text-white/50 text-sm">Сейчас здесь не собирается ни один караван. Загляните позже.</p>
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
                      Наняться в охрану
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {hireError && <p className="text-site-red text-xs sm:text-sm">{hireError}</p>}
          {hint}
        </div>
      )}

      <ModalShell
        open={confirm !== null}
        onClose={() => !hiring && setConfirm(null)}
        title="Наняться в охрану?"
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
          <li>Пока вы в охране, ходить, писать посты и торговать нельзя — вы едете вместе с караваном.</li>
          <li>При налёте вы сражаетесь сами, автобоя нет; на ход даётся 24 часа.</li>
          <li>Плата — при доставке; отобьётесь от налёта — надбавка.</li>
          <li>Сойти можно в любой момент, но без оплаты и без возврата в этот караван.</li>
        </ul>
      </ModalShell>
    </ModalShell>
  );
};

export default CaravaneerModal;
