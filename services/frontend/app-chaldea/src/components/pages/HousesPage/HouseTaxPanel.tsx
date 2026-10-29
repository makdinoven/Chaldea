import { useState } from 'react';
import toast from 'react-hot-toast';
import { AlertTriangle, Coins, Snowflake } from 'lucide-react';
import { payTax, type ActingCharacter, type House } from '../../../api/houses';
import { apiErrorMessage } from '../../../api/errors';
import { useAppDispatch } from '../../../redux/store';
import { getMe } from '../../../redux/slices/userSlice';
import { formatServerDate } from '../../../utils/serverDate';
import { useCurrency } from '../../../hooks/useCurrency';

interface HouseTaxPanelProps {
  house: House;
  /** The character the viewer acts through here — it pays. */
  acting: ActingCharacter | null;
  onChanged: () => void;
}

const gold = (n: number) => n.toLocaleString('ru-RU');

/** «15 декабря» — the end of the current tax period in the viewer's timezone. */
export const taxDeadline = (house: House) =>
  formatServerDate(house.tax.period_ends_at, { day: 'numeric', month: 'long' });

/**
 * FEAT-180 stage 4 — the house tax under the header: a quiet line when paid,
 * a warning while this season is owed, a red banner when the house is frozen.
 * The owner or any resident (through the acting character) pays.
 */
const HouseTaxPanel = ({ house, acting, onChanged }: HouseTaxPanelProps) => {
  const { format } = useCurrency();
  const dispatch = useAppDispatch();
  const [busy, setBusy] = useState(false);
  const { tax } = house;
  const payer = acting?.character ?? null;
  const date = taxDeadline(house);
  const frozen = house.status === 'frozen';

  const pay = async () => {
    if (!payer) return;
    setBusy(true);
    try {
      const { paid } = await payTax(house.id, payer.id);
      toast.success(`Налог уплачен: ${format(paid)}`);
      onChanged();
      void dispatch(getMe());
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось заплатить налог'));
    } finally {
      setBusy(false);
    }
  };

  const payButton = payer && (
    <button type="button" onClick={() => void pay()} disabled={busy}
      className="btn-blue !w-full sm:!w-auto !px-5 !py-1.5 !text-xs shrink-0 flex items-center justify-center gap-1.5 disabled:opacity-50">
      <Coins size={13} />
      {busy ? 'Оплата...' : `Заплатить ${gold(tax.due)}`}
      {house.acting.length > 1 && <span className="opacity-70 truncate max-w-[120px]">· {payer.name}</span>}
    </button>
  );

  if (frozen) {
    return (
      <div className="rounded-card border border-site-red/60 bg-site-red/10 backdrop-blur-sm p-4 flex flex-col sm:flex-row sm:items-center gap-3">
        <Snowflake size={22} className="text-site-red shrink-0 hidden sm:block" />
        <div className="flex flex-col gap-1 flex-1 min-w-0">
          <span className="text-site-red text-sm sm:text-base font-medium uppercase tracking-[0.06em]">
            Дом заморожен за неуплату налога
          </span>
          <span className="text-white/75 text-xs sm:text-sm">
            Долг — {format(tax.due)} ({tax.owed_periods} {tax.owed_periods === 1 ? 'сезон' : 'сезона'}).
            Пока он не погашен, в доме нельзя писать, спать, строить, обставлять комнаты и пользоваться кладовой;
            бонус мастерской не действует. Если не заплатить до {date}, город изымет дом.
          </span>
        </div>
        {payButton}
      </div>
    );
  }

  if (tax.owed_periods > 0) {
    return (
      <div className="rounded-card border border-gold/50 bg-gold/10 backdrop-blur-sm px-4 py-3 flex flex-col sm:flex-row sm:items-center gap-3">
        <AlertTriangle size={18} className="text-gold shrink-0 hidden sm:block" />
        <span className="text-white/85 text-sm flex-1 min-w-0">
          Налог за сезон не уплачен — <span className="text-gold">{format(tax.due)}</span> до {date}, иначе дом заморозят.
        </span>
        {payButton}
      </div>
    );
  }

  return (
    <p className="text-white/50 text-xs flex items-center gap-1.5 px-1">
      <Coins size={13} className="text-gold/70 shrink-0" />
      Налог: {format(tax.per_season)} за сезон · оплачен до {date}
    </p>
  );
};

export default HouseTaxPanel;
