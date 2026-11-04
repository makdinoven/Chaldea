import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import { postShadowClose, postShadowReveal, type ShadowCrime } from '../../../api/shadowAdmin';
import { LAW_REASON_MAX, LAW_REASON_MIN } from '../../../api/lawAdmin';
import { newRequestId } from '../../../api/reputationAdmin';
import { apiErrorMessage } from '../../../api/errors';

export type CrimeAction = 'reveal' | 'close';

/** The minimal crime info the dialog needs (a `ShadowCrime` or a character-card crime row). */
export interface CrimeActionTarget {
  id: number;
  title: string;
}

interface CrimeActionModalProps {
  target: CrimeActionTarget | null;
  action: CrimeAction;
  onClose: () => void;
  /** Called after a successful reveal / close with the updated row. */
  onDone: (crime: ShadowCrime) => void;
}

const LABEL = 'text-white/50 text-xs font-medium uppercase tracking-[0.06em]';

const TEXTS: Record<CrimeAction, { title: string; button: string; busy: string; hint: string; error: string }> = {
  reveal: {
    title: 'Раскрыть преступление',
    button: 'Раскрыть',
    busy: 'Раскрытие...',
    hint: 'Стража узнает, кто это был: отложенные репутация и розыск применятся один раз, игрок получит уведомление.',
    error: 'Не удалось раскрыть преступление',
  },
  close: {
    title: 'Закрыть дело',
    button: 'Закрыть дело',
    busy: 'Закрытие...',
    hint: 'Дело закроется навсегда без последствий для персонажа. Игрок уведомления не получит.',
    error: 'Не удалось закрыть дело',
  },
};

/** FEAT-199 staff reveal / close of a deferred crime with a mandatory reason; a new `request_id` per submit. */
const CrimeActionModal = ({ target, action, onClose, onDone }: CrimeActionModalProps) => {
  const [reason, setReason] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const t = TEXTS[action];

  useEffect(() => {
    if (target) {
      setReason('');
      setError(null);
    }
  }, [target, action]);

  const submit = async () => {
    if (!target) return;
    const r = reason.trim();
    if (r.length < LAW_REASON_MIN) {
      setError(`Причина обязательна — не короче ${LAW_REASON_MIN} символов`);
      return;
    }
    if (r.length > LAW_REASON_MAX) {
      setError(`Причина — не длиннее ${LAW_REASON_MAX} символов`);
      return;
    }
    setError(null);
    setSubmitting(true);
    try {
      const body = { reason: r, request_id: newRequestId() };
      const result = action === 'reveal' ? await postShadowReveal(target.id, body) : await postShadowClose(target.id, body);
      toast.success(result.message);
      onDone(result.crime);
      onClose();
    } catch (e) {
      const msg = apiErrorMessage(e, t.error);
      setError(msg);
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ModalShell
      open={target !== null}
      onClose={onClose}
      title={t.title}
      size="sm"
      dismissible={!submitting}
      footer={
        <div className="flex flex-col-reverse sm:flex-row sm:justify-end gap-2">
          <button type="button" className="btn-line w-full sm:w-auto !px-6" disabled={submitting} onClick={onClose}>
            Отмена
          </button>
          <button type="button" className="btn-blue w-full sm:w-auto !px-6 disabled:opacity-50"
            disabled={submitting || reason.trim().length < LAW_REASON_MIN} onClick={() => void submit()}>
            {submitting ? t.busy : t.button}
          </button>
        </div>
      }
    >
      <div className="flex flex-col gap-3">
        {target && <p className="text-white text-sm break-words">{target.title}</p>}
        <p className="text-white/50 text-sm">{t.hint}</p>
        <label className="flex flex-col gap-1">
          <span className={LABEL}>Причина (обязательно)</span>
          <textarea className="textarea-bordered text-sm" rows={3} maxLength={LAW_REASON_MAX} value={reason}
            disabled={submitting} placeholder="Почему принято решение — видно только в админке"
            onChange={(e) => setReason(e.target.value)} />
          <span className="text-white/40 text-xs self-end">{reason.trim().length}/{LAW_REASON_MAX}</span>
        </label>
        {error && <p className="text-site-red text-sm">{error}</p>}
      </div>
    </ModalShell>
  );
};

export default CrimeActionModal;
