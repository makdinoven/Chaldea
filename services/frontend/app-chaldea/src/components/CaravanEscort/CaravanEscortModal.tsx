import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { fetchEscortJob, leaveEscort } from '../../api/caravanEscort';
import { apiErrorMessage } from '../../api/errors';
import { useCurrency } from '../../hooks/useCurrency';
import { getMe } from '../../redux/slices/userSlice';
import { useAppDispatch } from '../../redux/store';
import type { EscortJob } from '../../types/caravanEscort';
import { battlePath } from '../../utils/battlePath';
import ModalShell from '../CommonComponents/ModalShell/ModalShell';
import RemainingText from '../CommonComponents/RemainingText';
import CaravanEscortChannel from './CaravanEscortChannel';
import CaravanEscortRoute from './CaravanEscortRoute';
import { ACTIVE_RAID, ESCORT_RAID_LABEL, ESCORT_STATE_CLS, stateLabel } from './escortLabels';

interface CaravanEscortModalProps {
  characterId: number;
  onClose: () => void;
}

/** Job refresh period while the panel is open (feature file 3.16). */
const POLL_MS = 30_000;

/**
 * FEAT-212 — «Вы в охране каравана»: route, where the caravan is, countdown to the next move, state,
 * fellow escorts, expected pay, the raid (with a link to the battle), the private caravan channel and «Сойти».
 */
