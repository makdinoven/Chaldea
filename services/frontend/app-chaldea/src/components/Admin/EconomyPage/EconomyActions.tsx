import { useState } from 'react';
import toast from 'react-hot-toast';
import { postEconomyAdjust, postEconomyEmission } from '../../../api/economyAdmin';
import { apiErrorMessage } from '../../../api/errors';
import { useCurrency } from '../../../hooks/useCurrency';
import ConfirmDialog from '../../pages/LocationPage/ConfirmDialog';
import type { EconAccount } from '../../../types/economy';
import AccountPicker from './AccountPicker';
import { ADJUST_KINDS, EMISSION_KINDS } from './economyLabels';

const MAX_AMOUNT = 1_000_000_000_000;
const COMMENT_MIN = 3;
const COMMENT_MAX = 500;

type Mode = 'emission' | 'adjust';

interface ActionFormProps {
  mode: Mode;
  onDone: () => void;
}

const ActionForm = ({ mode, onDone }: ActionFormProps) => {
  const { format } = useCurrency();
  const [account, setAccount] = useState<EconAccount | null>(null);
  const [amountText, setAmountText] = useState('');
  const [direction, setDirection] = useState<1 | -1>(1);
  const [comment, setComment] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  const isEmission = mode === 'emission';
  const amount = Number(amountText);
  const amountValid = Number.isInteger(amount) && amount >= 1 && amount <= MAX_AMOUNT;
  const commentTrimmed = comment.trim();
  const commentValid = commentTrimmed.length >= COMMENT_MIN && commentTrimmed.length <= COMMENT_MAX;
  const delta = isEmission ? amount : amount * direction;
  const canSubmit = Boolean(account) && amountValid && commentValid && !busy;

  const submit = async () => {
    if (!account) return;
    setConfirming(false);
    setBusy(true);
    try {
      const result = isEmission
        ? await postEconomyEmission({ account_id: account.account_id, amount, comment: commentTrimmed })
        : await postEconomyAdjust({ account_id: account.account_id, delta, comment: commentTrimmed });
      toast.success(
        `${isEmission ? 'Эмиссия проведена' : 'Корректировка проведена'}. Баланс счёта: ${format(result.balance)}`,
      );
      setAccount(null);
      setAmountText('');
      setComment('');
      setDirection(1);
      onDone();
    } catch (e) {
      toast.error(apiErrorMessage(e, isEmission ? 'Не удалось провести эмиссию' : 'Не удалось провести корректировку'));
    } finally {
      setBusy(false);
    }
  };

  const idPrefix = `econ-${mode}`;

  return (
    <section className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-4 min-w-0">
      <div className="flex flex-col gap-1">
        <h2 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">
          {isEmission ? 'Эмиссия' : 'Корректировка'}
        </h2>
        <p className="text-white/50 text-sm">
          {isEmission
            ? 'Выпуск новых денег в казну региона, страны или в Казну Скитальцев. Налог не удерживается.'
            : 'Ручное начисление или списание на счёт персонажа или казны — через счёт «Корректировки».'}
        </p>
      </div>

      <AccountPicker
        kinds={isEmission ? EMISSION_KINDS : ADJUST_KINDS}
        value={account}
        onChange={setAccount}
        label="Счёт"
        inputId={`${idPrefix}-account`}
      />

      {!isEmission && (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => setDirection(1)}
            className={`chip-outline rounded-full px-4 py-1.5 text-xs font-medium ${direction === 1 ? 'chip-outline-active' : ''}`}
          >
            Начислить
          </button>
          <button
            type="button"
            onClick={() => setDirection(-1)}
            className={`chip-outline rounded-full px-4 py-1.5 text-xs font-medium ${direction === -1 ? 'chip-outline-active' : ''}`}
          >
            Списать
          </button>
        </div>
      )}

      <div className="flex flex-col gap-1">
        <label htmlFor={`${idPrefix}-amount`} className="text-white/60 text-xs uppercase tracking-[0.06em]">
          Сумма
        </label>
        <input
          id={`${idPrefix}-amount`}
          type="number"
          inputMode="numeric"
          min={1}
          max={MAX_AMOUNT}
          step={1}
          className="input-underline w-full sm:max-w-[240px]"
          value={amountText}
          onChange={(e) => setAmountText(e.target.value)}
          placeholder="Например, 1000"
        />
        {amountText !== '' && !amountValid && (
          <p className="text-site-red text-xs">Целое число от 1 до 1 000 000 000 000</p>
        )}
        {amountValid && <p className="text-white/40 text-xs">{format(amount)}</p>}
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor={`${idPrefix}-comment`} className="text-white/60 text-xs uppercase tracking-[0.06em]">
          Комментарий (обязательно)
        </label>
        <textarea
          id={`${idPrefix}-comment`}
          className="textarea-bordered w-full"
          rows={3}
          maxLength={COMMENT_MAX}
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Причина: попадёт в журнал операций"
        />
        {comment !== '' && !commentValid && (
          <p className="text-site-red text-xs">От {COMMENT_MIN} до {COMMENT_MAX} символов</p>
        )}
      </div>

      <button
        type="button"
        className="btn-blue w-full sm:w-auto sm:self-start !px-6"
        disabled={!canSubmit}
        onClick={() => setConfirming(true)}
      >
        {busy ? 'Проведение...' : isEmission ? 'Провести эмиссию' : 'Провести корректировку'}
      </button>

      {confirming && account && (
        <ConfirmDialog
          title={isEmission ? 'Подтвердите эмиссию' : 'Подтвердите корректировку'}
          message={
            isEmission
              ? `Выпустить ${format(amount)} в «${account.name ?? `#${account.account_id}`}»? Общая сумма денег в мире вырастет.`
              : `${direction === 1 ? 'Начислить' : 'Списать'} ${format(amount)} ${direction === 1 ? 'на счёт' : 'со счёта'} «${
                  account.name ?? `#${account.account_id}`
                }»? Сейчас на счёте ${format(account.balance)}.`
          }
          confirmLabel={isEmission ? 'Выпустить' : direction === 1 ? 'Начислить' : 'Списать'}
          danger={!isEmission && direction === -1}
          onConfirm={submit}
          onCancel={() => setConfirming(false)}
        />
      )}
    </section>
  );
};

interface EconomyActionsProps {
  canEmit: boolean;
  canAdjust: boolean;
  onDone: () => void;
}

/** Admin money actions: emission (economy:emit) and adjustment (economy:adjust). */
const EconomyActions = ({ canEmit, canAdjust, onDone }: EconomyActionsProps) => (
  <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
    {canEmit && <ActionForm mode="emission" onDone={onDone} />}
    {canAdjust && <ActionForm mode="adjust" onDone={onDone} />}
  </div>
);

export default EconomyActions;
