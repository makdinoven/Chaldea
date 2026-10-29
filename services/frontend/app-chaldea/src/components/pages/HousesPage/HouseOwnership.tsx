import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Crown, Tag } from 'lucide-react';
import { putUpForSale, setHeir, takeOffSale, type House } from '../../../api/houses';
import { apiErrorMessage } from '../../../api/errors';
import ConfirmDialog from '../LocationPage/ConfirmDialog';
import { FIELD, LABEL } from '../EpisodesPage/EpisodeFormModal';
import { useCurrency } from '../../../hooks/useCurrency';

interface HouseOwnershipProps {
  house: House;
  ownerCharacterId: number;
  onChanged: () => void;
}

const MAX_PRICE = 1_000_000_000;
const SALE_WARNING = 'Мебель и вещи кладовой перейдут покупателю, жильцы и наследник будут выписаны.';

/** FEAT-180 stage 4 — the owner's «Владение»: the heir and selling the house on the board. */
const HouseOwnership = ({ house, ownerCharacterId, onChanged }: HouseOwnershipProps) => {
  const { format, forms } = useCurrency();
  const [heirId, setHeirId] = useState<number | null>(house.heir?.id ?? null);
  const [savingHeir, setSavingHeir] = useState(false);
  const [price, setPrice] = useState(house.sale_price != null ? String(house.sale_price) : '');
  const [busy, setBusy] = useState(false);
  const [confirmSale, setConfirmSale] = useState<number | null>(null);

  useEffect(() => setHeirId(house.heir?.id ?? null), [house.heir?.id]);

  const residents = house.residents.filter((r) => r.character);
  const heirDirty = heirId !== (house.heir?.id ?? null);
  const listed = house.sale_price != null;
  const blockedReason = house.status === 'frozen'
    ? 'Дом заморожен за неуплату налога — сначала заплатите налог.'
    : house.tax.owed_periods > 0
      ? 'Сначала заплатите налог за этот сезон.'
      : null;

  const saveHeir = async () => {
    setSavingHeir(true);
    try {
      await setHeir(house.id, ownerCharacterId, heirId);
      toast.success(heirId == null ? 'Наследник снят' : 'Наследник назначен');
      onChanged();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить наследника'));
    } finally {
      setSavingHeir(false);
    }
  };

  const askSale = () => {
    const value = Number(price);
    if (!Number.isInteger(value) || value < 1 || value > MAX_PRICE) {
      toast.error(`Укажите цену — целое число ${forms.genitive} от 1`);
      return;
    }
    setConfirmSale(value);
  };

  const run = async (job: () => Promise<unknown>, done: string, failed: string) => {
    setBusy(true);
    try {
      await job();
      toast.success(done);
      onChanged();
    } catch (e) {
      toast.error(apiErrorMessage(e, failed));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <section className="bg-site-bg backdrop-blur-sm rounded-card border border-gold-dark/20 p-4 sm:p-5 flex flex-col gap-3">
        <h2 className="gold-text text-sm font-medium uppercase tracking-[0.08em] flex items-center gap-2">
          <Crown size={15} className="text-gold" />Наследник
        </h2>
        <p className="text-white/55 text-xs leading-snug">
          Если хозяин будет удалён, дом перейдёт наследнику; без наследника его изымет город.
          Наследником может быть только жилец дома.
        </p>
        <label className="flex flex-col gap-1.5">
          <span className={LABEL}>Наследник</span>
          <select value={heirId ?? ''} onChange={(e) => setHeirId(e.target.value === '' ? null : Number(e.target.value))}
            className={FIELD}>
            <option value="">Без наследника</option>
            {residents.map((r) => <option key={r.id} value={r.character!.id}>{r.character!.name}</option>)}
          </select>
        </label>
        {residents.length === 0 && (
          <p className="text-white/40 text-xs italic">Жильцов нет — поселите кого-нибудь во вкладке «Жильцы».</p>
        )}
        <button type="button" onClick={() => void saveHeir()} disabled={!heirDirty || savingHeir}
          className="btn-blue !w-full sm:!w-auto !px-6 self-end disabled:opacity-40">
          {savingHeir ? 'Сохранение...' : 'Сохранить'}
        </button>
      </section>

      <section className="bg-site-bg backdrop-blur-sm rounded-card border border-gold-dark/20 p-4 sm:p-5 flex flex-col gap-3">
        <h2 className="gold-text text-sm font-medium uppercase tracking-[0.08em] flex items-center gap-2">
          <Tag size={15} className="text-gold" />Продажа
        </h2>
        <p className="text-white/55 text-xs leading-snug">
          Выставленный дом виден на <Link to="/houses/market" className="site-link">доске продажи домов</Link>.
          Покупатель платит на месте, в локации дома; {forms.name.toLowerCase()} получает хозяин. {SALE_WARNING}
        </p>
        {listed ? (
          <div className="flex flex-col sm:flex-row sm:items-center gap-3">
            <span className="text-white text-sm flex-1">
              Продаётся за <span className="text-gold">{format(house.sale_price!)}</span>
            </span>
            <button type="button" disabled={busy}
              onClick={() => void run(() => takeOffSale(house.id, ownerCharacterId), 'Дом снят с продажи', 'Не удалось снять с продажи')}
              className="btn-line !w-full sm:!w-auto !px-5 disabled:opacity-50">
              Снять с продажи
            </button>
          </div>
        ) : (
          <div className="flex flex-col sm:flex-row sm:items-end gap-3">
            <label className="flex flex-col gap-1.5 flex-1">
              <span className={LABEL}>Цена, {forms.name.toLowerCase()}</span>
              <input type="number" inputMode="numeric" min={1} max={MAX_PRICE} value={price}
                disabled={blockedReason != null}
                onChange={(e) => setPrice(e.target.value)} className={FIELD} />
            </label>
            <button type="button" onClick={askSale} disabled={busy || blockedReason != null || !price}
              className="btn-blue !w-full sm:!w-auto !px-6 disabled:opacity-40">
              Выставить на продажу
            </button>
          </div>
        )}
        {blockedReason && !listed && <p className="text-site-red text-xs">{blockedReason}</p>}
      </section>

      {confirmSale != null && (
        <ConfirmDialog
          title="Выставить дом на продажу"
          message={`«${house.name}» появится на доске продажи за ${format(confirmSale)}. ${SALE_WARNING} Снять с продажи можно в любой момент до покупки.`}
          confirmLabel="Выставить"
          onCancel={() => setConfirmSale(null)}
          onConfirm={() => {
            const value = confirmSale;
            setConfirmSale(null);
            void run(() => putUpForSale(house.id, ownerCharacterId, value), 'Дом выставлен на продажу', 'Не удалось выставить дом');
          }}
        />
      )}
    </div>
  );
};

export default HouseOwnership;