const CaravanEscortModal = ({ characterId, onClose }: CaravanEscortModalProps) => {
  const dispatch = useAppDispatch();
  const { format } = useCurrency();
  const [job, setJob] = useState<EscortJob | null>(null);
  /** False until the first answer; then `job === null` means no job. */
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  /** Moment of the next move, fixed when the job was loaded (the server sends seconds). */
  const [nextMoveAt, setNextMoveAt] = useState<Date | null>(null);
  const [confirmLeave, setConfirmLeave] = useState(false);
  const [leaving, setLeaving] = useState(false);
  const [leaveError, setLeaveError] = useState<string | null>(null);
  const leavingRef = useRef(false);
  const hadJobRef = useRef(false);
  /** The first failure of a poll series is toasted; repeats stay inline only. */
  const toastedRef = useRef(false);

  const load = useCallback(async () => {
    try {
      const res = await fetchEscortJob(characterId);
      setJob(res);
      setNextMoveAt(res && res.next_move_in_sec != null ? new Date(Date.now() + res.next_move_in_sec * 1000) : null);
      setLoadError(null);
      toastedRef.current = false;
      // The job ended while the panel was open: the lock is gone too.
      if (!res && hadJobRef.current) void dispatch(getMe());
      hadJobRef.current = Boolean(res);
    } catch (err) {
      const msg = apiErrorMessage(err, 'Не удалось загрузить охрану каравана');
      setLoadError(msg);
      if (!toastedRef.current) {
        toast.error(msg);
        toastedRef.current = true;
      }
    } finally {
      setLoaded(true);
    }
  }, [characterId, dispatch]);

  /** Stable for the channel (its poll must not restart on every render). */
  const reloadJob = useCallback(() => {
    void load();
  }, [load]);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(timer);
  }, [load]);

  const leave = async () => {
    if (leavingRef.current) return;
    leavingRef.current = true;
    setLeaving(true);
    setLeaveError(null);
    try {
      await leaveEscort(characterId);
      toast.success('Вы сошли с каравана');
      setConfirmLeave(false);
      await dispatch(getMe());
      onClose();
    } catch (err) {
      const msg = apiErrorMessage(err, 'Не удалось сойти с каравана');
      setLeaveError(msg);
      toast.error(msg);
      void load();
    } finally {
      leavingRef.current = false;
      setLeaving(false);
    }
  };

  const raidActive = Boolean(job?.raid_status && ACTIVE_RAID.has(job.raid_status));
  const battleLink =
    job?.battle_id != null && job.current_location_id != null ? battlePath(job.current_location_id, job.battle_id) : null;

  const icon = (
    <div className="gold-outline w-9 h-9 rounded-full bg-black/40 shrink-0 flex items-center justify-center text-lg" aria-hidden>
      🐫
    </div>
  );

  return (
    <ModalShell open onClose={onClose} title="Охрана каравана" size="lg" icon={icon} dismissible={!leaving}>
      {!loaded ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
        </div>
      ) : !job ? (
        <div className="flex flex-col items-center gap-3 py-8 text-center">
          <p className={loadError ? 'text-site-red text-sm' : 'text-white/70 text-sm'}>
            {loadError ?? 'Вы сейчас не в охране каравана.'}
          </p>
          {loadError && (
            <button type="button" className="btn-line" onClick={() => void load()}>
              Повторить
            </button>
          )}
        </div>
      ) : (
        <div className="flex flex-col gap-4 min-w-0">
          {/* Caravan, direction, state */}
          <div className="flex flex-col gap-1 min-w-0">
            <span className="text-white text-base sm:text-lg font-medium break-words">
              Караван: {job.group_name ?? job.group_code}
            </span>
            <span className="text-white/70 text-sm break-words">
              {job.from_region_name ?? '—'} <span className="text-gold/70">→</span> {job.to_region_name ?? '—'}
            </span>
            <span className={`text-sm font-medium ${ESCORT_STATE_CLS[job.state] ?? 'text-white/80'}`}>
              {stateLabel(job.state)}
              {nextMoveAt && (job.state === 'preparing' || job.state === 'on_road') && (
                <span className="text-white/70 font-normal">
                  {' — '}
                  <RemainingText
                    until={nextMoveAt}
                    prefix={job.state === 'preparing' ? 'отправится через' : 'следующий переход через'}
                    doneText="вот-вот тронется"
                  />
                </span>
              )}
            </span>
            {loadError && <p className="text-site-red text-xs">{loadError}</p>}
          </div>

          {/* Raid */}
          {job.raid_status && (
            <div
              className={`flex flex-col sm:flex-row sm:items-center gap-2 rounded-card border px-3 py-2 ${
                raidActive ? 'border-site-red/50 bg-site-red/[0.08]' : 'border-white/10 bg-white/[0.03]'
              }`}
            >
              <div className="flex flex-col min-w-0 flex-1">
                <span className={`text-sm ${raidActive ? 'text-site-red' : 'text-white/80'}`}>
                  Налёт: {ESCORT_RAID_LABEL[job.raid_status] ?? job.raid_status}
                </span>
                {raidActive && (
                  <span className="text-white/55 text-xs">
                    В бою налёта автобоя нет — ходите сами, на ход даётся 24 часа.
                  </span>
                )}
              </div>
              {battleLink && (
                <Link to={battleLink} onClick={onClose} className="btn-blue text-center text-sm !px-5 shrink-0">
                  Перейти в бой
                </Link>
              )}
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 min-w-0">
            {/* Route */}
            <section className="flex flex-col gap-2 min-w-0">
              <h3 className="gold-text text-sm sm:text-base font-medium uppercase tracking-wide">Маршрут</h3>
              <p className="text-white/60 text-xs">
                Сейчас:{' '}
                <span className="text-white">
                  {job.current_location_name ?? (job.current_location_id ? `#${job.current_location_id}` : '—')}
                </span>
                {job.route.length > 0 && ` (${job.route_index + 1} из ${job.route.length})`}
              </p>
              <CaravanEscortRoute route={job.route} routeIndex={job.route_index} />
            </section>

            {/* Escorts and pay */}
            <section className="flex flex-col gap-3 min-w-0">
              <div className="flex flex-col gap-2">
                <h3 className="gold-text text-sm sm:text-base font-medium uppercase tracking-wide">Охрана</h3>
                <span className="text-white/60 text-xs">
                  Игроков в охране: {job.escorts.length} из {job.seats_total}
                </span>
                <ul className="flex flex-col gap-1.5">
                  {job.escorts.map((m) => (
                    <li key={m.character_id} className="flex items-center gap-2 min-w-0">
                      <div className="w-7 h-7 rounded-full overflow-hidden bg-black/40 shrink-0">
                        {m.avatar ? (
                          <img src={m.avatar} alt="" className="w-full h-full object-cover" />
                        ) : (
                          <span className="w-full h-full flex items-center justify-center text-xs text-white/40" aria-hidden>
                            ?
                          </span>
                        )}
                      </div>
                      <span className={`text-sm break-words ${m.character_id === characterId ? 'text-gold' : 'text-white/85'}`}>
                        {m.name ?? `#${m.character_id}`}
                        {m.character_id === characterId && <span className="text-white/40 text-xs"> (вы)</span>}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="flex flex-col gap-0.5 rounded-card border border-white/10 bg-white/[0.03] px-3 py-2">
                <span className="text-white/50 text-[11px] uppercase tracking-wide">Плата при доставке</span>
                <span className="text-gold text-sm font-medium">~{format(job.pay_estimate)}</span>
                <span className="text-white/45 text-xs">
                  Доля от выручки продавца, делится поровну между охранниками. Ограбят — меньше; отобьётесь —
                  надбавка.
                </span>
              </div>
            </section>
          </div>

          <CaravanEscortChannel characterId={characterId} onNotEscort={reloadJob} />

          {/* Leave */}
          <section className="flex flex-col gap-2 border-t border-white/10 pt-3">
            {!confirmLeave ? (
              <button
                type="button"
                className="btn-line self-start w-full sm:w-auto"
                disabled={raidActive || leaving}
                title={raidActive ? 'Идёт бой — сойти с каравана нельзя' : undefined}
                onClick={() => {
                  setLeaveError(null);
                  setConfirmLeave(true);
                }}
              >
                Сойти с каравана
              </button>
            ) : (
              <div className="flex flex-col gap-2 rounded-card border border-site-red/40 bg-site-red/[0.06] p-3">
                <p className="text-white text-sm">Сойти с каравана?</p>
                <p className="text-white/60 text-xs">
                  Вы останетесь там, где сейчас караван. Оплаты не будет, и обратно в этот караван вас не возьмут.
                </p>
                <div className="flex flex-col sm:flex-row gap-2">
                  <button type="button" className="btn-line w-full sm:w-auto" disabled={leaving} onClick={() => setConfirmLeave(false)}>
                    Остаться
                  </button>
                  <button type="button" className="btn-blue w-full sm:w-auto !px-5" disabled={leaving} onClick={() => void leave()}>
                    {leaving ? 'Сходим...' : 'Сойти'}
                  </button>
                </div>
              </div>
            )}
            {raidActive && <p className="text-white/45 text-xs">Пока идёт бой, сойти с каравана нельзя.</p>}
            {leaveError && <p className="text-site-red text-xs">{leaveError}</p>}
          </section>
        </div>
      )}
    </ModalShell>
  );
};

export default CaravanEscortModal;
