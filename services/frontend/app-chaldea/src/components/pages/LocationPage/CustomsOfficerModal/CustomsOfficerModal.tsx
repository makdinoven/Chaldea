import { useCallback, useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { enlistCustoms, fetchCustomsOfficer, resignCustoms } from '../../../../api/customs';
import { apiErrorMessage } from '../../../../api/errors';
import { useCurrency } from '../../../../hooks/useCurrency';
import { useAppSelector } from '../../../../redux/store';
import type { CustomsOfficerView } from '../../../../types/customs';
import { formatServerDate } from '../../../../utils/serverDate';
import ModalShell from '../../../CommonComponents/ModalShell/ModalShell';
import { NPC_DIALOGUE_HINT_CUSTOMS, isNpcDialogueGateError } from '../npcDialogueGate';

interface CustomsOfficerModalProps {
  npcId: number;
  npcName: string;
  npcAvatar: string | null;
  onClose: () => void;
}

type PendingAction = 'enlist' | 'resign';

const PERCENT = 100;

/**
 * FEAT-216 — «Таможенник» NPC at a customs post: enlist in the customs service of the post's country, see one's
 * own service (seizures, earnings) and resign. An officer on watch may notice a passing contraband caravan;
 * the alert then offers «Досмотреть» in the location's caravan block.
 */
const CustomsOfficerModal = ({ npcId, npcName, npcAvatar, onClose }: CustomsOfficerModalProps) => {
  const characterId = useAppSelector((s) => s.user.character?.id ?? null) as number | null;
  const { format } = useCurrency();

  const [view, setView] = useState<CustomsOfficerView | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [gateHint, setGateHint] = useState(false);
  const [confirm, setConfirm] = useState<PendingAction | null>(null);
  const [pending, setPending] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const pendingRef = useRef(false);

  const load = useCallback(async () => {
    if (!characterId) {
      setLoading(false);
      setLoadError('Нужен персонаж, чтобы поступить на таможню');
      return;
    }
    setLoading(true);
    try {
      setView(await fetchCustomsOfficer(npcId, characterId));
      setLoadError(null);
      setGateHint(false);
    } catch (err) {
      const text = apiErrorMessage(err, 'Не удалось открыть таможенника');
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

  const run = async (action: PendingAction) => {
    if (pendingRef.current || !characterId) return;
    pendingRef.current = true;
    setPending(true);
    setActionError(null);
    try {
      if (action === 'enlist') {
        await enlistCustoms(npcId, characterId);
        toast.success('Вы поступили на службу в таможню');
      } else {
        await resignCustoms(characterId);
        toast.success('Вы оставили службу на таможне');
      }
      setConfirm(null);
    } catch (err) {
      const text = apiErrorMessage(
        err,
        action === 'enlist' ? 'Не удалось поступить на таможню' : 'Не удалось оставить службу',
      );
      setActionError(text);
      setGateHint(isNpcDialogueGateError(err));
      toast.error(text);
      setConfirm(null);
    } finally {
      pendingRef.current = false;
      setPending(false);
      void load();
    }
  };

  const icon = (
    <div className="gold-outline relative w-9 h-9 rounded-full overflow-hidden bg-black/40 shrink-0">
      {npcAvatar ? (
        <img src={npcAvatar} alt={npcName} className="w-full h-full object-cover" />
      ) : (
        <div className="w-full h-full flex items-center justify-center text-lg" aria-hidden>
          🛃
        </div>
      )}
    </div>
  );

  const hint = gateHint && <p className="text-white/60 text-xs sm:text-sm">{NPC_DIALOGUE_HINT_CUSTOMS}</p>;
  const job = view?.job ?? null;
  const country = view?.country_name ?? 'этой страны';
  /** The officer serves another country than this post's. */
  const otherCountry = Boolean(job && view && job.country_id !== view.country_id);
  const sharePct = view ? Math.round(view.params.officer_share * PERCENT) : 0;

  return (
    <ModalShell open onClose={onClose} title={npcName} size="lg" icon={icon} dismissible={!pending}>
      {loading && !view ? (
        <div className="flex items-center justify-center py-12">
          <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
        </div>
      ) : !view ? (
        <div className="flex flex-col items-center gap-3 py-8 text-center">
          <p className="text-site-red text-sm">{loadError ?? 'Не удалось открыть таможенника'}</p>
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
            Таможня страны «{country}» набирает людей на вахту. Таможенник, стоящий в пограничных локациях своей
            страны, может заметить проходящий мимо караван с контрабандой — тогда у него есть{' '}
            {view.params.alert_minutes} мин, чтобы остановить караван и досмотреть его. Бой с охраной контрабандистов
            законен. Победа — товар конфискуют, таможенникам достаётся {sharePct}% штрафа, а ещё слава и репутация у
            страны.
          </p>

          {job ? (
            <section className="flex flex-col gap-2 rounded-card border border-gold/40 bg-gold/[0.06] p-3">
              <h3 className="gold-text text-sm sm:text-base font-medium uppercase tracking-wide">Ваша служба</h3>
              <span className="text-white text-sm break-words">
                Таможня: {job.country_name ?? '—'}
                {otherCountry && <span className="text-white/50"> (не этой страны)</span>}
              </span>
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-white/70 text-xs sm:text-sm">
                <span>На службе с {formatServerDate(job.enlisted_at)}</span>
                <span>
                  Конфискаций: <span className="text-white font-medium">{job.seizures}</span>
                </span>
                <span>
                  Заработано: <span className="text-gold font-medium">{format(job.earned)}</span>
                </span>
              </div>
              <button
                type="button"
                className="btn-line w-full sm:w-auto sm:self-start"
                disabled={pending}
                onClick={() => {
                  setActionError(null);
                  setConfirm('resign');
                }}
              >
                Оставить службу
              </button>
            </section>
          ) : (
            <section className="flex flex-col gap-2">
              {!view.can_enlist && view.reason && (
                <p className="text-white/60 text-xs sm:text-sm break-words">{view.reason}</p>
              )}
              <button
                type="button"
                className="btn-blue w-full sm:w-auto sm:self-start !px-6"
                disabled={!view.can_enlist || pending}
                onClick={() => {
                  setActionError(null);
                  setConfirm('enlist');
                }}
              >
                Поступить на таможню
              </button>
            </section>
          )}

          {actionError && <p className="text-site-red text-xs sm:text-sm">{actionError}</p>}
          {hint}
        </div>
      )}

      <ModalShell
        open={confirm !== null}
        onClose={() => !pending && setConfirm(null)}
        title={confirm === 'resign' ? 'Оставить службу?' : 'Поступить на таможню?'}
        size="sm"
        dismissible={!pending}
        footer={
          <>
            <button
              type="button"
              className="btn-line w-full sm:w-auto sm:max-w-[160px]"
              disabled={pending}
              onClick={() => setConfirm(null)}
            >
              Отмена
            </button>
            <button
              type="button"
              className="btn-blue w-full sm:w-auto"
              disabled={pending}
              onClick={() => confirm && void run(confirm)}
            >
              {pending ? 'Минутку...' : confirm === 'resign' ? 'Оставить' : 'Поступить'}
            </button>
          </>
        }
      >
        {confirm === 'resign' ? (
          <p className="text-white/80 text-sm">
            Вы перестанете замечать контрабанду. Заработанное останется при вас; вернуться на службу можно позже у таможенника.
          </p>
        ) : (
          <ul className="flex flex-col gap-1.5 text-white/80 text-sm list-disc pl-5">
            <li>Вахта идёт сама, пока вы находитесь в локациях страны «{country}», куда заходят караваны.</li>
            <li>Заметили контрабанду — придёт уведомление, а в локации появится кнопка «Досмотреть».</li>
            <li>Таможенник не может наниматься в охрану контрабанды.</li>
          </ul>
        )}
      </ModalShell>
    </ModalShell>
  );
};

export default CustomsOfficerModal;
