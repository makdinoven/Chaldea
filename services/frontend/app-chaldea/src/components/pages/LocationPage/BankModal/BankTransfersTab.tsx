import { useState } from 'react';
import toast from 'react-hot-toast';
import { bankSend, bankTransfer } from '../../../../api/bank';
import { useCurrency } from '../../../../hooks/useCurrency';
import type { BankRegion } from '../../../../types/bank';
import ConfirmationModal from '../../../ui/ConfirmationModal';
import { parseAmount, percent, regionLabel, transferFee } from './bankFormat';
import {
  AmountInput,
  BankCard,
  BankSection,
  Choice,
  SELECT_CLASS,
  SmallButton,
  type BankTabProps,
} from './BankParts';

const regionOption = (r: BankRegion): string => (r.country_name ? `${r.name} (${r.country_name})` : r.name);

/** «wallet» or a demand deposit id as a string (select value). */
type SendSource = 'wallet' | string;

interface SendDraft {
  source: SendSource;
  recipient: string;
  regionId: number;
  amount: number;
  fee: number;
}

const BankTransfersTab = ({ view, characterId, npcId, pending, run }: BankTabProps) => {
  const { format, forms } = useCurrency();
  const { rates } = view;
  const demand = view.deposits.filter((d) => d.kind === 'demand');
  const fee = (amount: number) => transferFee(amount, rates.transfer_fee_rate, rates.transfer_fee_min);
  const feeHint = `Комиссия ${percent(rates.transfer_fee_rate)} %, не меньше ${format(rates.transfer_fee_min, true)} — в казну региона банкира.`;

  /* ── Own deposit → another bank ── */
  const [moveFrom, setMoveFrom] = useState<string>('');
  const moveDeposit = demand.find((d) => String(d.id) === moveFrom) ?? demand[0] ?? null;
  const moveTargets = view.bank_regions.filter((r) => r.region_id !== moveDeposit?.region_id);
  const [moveTo, setMoveTo] = useState<string>('');
  const moveToId = moveTargets.some((r) => String(r.region_id) === moveTo)
    ? Number(moveTo)
    : (moveTargets[0]?.region_id ?? 0);
  const [moveAmount, setMoveAmount] = useState('');
  const moveN = parseAmount(moveAmount);

  const doMove = async () => {
    if (!moveDeposit || !moveToId) return;
    if (moveN < 1) {
      toast.error('Укажите сумму');
      return;
    }
    if (moveN + fee(moveN) > moveDeposit.amount) {
      toast.error(`На вкладе недостаточно средств с учётом комиссии ${format(fee(moveN), true)}`);
      return;
    }
    const ok = await run(
      (request_id) =>
        bankTransfer(npcId, {
          character_id: characterId,
          deposit_id: moveDeposit.id,
          to_region_id: moveToId,
          amount: moveN,
          request_id,
        }),
      'Не удалось перевести вклад',
    );
    if (ok) setMoveAmount('');
  };

  /* ── To another player ── */
  const [sendSource, setSendSource] = useState<SendSource>('wallet');
  const sendDeposit = sendSource === 'wallet' ? null : (demand.find((d) => String(d.id) === sendSource) ?? null);
  const effectiveSource: SendSource = sendDeposit ? sendSource : 'wallet';
  const [recipient, setRecipient] = useState('');
  const [sendTo, setSendTo] = useState<string>('');
  const sendToId = view.bank_regions.some((r) => String(r.region_id) === sendTo)
    ? Number(sendTo)
    : (view.bank_regions.find((r) => r.region_id === view.region_id)?.region_id ??
      view.bank_regions[0]?.region_id ??
      0);
  const [sendAmount, setSendAmount] = useState('');
  const sendN = parseAmount(sendAmount);
  const sendAvailable = sendDeposit ? sendDeposit.amount : view.wallet;
  const [confirm, setConfirm] = useState<SendDraft | null>(null);

  const requestSend = () => {
    const name = recipient.trim();
    if (!name) {
      toast.error('Укажите имя получателя');
      return;
    }
    if (!sendToId) {
      toast.error('Выберите банк получателя');
      return;
    }
    if (sendN < 1) {
      toast.error('Укажите сумму');
      return;
    }
    const f = fee(sendN);
    if (sendN + f > sendAvailable) {
      toast.error(
        sendDeposit
          ? `На вкладе недостаточно средств с учётом комиссии ${format(f, true)}`
          : `Недостаточно ${forms.genitive} с учётом комиссии ${format(f, true)}`,
      );
      return;
    }
    setConfirm({ source: effectiveSource, recipient: name, regionId: sendToId, amount: sendN, fee: f });
  };

  const doSend = async (draft: SendDraft) => {
    const ok = await run(
      (request_id) =>
        bankSend(npcId, {
          character_id: characterId,
          source: draft.source === 'wallet' ? 'wallet' : 'deposit',
          deposit_id: draft.source === 'wallet' ? null : Number(draft.source),
          recipient_name: draft.recipient,
          to_region_id: draft.regionId,
          amount: draft.amount,
          request_id,
        }),
      'Не удалось отправить перевод',
    );
    if (ok) {
      setSendAmount('');
      setRecipient('');
    }
  };

  const regionName = (id: number) => {
    const r = view.bank_regions.find((x) => x.region_id === id);
    return r ? r.name : `#${id}`;
  };

  if (view.bank_regions.length === 0) {
    return <p className="text-white/50 text-sm">Сейчас ни один банк не принимает переводы.</p>;
  }

  return (
    <div className="flex flex-col gap-5 min-w-0">
      <p className="text-white/50 text-xs">{feeHint}</p>

      <BankSection title="В другой банк">
        <BankCard>
          {demand.length === 0 ? (
            <p className="text-white/50 text-sm">
              Перевести можно только вклад до востребования — у вас его нет.
            </p>
          ) : moveTargets.length === 0 ? (
            <p className="text-white/50 text-sm">Других банков, принимающих вклады, сейчас нет.</p>
          ) : (
            <>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                <label className="flex flex-col gap-0.5 min-w-0">
                  <span className="text-white/50 text-[11px] uppercase tracking-wide">Откуда</span>
                  <select
                    value={moveDeposit ? String(moveDeposit.id) : ''}
                    onChange={(e) => setMoveFrom(e.target.value)}
                    disabled={pending}
                    className={SELECT_CLASS}
                  >
                    {demand.map((d) => (
                      <option key={d.id} value={String(d.id)}>
                        {regionLabel(d.region_name)} — {format(d.amount, true)}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex flex-col gap-0.5 min-w-0">
                  <span className="text-white/50 text-[11px] uppercase tracking-wide">Куда</span>
                  <select
                    value={String(moveToId)}
                    onChange={(e) => setMoveTo(e.target.value)}
                    disabled={pending}
                    className={SELECT_CLASS}
                  >
                    {moveTargets.map((r) => (
                      <option key={r.region_id} value={String(r.region_id)}>
                        {regionOption(r)}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="flex flex-wrap items-end gap-2">
                <AmountInput value={moveAmount} onChange={setMoveAmount} disabled={pending} />
                <SmallButton onClick={() => void doMove()} disabled={pending || moveN < 1}>
                  Перевести
                </SmallButton>
              </div>
              {moveN > 0 && (
                <span className="text-white/50 text-xs">
                  Комиссия {format(fee(moveN), true)} · со вклада спишется {format(moveN + fee(moveN), true)}
                </span>
              )}
            </>
          )}
        </BankCard>
      </BankSection>

      <BankSection title="Другому игроку">
        <BankCard>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <label className="flex flex-col gap-0.5 min-w-0">
              <span className="text-white/50 text-[11px] uppercase tracking-wide">Получатель</span>
              <input
                type="text"
                value={recipient}
                maxLength={255}
                onChange={(e) => setRecipient(e.target.value)}
                disabled={pending}
                placeholder="Имя персонажа"
                className="input-underline !text-sm w-full min-w-0"
              />
            </label>
            <label className="flex flex-col gap-0.5 min-w-0">
              <span className="text-white/50 text-[11px] uppercase tracking-wide">На вклад в банке</span>
              <select
                value={String(sendToId)}
                onChange={(e) => setSendTo(e.target.value)}
                disabled={pending}
                className={SELECT_CLASS}
              >
                {view.bank_regions.map((r) => (
                  <option key={r.region_id} value={String(r.region_id)}>
                    {regionOption(r)}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="flex flex-col gap-1">
            <span className="text-white/50 text-[11px] uppercase tracking-wide">Списать с</span>
            <Choice<SendSource>
              value={effectiveSource}
              onChange={setSendSource}
              disabled={pending}
              options={[
                { value: 'wallet', label: `Кошелёк (${format(view.wallet, true)})` },
                ...demand.map((d) => ({
                  value: String(d.id),
                  label: `Вклад: ${regionLabel(d.region_name)} (${format(d.amount, true)})`,
                })),
              ]}
            />
          </div>
          <div className="flex flex-wrap items-end gap-2">
            <AmountInput value={sendAmount} onChange={setSendAmount} disabled={pending} />
            <SmallButton onClick={requestSend} disabled={pending || sendN < 1 || !recipient.trim()}>
              Отправить
            </SmallButton>
          </div>
          {sendN > 0 && (
            <span className="text-white/50 text-xs">
              Комиссия {format(fee(sendN), true)} · всего спишется {format(sendN + fee(sendN), true)}
            </span>
          )}
        </BankCard>
      </BankSection>

      <ConfirmationModal
        isOpen={confirm !== null}
        title="Отправить перевод?"
        message={
          confirm
            ? `${format(confirm.amount, true)} → «${confirm.recipient}», на вклад в банке региона «${regionName(
                confirm.regionId,
              )}». Комиссия ${format(confirm.fee, true)}.`
            : ''
        }
        onCancel={() => setConfirm(null)}
        onConfirm={() => {
          const draft = confirm;
          setConfirm(null);
          if (draft) void doSend(draft);
        }}
      />
    </div>
  );
};

export default BankTransfersTab;
