import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { getBankSummary } from '../../../api/bank';
import { useCurrency } from '../../../hooks/useCurrency';
import { useAppSelector } from '../../../redux/store';
import type { BankSummary as BankSummaryData } from '../../../types/bank';
import { formatServerDateTime } from '../../../utils/serverDate';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import { bankErrorText, regionLabel } from '../../pages/LocationPage/BankModal/bankFormat';
import { BankCard, BankLine, BankSection, DebtorBadge } from '../../pages/LocationPage/BankModal/BankParts';

/**
 * FEAT-184 — own bank summary on the profile «Персонаж» panel: total in deposits,
 * the loan debt and the «Должник» mark; a click opens a read-only list by region.
 * Hidden when the character has neither deposits nor a loan.
 */
const BankSummary = () => {
  const { format } = useCurrency();
  const characterId = useAppSelector((s) => s.user.character?.id ?? null) as number | null;
  const [summary, setSummary] = useState<BankSummaryData | null>(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    setSummary(null);
    if (!characterId) return undefined;
    let cancelled = false;
    getBankSummary(characterId)
      .then((data) => {
        if (!cancelled) setSummary(data);
      })
      .catch((err) => {
        if (!cancelled) toast.error(bankErrorText(err, 'Не удалось загрузить банковские вклады'));
      });
    return () => {
      cancelled = true;
    };
  }, [characterId]);

  if (!summary || (summary.deposits.length === 0 && !summary.loan)) return null;

  const { deposits, loan } = summary;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title="Вклады и займ по банкам"
        className="flex flex-wrap items-center justify-center gap-x-5 gap-y-1.5 -mt-2 text-sm hover:opacity-80 transition-opacity duration-200"
      >
        {deposits.length > 0 && (
          <span className="flex items-center gap-1.5">
            <span className="text-[11px] font-medium uppercase tracking-[0.05em] text-white/55">Во вкладах</span>
            <span className="gold-text font-medium">{format(summary.total_deposits, true)}</span>
          </span>
        )}
        {loan && (
          <span className="flex items-center gap-1.5">
            <span className="text-[11px] font-medium uppercase tracking-[0.05em] text-white/55">Долг</span>
            <span className={`font-medium ${loan.overdue ? 'text-site-red' : 'text-white'}`}>
              {format(loan.debt, true)}
            </span>
          </span>
        )}
        {summary.debtor && <DebtorBadge />}
      </button>

      <ModalShell open={open} onClose={() => setOpen(false)} title="Банк" size="sm">
        <div className="flex flex-col gap-5 min-w-0">
          {deposits.length > 0 && (
            <BankSection title="Вклады">
              {deposits.map((d) => (
                <BankCard key={d.id}>
                  <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
                    <span className="text-white text-sm font-medium truncate">«{regionLabel(d.region_name)}»</span>
                    <span className="text-white/50 text-xs">
                      {d.kind === 'term' ? `Срочный, ${d.term_days ?? '—'} дн.` : 'До востребования'}
                    </span>
                  </div>
                  <BankLine label="Сумма">{format(d.amount, true)}</BankLine>
                  {d.interest_accrued > 0 && (
                    <BankLine label="Начислено">{format(d.interest_accrued, true)}</BankLine>
                  )}
                  {d.kind === 'term' && d.matures_at && (
                    <BankLine label={d.matured ? 'Срок вышел' : 'Срок до'}>{formatServerDateTime(d.matures_at)}</BankLine>
                  )}
                </BankCard>
              ))}
              <BankLine label="Всего во вкладах">{format(summary.total_deposits, true)}</BankLine>
            </BankSection>
          )}

          {loan && (
            <BankSection title="Займ">
              <BankCard>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <span className="text-white text-sm font-medium truncate">«{regionLabel(loan.region_name)}»</span>
                  {loan.overdue && <DebtorBadge />}
                </div>
                <BankLine label="Долг">{format(loan.debt, true)}</BankLine>
                <BankLine label="Вернуть до">{formatServerDateTime(loan.due_at)}</BankLine>
                {loan.penalty_total > 0 && <BankLine label="Пени">{format(loan.penalty_total, true)}</BankLine>}
              </BankCard>
            </BankSection>
          )}

          <p className="text-white/50 text-xs text-center">Операции — у банкира</p>
        </div>
      </ModalShell>
    </>
  );
};

export default BankSummary;
