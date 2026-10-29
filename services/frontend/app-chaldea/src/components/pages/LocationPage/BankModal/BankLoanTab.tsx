import { useState } from 'react';
import toast from 'react-hot-toast';
import { bankLoan, bankRepay } from '../../../../api/bank';
import { useCurrency } from '../../../../hooks/useCurrency';
import { BANK_TERMS, type BankTerm } from '../../../../types/bank';
import { formatServerDateTime } from '../../../../utils/serverDate';
import { loanTotal, parseAmount, percent, regionLabel, termRateText } from './bankFormat';
import {
  AmountInput,
  BankCard,
  BankLine,
  BankSection,
  Choice,
  DebtorBadge,
  SmallButton,
  type BankTabProps,
} from './BankParts';

const DAY_MS = 86_400_000;

const BankLoanTab = ({ view, characterId, npcId, pending, run }: BankTabProps) => {
  const { format, forms } = useCurrency();
  const { rates, loan } = view;

  const [term, setTerm] = useState<BankTerm>(7);
  const [amount, setAmount] = useState('');
  const [repayAmount, setRepayAmount] = useState('');

  const amountN = parseAmount(amount);
  const repayN = parseAmount(repayAmount);

  const takeLoan = async () => {
    if (amountN < 1) {
      toast.error('Укажите сумму');
      return;
    }
    if (amountN > view.max_loan_now) {
      toast.error(`Сейчас можно взять не больше ${format(view.max_loan_now, true)}`);
      return;
    }
    const ok = await run(
      (request_id) => bankLoan(npcId, { character_id: characterId, amount: amountN, term_days: term, request_id }),
      'Не удалось взять займ',
    );
    if (ok) setAmount('');
  };

  const repay = async () => {
    if (!loan) return;
    if (repayN < 1) {
      toast.error('Укажите сумму');
      return;
    }
    if (repayN > view.wallet) {
      toast.error(`Недостаточно ${forms.genitive}`);
      return;
    }
    const ok = await run(
      (request_id) => bankRepay(npcId, { character_id: characterId, amount: repayN, request_id }),
      'Не удалось погасить займ',
    );
    if (ok) setRepayAmount('');
  };

  if (loan) {
    const repayAll = Math.min(loan.debt, view.wallet);
    return (
      <BankSection title="Ваш займ">
        <BankCard className={loan.overdue ? '!border-site-red/30' : ''}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="text-white/50 text-xs sm:text-sm">Долг сейчас</span>
            <div className="flex items-center gap-2">
              {(loan.overdue || view.debtor) && <DebtorBadge />}
              <span className={`text-base sm:text-lg font-medium ${loan.overdue ? 'text-site-red' : 'text-gold'}`}>
                {format(loan.debt, true)}
              </span>
            </div>
          </div>
          <BankLine label="Банк">{regionLabel(loan.region_name)}</BankLine>
          <BankLine label="Взято">{format(loan.principal, true)}</BankLine>
          <BankLine label="Ставка">{termRateText(loan.rate_day, loan.term_days)}</BankLine>
          <BankLine label="Вернуть до">{formatServerDateTime(loan.due_at)}</BankLine>
          {loan.interest_total > 0 && <BankLine label="Проценты">{format(loan.interest_total, true)}</BankLine>}
          {loan.penalty_total > 0 && (
            <BankLine label="Пени">
              <span className="text-site-red">{format(loan.penalty_total, true)}</span>
            </BankLine>
          )}
          {loan.paid_total > 0 && <BankLine label="Уже погашено">{format(loan.paid_total, true)}</BankLine>}
          {loan.collected_total > 0 && (
            <BankLine label="Взыскано банком">{format(loan.collected_total, true)}</BankLine>
          )}
          {loan.overdue && (
            <p className="text-site-red text-xs">
              Срок вышел: каждые 6 часов начисляются пени ({percent(loan.penalty_rate_day)} % в день), банк сам
              списывает долг со вкладов и кошелька. Новые займы не выдаются, пока долг не погашен.
            </p>
          )}
          <div className="flex flex-wrap items-end gap-2 mt-1">
            <AmountInput value={repayAmount} onChange={setRepayAmount} allAmount={repayAll} disabled={pending} />
            <SmallButton onClick={() => void repay()} disabled={pending || repayN < 1}>
              Погасить
            </SmallButton>
          </div>
          <span className="text-white/40 text-xs">Гасить можно частями и досрочно, у любого банкира.</span>
        </BankCard>
      </BankSection>
    );
  }

  const termOptions = BANK_TERMS.map((t) => ({ value: t, label: `${t} дн.` }));
  const dueDate = new Date(Date.now() + term * DAY_MS).toLocaleDateString('ru-RU', {
    day: 'numeric',
    month: 'long',
  });

  return (
    <BankSection title="Взять займ">
      <BankCard>
        {view.debtor && (
          <div className="flex items-center gap-2">
            <DebtorBadge />
            <span className="text-site-red text-xs">Новые займы не выдаются</span>
          </div>
        )}
        <BankLine label="Ваш лимит">{format(view.loan_cap, true)}</BankLine>
        <BankLine label="Можно взять сейчас">{format(view.max_loan_now, true)}</BankLine>
        <BankLine label="Ставка">{termRateText(rates.loan_rate_day, term)}</BankLine>
        <BankLine label="Пени при просрочке">{percent(rates.penalty_rate_day)} % в день</BankLine>

        {view.max_loan_now <= 0 ? (
          <p className="text-white/60 text-sm">{view.loan_refusal ?? 'Сейчас банк не выдаёт займ.'}</p>
        ) : (
          <>
            <Choice<BankTerm> value={term} onChange={setTerm} options={termOptions} disabled={pending} />
            <div className="flex flex-wrap items-end gap-2">
              <AmountInput value={amount} onChange={setAmount} allAmount={view.max_loan_now} disabled={pending} />
              <SmallButton onClick={() => void takeLoan()} disabled={pending || amountN < 1}>
                Взять займ
              </SmallButton>
            </div>
            {amountN > 0 && (
              <span className="text-white/50 text-xs">
                Вернуть до {dueDate}: ≈ {format(loanTotal(amountN, rates.loan_rate_day, term), true)}. Ставка
                фиксируется при выдаче.
              </span>
            )}
          </>
        )}
      </BankCard>
    </BankSection>
  );
};

export default BankLoanTab;
