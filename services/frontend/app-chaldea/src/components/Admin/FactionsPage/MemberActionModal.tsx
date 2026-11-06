import { useState } from 'react';
import toast from 'react-hot-toast';
import { Coins, UserX } from 'lucide-react';
import { FACTION_LIMITS, adminExpelMember, adminMemberPoints } from '../../../api/factions';
import { apiErrorMessage } from '../../../api/errors';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import { FIELD, LABEL, SIGNED_INT_RE, toInt } from './adminShared';

export interface MemberActionTarget {
  mode: 'points' | 'expel';
  membershipId: number;
  characterName: string;
  factionName: string;
  points: number;
}

/** Admin: points ± with a reason (no hostility penalty), or expel with a reason (same as leaving). */
const MemberActionModal = ({ target, onClose, onDone }: { target: MemberActionTarget | null; onClose: () => void; onDone: () => void }) => {
  const [delta, setDelta] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const mode = target?.mode ?? 'points';

  const close = () => {
    setDelta('');
    setReason('');
    onClose();
  };

  const submit = async () => {
    if (!target) return;
    const why = reason.trim();
    if (why.length < FACTION_LIMITS.reasonMin || why.length > FACTION_LIMITS.reasonMax) {
      toast.error(`Причина: от ${FACTION_LIMITS.reasonMin} до ${FACTION_LIMITS.reasonMax} символов`);
      return;
    }
    setBusy(true);
    try {
      if (mode === 'points') {
        const d = toInt(delta);
        if (d == null || d === 0 || Math.abs(d) > FACTION_LIMITS.adminDeltaMax) {
          toast.error(`Изменение очков: от −${FACTION_LIMITS.adminDeltaMax} до ${FACTION_LIMITS.adminDeltaMax}, не 0`);
          return;
        }
        const r = await adminMemberPoints(target.membershipId, d, why);
        toast.success(`Очки изменены: ${r.points_delta > 0 ? '+' : ''}${r.points_delta}, теперь ${r.points_after}`);
      } else {
        await adminExpelMember(target.membershipId, why);
        toast.success(`${target.characterName} исключён из фракции`);
      }
      setDelta('');
      setReason('');
      onDone();
    } catch (e) {
      toast.error(apiErrorMessage(e, mode === 'points' ? 'Не удалось изменить очки' : 'Не удалось исключить'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <ModalShell
      open={target !== null}
      onClose={close}
      title={mode === 'points' ? 'Очки фракции' : 'Исключение'}
      icon={
        mode === 'points' ? (
          <Coins size={18} strokeWidth={1.8} className="text-gold shrink-0" />
        ) : (
          <UserX size={18} strokeWidth={1.8} className="text-gold shrink-0" />
        )
      }
      size="sm"
      dismissible={!busy}
      footer={
        <>
          <button type="button" className="btn-line w-full sm:w-auto" onClick={close} disabled={busy}>
            Отмена
          </button>
          <button type="button" className="btn-blue w-full sm:w-auto disabled:opacity-50" onClick={() => void submit()} disabled={busy}>
            {mode === 'points' ? 'Применить' : 'Исключить'}
          </button>
        </>
      }
    >
      {target && (
        <div className="flex flex-col gap-4">
          <p className="text-white/80 text-sm">
            {target.characterName} · <span className="text-gold">«{target.factionName}»</span> · сейчас очков: {target.points}
          </p>
          {mode === 'points' ? (
            <label className="flex flex-col gap-1">
              <span className={LABEL}>Изменение (+ или −)</span>
              <input inputMode="numeric" value={delta} onChange={(e) => SIGNED_INT_RE.test(e.target.value) && setDelta(e.target.value)} className={FIELD} placeholder="например, 50 или -20" />
              <span className="text-white/40 text-xs">Без штрафа враждебным фракциям; звание проверится автоматически.</span>
            </label>
          ) : (
            <p className="text-white/60 text-xs">
              Как при выходе: часть очков сгорает, повторно вступить можно только после срока из настроек.
            </p>
          )}
          <label className="flex flex-col gap-1">
            <span className={LABEL}>Причина (увидит игрок)</span>
            <textarea value={reason} maxLength={FACTION_LIMITS.reasonMax} onChange={(e) => setReason(e.target.value)} rows={3} className="textarea-bordered text-sm" />
          </label>
        </div>
      )}
    </ModalShell>
  );
};

export default MemberActionModal;
