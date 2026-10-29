import { useCallback, useEffect, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { fetchEconomyBank, putEconomyBankFlag } from '../../../api/economyAdmin';
import { apiErrorMessage } from '../../../api/errors';
import { BigMoney } from './CompactValue';
import { useCurrency } from '../../../hooks/useCurrency';
import ConfirmDialog from '../../pages/LocationPage/ConfirmDialog';
import type { EconBankAdminItem } from '../../../types/economy';
import { BankBadge } from './regionBits';
import { FieldHint } from './ParamHint';

const HTTP_NOT_FOUND = 404;

interface RegionBankPanelProps {
  regionId: number;
  regionName: string;
  canEdit: boolean;
  /** The flag moves money (start capital from the treasury) — the editor and the list reload. */
  onChanged: () => void;
}

const bankersCount = (b: EconBankAdminItem): number => (Array.isArray(b.bankers) ? b.bankers.length : b.bankers ?? 0);

/** «Банк есть» of one region (FEAT-184) inside the region editor; the full picture lives in the «Банки» tab. */
const RegionBankPanel = ({ regionId, regionName, canEdit, onChanged }: RegionBankPanelProps) => {
  const { format } = useCurrency();
  /** undefined = loading, null = the region has no bank row yet */
  const [bank, setBank] = useState<EconBankAdminItem | null | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [seedCapital, setSeedCapital] = useState(true);
  const [confirmClose, setConfirmClose] = useState(false);

  const load = useCallback(() => {
    fetchEconomyBank(regionId)
      .then((detail) => {
        setBank(detail.item);
        setError(null);
      })
      .catch((e) => {
        if (axios.isAxiosError(e) && e.response?.status === HTTP_NOT_FOUND) {
          setBank(null);
          setError(null);
          return;
        }
        const msg = apiErrorMessage(e, 'Не удалось загрузить банк региона');
        setError(msg);
        toast.error(msg);
      });
  }, [regionId]);

  useEffect(load, [load]);

  const enabled = bank?.enabled ?? false;
  const neverSeeded = !bank || !bank.capital_seeded_at;

  const setFlag = async (next: boolean) => {
    setConfirmClose(false);
    setBusy(true);
    try {
      const item = await putEconomyBankFlag(regionId, { is_enabled: next, seed_capital: next && neverSeeded && seedCapital });
      const seededNow = next && neverSeeded && !!item.capital_seeded_at;
      setBank(item);
      setError(null);
      if (!next) toast.success(`Банк региона «${regionName}» закрыт`);
      else if (seededNow) toast.success(`Банк открыт. Стартовый капитал из казны: ${format(item.own_funds)}`);
      else toast.success(`Банк открыт. Свои средства банка: ${format(item.own_funds)}`);
      onChanged();
    } catch (e) {
      toast.error(apiErrorMessage(e, next ? 'Не удалось открыть банк' : 'Не удалось закрыть банк'));
    } finally {
      setBusy(false);
    }
  };

  const onToggle = (next: boolean) => {
    if (next) setFlag(true);
    else setConfirmClose(true);
  };

  return (
    <section className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-3 min-w-0">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Банк</h3>
        {enabled && <BankBadge />}
      </div>

      {error && bank === undefined && <p className="text-site-red text-sm">{error}</p>}
      {!error && bank === undefined && (
        <div className="w-6 h-6 border-4 border-white/30 border-t-gold rounded-full animate-spin" />
      )}

      {bank !== undefined && (
        <>
          <label htmlFor={`econ-bank-flag-${regionId}`} className="flex items-start gap-3 cursor-pointer select-none">
            <input
              id={`econ-bank-flag-${regionId}`}
              type="checkbox"
              checked={enabled}
              disabled={!canEdit || busy}
              onChange={(e) => onToggle(e.target.checked)}
              className="w-4 h-4 mt-0.5 shrink-0 accent-gold"
            />
            <span className="flex flex-col gap-0.5">
              <span className="flex items-center gap-1 text-white text-sm">
                Банк есть
                <FieldHint field="bank_enabled" label="Банк есть" />
              </span>
              <span className="text-white/40 text-xs">
                Игроки пользуются банком у НПС-банкира региона, жители держат в нём часть сбережений. При закрытии
                вклады остаются: их можно снять у банкира региона или перевести в другой банк.
              </span>
            </span>
          </label>

          {canEdit && !enabled && neverSeeded && (
            <label htmlFor={`econ-bank-seed-${regionId}`} className="flex items-start gap-3 cursor-pointer select-none sm:pl-7">
              <input
                id={`econ-bank-seed-${regionId}`}
                type="checkbox"
                checked={seedCapital}
                disabled={busy}
                onChange={(e) => setSeedCapital(e.target.checked)}
                className="w-4 h-4 mt-0.5 shrink-0 accent-gold"
              />
              <span className="flex flex-col gap-0.5">
                <span className="flex items-center gap-1 text-white/80 text-sm">
                  Взять стартовый капитал из казны
                  <FieldHint field="bank_seed_capital" label="Стартовый капитал из казны" />
                </span>
                <span className="text-white/40 text-xs">
                  Один раз, при первом открытии; сумма — параметр «Стартовый капитал» во вкладке «Пересчёт».
                </span>
              </span>
            </label>
          )}

          {bank && (
            <dl className="grid grid-cols-2 md:grid-cols-4 gap-x-4 gap-y-2 text-sm">
              <div className="flex flex-col gap-0.5 min-w-0">
                <dt className="text-white/50 text-xs">Свои средства</dt>
                <dd className={`break-words ${bank.own_funds < 0 ? 'text-site-red' : 'text-white'}`}><BigMoney value={bank.own_funds} /></dd>
              </div>
              <div className="flex flex-col gap-0.5 min-w-0">
                <dt className="text-white/50 text-xs">Вклады игроков</dt>
                <dd className={`break-words ${bank.vault_ok ? 'text-white' : 'text-site-red'}`}>
                  <BigMoney value={bank.vault} />
                  {!bank.vault_ok && <span className="block text-xs">расхождение</span>}
                </dd>
              </div>
              <div className="flex flex-col gap-0.5 min-w-0">
                <dt className="text-white/50 text-xs">Можно выдать в займы</dt>
                <dd className="text-white break-words"><BigMoney value={bank.lendable} /></dd>
              </div>
              <div className="flex flex-col gap-0.5 min-w-0">
                <dt className="text-white/50 text-xs">Долг по займам игроков</dt>
                <dd className="text-white break-words">
                  <BigMoney value={bank.loans_debt} />
                  {bank.overdue_count > 0 && <span className="block text-site-red text-xs">должников: {bank.overdue_count}</span>}
                </dd>
              </div>
            </dl>
          )}

          {bank && enabled && bankersCount(bank) === 0 && (
            <p className="text-gold text-xs">В регионе нет живого банкира — игроки не смогут открыть банк.</p>
          )}
          {!canEdit && <p className="text-white/40 text-xs">Изменять может администратор с правом «economy:settings».</p>}
          <p className="text-white/40 text-xs">Капитал, вклады, займы и должники — во вкладке «Банки».</p>
        </>
      )}

      {confirmClose && (
        <ConfirmDialog
          title="Закрыть банк"
          message={`Банк региона «${regionName}» перестанет принимать вклады и выдавать займы. Вклады игроков останутся — их можно будет снять у банкира региона или перевести в другой банк; займы по-прежнему гасятся и взыскиваются.`}
          confirmLabel="Закрыть банк"
          danger
          onConfirm={() => setFlag(false)}
          onCancel={() => setConfirmClose(false)}
        />
      )}
    </section>
  );
};

export default RegionBankPanel;
