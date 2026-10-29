import { useState } from 'react';
import toast from 'react-hot-toast';
import { bankDeposit, bankTransfer, bankWithdraw } from '../../../../api/bank';
import { useCurrency } from '../../../../hooks/useCurrency';
import type { BankDeposit, BankTerm } from '../../../../types/bank';
import { formatServerDateTime } from '../../../../utils/serverDate';
import ConfirmationModal from '../../../ui/ConfirmationModal';
import {
  demandRateText,
  parseAmount,
  regionLabel,
  termInterest,
  termRateText,
  transferFee,
  weekInterest,
} from './bankFormat';
import {
  AmountInput,
  BankCard,
  BankLine,
  BankSection,
  Choice,
  SmallButton,
  type BankTabProps,
} from './BankParts';

type OpenKind = 'demand' | BankTerm;

/** Largest amount that fits into `total` together with its transfer commission. */
const maxWithFee = (total: number, feeRate: number, feeMin: number): number => {
  let a = Math.floor(total / (1 + feeRate));
  while (a > 0 && a + transferFee(a, feeRate, feeMin) > total) a -= 1;
  return Math.max(0, a);
};

const BankDepositsTab = ({ view, characterId, npcId, pending, run }: BankTabProps) => {
  const { format, forms } = useCurrency();
  const { rates } = view;
  const here = view.deposits.filter((d) => d.here);
  const elsewhere = view.deposits.filter((d) => !d.here);
  const demandHere = here.find((d) => d.kind === 'demand') ?? null;
  const termsHere = here.filter((d) => d.kind === 'term');

  const [demandAmount, setDemandAmount] = useState('');
  const [openKind, setOpenKind] = useState<OpenKind>('demand');
  const [openAmount, setOpenAmount] = useState('');
  const [moveAmounts, setMoveAmounts] = useState<Record<number, string>>({});
  const [earlyClose, setEarlyClose] = useState<BankDeposit | null>(null);

  const termRate = (term: number): number | null =>
    rates.term_rates.find((t) => t.term_days === term)?.rate_day ?? null;
  const termOptions = rates.term_rates.map((t) => t.term_days as BankTerm);

  const checkMin = (amount: number): boolean => {
    if (amount < 1) {
      toast.error('Укажите сумму');
      return false;
    }
    if (amount < rates.min_amount) {
      toast.error(`Минимальная сумма — ${format(rates.min_amount, true)}`);
      return false;
    }
    return true;
  };

  /* ── Demand deposit here: top up / withdraw ── */

  const topUp = async () => {
    const amount = parseAmount(demandAmount);
    if (!checkMin(amount)) return;
    if (amount > view.wallet) {
      toast.error(`Недостаточно ${forms.genitive}`);
      return;
    }
    const ok = await run(
      (request_id) => bankDeposit(npcId, { character_id: characterId, kind: 'demand', amount, request_id }),
      'Не удалось положить деньги на вклад',
    );
    if (ok) setDemandAmount('');
  };

  const withdrawDemand = async () => {
    if (!demandHere) return;
    const amount = parseAmount(demandAmount);
    if (amount < 1) {
      toast.error('Укажите сумму');
      return;
    }
    if (amount > demandHere.amount) {
      toast.error('На вкладе меньше денег');
      return;
    }
    const ok = await run(
      (request_id) =>
        bankWithdraw(npcId, { character_id: characterId, deposit_id: demandHere.id, amount, request_id }),
      'Не удалось снять деньги со вклада',
    );
    if (ok) setDemandAmount('');
  };

  /* ── Term deposits here ── */

  const withdrawTerm = (d: BankDeposit) =>
    run(
      (request_id) => bankWithdraw(npcId, { character_id: characterId, deposit_id: d.id, request_id }),
      d.matured ? 'Не удалось забрать вклад' : 'Не удалось закрыть вклад',
    );

  /* ── Open a deposit ── */

  const openAmountN = parseAmount(openAmount);
  const openTermRate = openKind === 'demand' ? null : termRate(openKind);

  const openDeposit = async () => {
    if (!checkMin(openAmountN)) return;
    if (openAmountN > view.wallet) {
      toast.error(`Недостаточно ${forms.genitive}`);
      return;
    }
    const ok = await run(
      (request_id) =>
        bankDeposit(npcId, {
          character_id: characterId,
          kind: openKind === 'demand' ? 'demand' : 'term',
          term_days: openKind === 'demand' ? null : openKind,
          amount: openAmountN,
          request_id,
        }),
      'Не удалось открыть вклад',
    );
    if (ok) setOpenAmount('');
  };

  /* ── Deposits in other banks → here ── */

  const canMoveHere = view.bank_enabled && view.region_id !== null;

  const moveHere = async (d: BankDeposit) => {
    if (view.region_id === null) return;
    const amount = parseAmount(moveAmounts[d.id] ?? '');
    if (amount < 1) {
      toast.error('Укажите сумму');
      return;
    }
    const fee = transferFee(amount, rates.transfer_fee_rate, rates.transfer_fee_min);
    if (amount + fee > d.amount) {
      toast.error(`На вкладе недостаточно средств с учётом комиссии ${format(fee, true)}`);
      return;
    }
    const toRegion = view.region_id;
    const ok = await run(
      (request_id) =>
        bankTransfer(npcId, {
          character_id: characterId,
          deposit_id: d.id,
          to_region_id: toRegion,
          amount,
          request_id,
        }),
      'Не удалось перевести вклад',
    );
    if (ok) setMoveAmounts((prev) => ({ ...prev, [d.id]: '' }));
  };

  return (
    <div className="flex flex-col gap-5 min-w-0">
      {/* Rates */}
      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-white/60">
        <span>
          До востребования: <span className="text-white">{demandRateText(rates.demand_rate_day)}</span>
        </span>
        {rates.term_rates.map((t) => (
          <span key={t.term_days}>
            Срочный: <span className="text-white">{termRateText(t.rate_day, t.term_days)}</span>
          </span>
        ))}
      </div>

      <BankSection title="Вклады в этом банке">
        {here.length === 0 && <p className="text-white/50 text-sm">Здесь у вас пока нет вкладов.</p>}

        {demandHere && (
          <BankCard>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="text-white text-sm font-medium">До востребования</span>
              <span className="text-gold text-base sm:text-lg font-medium">{format(demandHere.amount, true)}</span>
            </div>
            <BankLine label="Начислено процентов за всё время">{format(demandHere.interest_total, true)}</BankLine>
            <BankLine label="Ставка">
              {view.bank_enabled ? demandRateText(demandHere.rate_day ?? rates.demand_rate_day) : 'не начисляется'}
            </BankLine>
            <div className="flex flex-wrap items-end gap-2 mt-1">
              <AmountInput
                value={demandAmount}
                onChange={setDemandAmount}
                allAmount={demandHere.amount}
                disabled={pending}
              />
              <div className="flex gap-2 shrink-0">
                {view.bank_enabled && (
                  <SmallButton onClick={() => void topUp()} disabled={pending}>
                    Положить
                  </SmallButton>
                )}
                <SmallButton variant="line" onClick={() => void withdrawDemand()} disabled={pending}>
                  Снять
                </SmallButton>
              </div>
            </div>
          </BankCard>
        )}

        {termsHere.map((d) => (
          <BankCard key={d.id}>
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="text-white text-sm font-medium">Срочный, {d.term_days} дн.</span>
              <span className="text-gold text-base sm:text-lg font-medium">{format(d.amount, true)}</span>
            </div>
            <BankLine label="Набежало процентов">{format(d.interest_accrued, true)}</BankLine>
            {d.rate_day !== null && d.term_days !== null && (
              <BankLine label="Ставка">{termRateText(d.rate_day, d.term_days)}</BankLine>
            )}
            <BankLine label={d.matured ? 'Срок вышел' : 'Срок до'}>{formatServerDateTime(d.matures_at)}</BankLine>
            <div className="flex justify-end mt-1">
              {d.matured ? (
                <SmallButton onClick={() => void withdrawTerm(d)} disabled={pending}>
                  Забрать {format(d.amount + d.interest_accrued, true)}
                </SmallButton>
              ) : (
                <SmallButton variant="line" onClick={() => setEarlyClose(d)} disabled={pending}>
                  Закрыть досрочно
                </SmallButton>
              )}
            </div>
          </BankCard>
        ))}
      </BankSection>

      {view.bank_enabled && (
        <BankSection title="Открыть вклад">
          <BankCard>
            <Choice<OpenKind>
              value={openKind}
              onChange={setOpenKind}
              disabled={pending}
              options={[
                { value: 'demand', label: demandHere ? 'До востребования (пополнить)' : 'До востребования' },
                ...termOptions.map((t) => ({ value: t as OpenKind, label: `Срочный ${t} дн.` })),
              ]}
            />
            <div className="flex flex-wrap items-end gap-2">
              <AmountInput value={openAmount} onChange={setOpenAmount} allAmount={view.wallet} disabled={pending} />
              <SmallButton onClick={() => void openDeposit()} disabled={pending || openAmountN < 1}>
                {openKind === 'demand' ? 'Положить' : 'Открыть'}
              </SmallButton>
            </div>
            <div className="text-white/50 text-xs flex flex-col gap-0.5">
              {openKind === 'demand' ? (
                <span>
                  {demandRateText(rates.demand_rate_day)}
                  {openAmountN > 0 && <> · за неделю ≈ {format(weekInterest(openAmountN, rates.demand_rate_day), true)}</>}
                  . Снять можно в любой момент.
                </span>
              ) : openTermRate !== null ? (
                <span>
                  {termRateText(openTermRate, openKind)}
                  {openAmountN > 0 && (
                    <> · доход к концу срока: {format(termInterest(openAmountN, openTermRate, openKind), true)}</>
                  )}
                  . При досрочном закрытии проценты сгорают.
                </span>
              ) : null}
              <span>Минимальная сумма — {format(rates.min_amount, true)}.</span>
            </div>
          </BankCard>
        </BankSection>
      )}

      {elsewhere.length > 0 && (
        <BankSection title="В других банках">
          {elsewhere.map((d) => {
            const moveN = parseAmount(moveAmounts[d.id] ?? '');
            const fee = transferFee(moveN, rates.transfer_fee_rate, rates.transfer_fee_min);
            return (
              <BankCard key={d.id}>
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <span className="text-white text-sm font-medium min-w-0 break-words">
                    {regionLabel(d.region_name)} · {d.kind === 'demand' ? 'до востребования' : `срочный ${d.term_days} дн.`}
                  </span>
                  <span className="text-gold text-sm sm:text-base font-medium">{format(d.amount, true)}</span>
                </div>
                {d.kind === 'term' && (
                  <>
                    <BankLine label="Набежало процентов">{format(d.interest_accrued, true)}</BankLine>
                    <BankLine label={d.matured ? 'Срок вышел' : 'Срок до'}>{formatServerDateTime(d.matures_at)}</BankLine>
                    <p className="text-white/40 text-xs">Срочный вклад снимается только в своём банке.</p>
                  </>
                )}
                {d.kind === 'demand' && canMoveHere && (
                  <>
                    <div className="flex flex-wrap items-end gap-2">
                      <AmountInput
                        value={moveAmounts[d.id] ?? ''}
                        onChange={(v) => setMoveAmounts((prev) => ({ ...prev, [d.id]: v }))}
                        allAmount={maxWithFee(d.amount, rates.transfer_fee_rate, rates.transfer_fee_min)}
                        disabled={pending}
                      />
                      <SmallButton onClick={() => void moveHere(d)} disabled={pending || moveN < 1}>
                        Перевести сюда
                      </SmallButton>
                    </div>
                    {moveN > 0 && (
                      <span className="text-white/50 text-xs">
                        Комиссия {format(fee, true)} · со вклада спишется {format(moveN + fee, true)}
                      </span>
                    )}
                  </>
                )}
              </BankCard>
            );
          })}
        </BankSection>
      )}

      <ConfirmationModal
        isOpen={earlyClose !== null}
        title="Закрыть вклад досрочно?"
        message={
          earlyClose
            ? `Вы получите ${format(earlyClose.amount, true)}. Набежавшие проценты (${format(
                earlyClose.interest_accrued,
                true,
              )}) сгорят.`
            : ''
        }
        onCancel={() => setEarlyClose(null)}
        onConfirm={() => {
          const d = earlyClose;
          setEarlyClose(null);
          if (d) void withdrawTerm(d);
        }}
      />
    </div>
  );
};

export default BankDepositsTab;
