import { useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import {
  MAX_REJECTION_REASON_LENGTH,
  approveCharacterRequest,
  rejectCharacterRequest,
} from '../../../api/characterRequests';
import type { OriginCountry } from '../../../api/origins';
import CharacterPassport, {
  fromModerationRequest,
} from '../../CommonComponents/CharacterPassport';

/**
 * FEAT-154 (task #21) — the moderator's view of one character request.
 *
 * The ad-hoc avatar + three text blocks are replaced by the shared
 * `CharacterPassport` (rule 26): the moderator now judges exactly the document
 * the player will carry, including the «редкий выбор» badge for an origin that
 * is untypical for the chosen subrace (rule 11).
 *
 * Rejection now carries a reason (rule 28), entered in a modal and capped at
 * `MAX_REJECTION_REASON_LENGTH` in the UI so the 400 of rule 30b is never hit.
 */

/**
 * One moderation row. The FEAT-154 keys are optional because
 * `GET /characters/moderation-requests` does not serialize them yet — the
 * passport simply prints «—» for whatever is missing.
 */
export interface RequestData {
  request_id: number;
  name: string;
  avatar: string | null;
  biography: string | null;
  background: string | null;
  appearance: string | null;
  personality?: string | null;
  race_name: string | null;
  subrace_name: string | null;
  class_name: string | null;
  age: number | null;
  height: string | null;
  weight?: string | null;
  sex: string | null;
  status?: string | null;
  created_at?: string | null;
  character_id?: number | null;
  id_subrace?: number | null;
  // FEAT-154 additive keys
  origin_id?: number | null;
  start_location_id?: number | null;
  skitaltsy_since_year?: number | null;
  skitaltsy_since_segment?: number | null;
  rejection_reason?: string | null;
}

interface RequestProps {
  data: RequestData;
  requestType?: string;
  onStatusChange?: (requestId: number) => void;
  /** Origin registry, loaded ONCE by the page — never per request row. */
  origins?: readonly OriginCountry[] | null;
  /** `typical_origin_ids` of this request's subrace — drives the rare badge. */
  typicalOriginIds?: readonly number[] | null;
  /** Name of `start_location_id`, resolved by the page from the curated list. */
  startLocationName?: string | null;
  /** In-game year from `selectCurrentGameYear`. Never a literal. */
  currentGameYear?: number | null;
}

/** Ink-language action button — the passport sheet is parchment, not dark UI. */
const PassportAction = ({
  text,
  onClick,
  disabled = false,
  tone = 'neutral',
}: {
  text: string;
  onClick: () => void;
  disabled?: boolean;
  tone?: 'neutral' | 'danger';
}) => (
  <button
    type="button"
    onClick={onClick}
    disabled={disabled}
    className={`
      font-lore rounded-card border px-5 py-2 text-base
      transition-colors duration-200 ease-site
      disabled:cursor-not-allowed disabled:opacity-50
      ${
        tone === 'danger'
          ? 'border-[#8b1a1a]/50 text-[#8b1a1a] hover:bg-[#8b1a1a]/10'
          : 'border-ink/40 text-ink hover:bg-ink/10'
      }
    `}
  >
    {text}
  </button>
);

const Request = ({
  data,
  requestType,
  onStatusChange,
  origins,
  typicalOriginIds,
  startLocationName,
  currentGameYear = null,
}: RequestProps) => {
  const isClaim = requestType === 'claim';

  const [busy, setBusy] = useState(false);
  const [rejectOpen, setRejectOpen] = useState(false);
  const [reason, setReason] = useState('');

  const passport = useMemo(
    () =>
      fromModerationRequest(
        { ...data, id: data.request_id },
        { origins, typicalOriginIds, startLocationName },
      ),
    [data, origins, typicalOriginIds, startLocationName],
  );

  const handleApprove = async () => {
    setBusy(true);
    try {
      const result = await approveCharacterRequest(data.request_id);
      toast.success(result.message || 'Заявка одобрена');
      // The backend degrades the start location instead of failing (§3.6).
      if (result.location_warning) toast(result.location_warning, { icon: '⚠️' });
      onStatusChange?.(data.request_id);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Не удалось одобрить заявку');
    } finally {
      setBusy(false);
    }
  };

  const handleReject = async () => {
    const trimmed = reason.trim();
    setBusy(true);
    try {
      const result = await rejectCharacterRequest(data.request_id, trimmed || null);
      toast.success(result.message || 'Заявка отклонена');
      setRejectOpen(false);
      setReason('');
      onStatusChange?.(data.request_id);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Не удалось отклонить заявку');
    } finally {
      setBusy(false);
    }
  };

  const footer = (
    <div className="flex flex-col gap-3 sm:flex-row sm:justify-end">
      <PassportAction text="Одобрить" onClick={handleApprove} disabled={busy} />
      <PassportAction
        text="Отклонить"
        tone="danger"
        onClick={() => setRejectOpen(true)}
        disabled={busy}
      />
    </div>
  );

  const remaining = MAX_REJECTION_REASON_LENGTH - reason.length;

  return (
    <div className="flex w-full flex-col gap-3">
      {isClaim && (
        <div className="gray-bg flex flex-col gap-1 p-4">
          <h3 className="gold-text text-base font-medium uppercase sm:text-lg">
            Заявка на присвоение персонажа
          </h3>
          <p className="text-white text-sm">
            Игрок хочет получить персонажа{' '}
            <span className="text-gold font-medium">{data.name}</span>
          </p>
        </div>
      )}

      <CharacterPassport
        data={passport}
        variant="full"
        currentGameYear={currentGameYear}
        // The moderator judges the whole record, first posting included.
        audience="self"
        footer={footer}
      />

      {rejectOpen && (
        <div className="modal-overlay" onClick={() => !busy && setRejectOpen(false)}>
          <div
            className="modal-content gold-outline gold-outline-thick relative mx-4 w-full max-w-lg"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="gold-text mb-4 text-lg font-medium uppercase sm:text-xl">
              Отклонить заявку
            </h2>
            <p className="text-white/70 mb-3 text-sm">
              Причина будет отправлена игроку вместе с уведомлением. Поле можно оставить пустым.
            </p>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value.slice(0, MAX_REJECTION_REASON_LENGTH))}
              maxLength={MAX_REJECTION_REASON_LENGTH}
              rows={5}
              placeholder="Например: описание внешности не соответствует выбранной подрасе"
              className="textarea-bordered w-full !text-sm"
            />
            <p
              className={`mt-1 text-right text-xs ${
                remaining === 0 ? 'text-site-red' : 'text-white/40'
              }`}
            >
              Осталось символов: {remaining}
            </p>
            <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:justify-center">
              <button
                type="button"
                onClick={handleReject}
                disabled={busy}
                className="btn-blue !text-sm disabled:opacity-50"
              >
                {busy ? 'Отправка...' : 'Отклонить заявку'}
              </button>
              <button
                type="button"
                onClick={() => setRejectOpen(false)}
                disabled={busy}
                className="btn-line !text-sm disabled:opacity-50"
              >
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Request;
