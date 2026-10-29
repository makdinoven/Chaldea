import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { MapPin } from 'lucide-react';
import { buyListedHouse } from '../../../api/houses';
import { apiErrorMessage } from '../../../api/errors';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import { getMe } from '../../../redux/slices/userSlice';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import { useCurrency } from '../../../hooks/useCurrency';

/** What the dialog needs to know about a listed house. */
export interface ListedHouse {
  id: number;
  name: string;
  price: number;
  location_id: number;
  location_name: string | null;
  owner_id?: number | null;
  owner_name?: string | null;
  /** Unknown (undefined) outside the sale board. */
  furniture_count?: number;
  stored_stacks?: number;
  tax_per_season?: number;
}

interface BuyListedHouseDialogProps {
  house: ListedHouse;
  onClose: () => void;
}

/**
 * FEAT-180 stage 4 — buying a house off the sale board with the current
 * character. The buyer must stand in the house's location; otherwise the
 * dialog only explains that and links there.
 */
const BuyListedHouseDialog = ({ house, onClose }: BuyListedHouseDialogProps) => {
  const { format, forms } = useCurrency();
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const character = useAppSelector((state) => state.user.character);
  const [busy, setBusy] = useState(false);
  const here = character?.current_location?.id === house.location_id;
  const isOwner = character != null && house.owner_id != null && character.id === house.owner_id;
  const price = house.price.toLocaleString('ru-RU');
  const locationName = house.location_name ?? `локация #${house.location_id}`;

  const buy = async () => {
    if (!character) return;
    setBusy(true);
    try {
      const { house_id } = await buyListedHouse(house.id, character.id);
      toast.success(`«${house.name}» теперь ваш!`);
      // Gold in the header comes from /users/me.
      void dispatch(getMe());
      onClose();
      navigate(`/houses/${house_id}`);
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось купить дом'));
      setBusy(false);
    }
  };

  const transfers = [
    house.furniture_count != null ? `мебель во всех комнатах (${house.furniture_count} шт.)` : 'мебель во всех комнатах',
    house.stored_stacks != null ? `вещи кладовой (${house.stored_stacks} стоп.)` : 'вещи кладовой',
    'посты в комнатах',
  ];

  return (
    <ModalShell
      open
      onClose={onClose}
      title="Покупка дома"
      size="sm"
      dismissible={!busy}
      footer={
        <>
          <button type="button" className="btn-line w-full sm:w-auto !text-xs !py-2 !px-5" onClick={onClose} disabled={busy}>
            Отмена
          </button>
          {character && here && !isOwner && (
            <button type="button" autoFocus onClick={() => void buy()} disabled={busy}
              className="btn-blue w-full sm:w-auto !py-2 !px-5 !text-xs disabled:opacity-50">
              {busy ? 'Покупка...' : `Купить за ${price}`}
            </button>
          )}
        </>
      }
    >
      <div className="flex flex-col gap-3 text-sm text-white/80 break-words">
        <p>
          «{house.name}» за <span className="text-gold">{format(house.price)}</span>
          {house.owner_name ? <> у {house.owner_name}</> : null}.
        </p>
        <div className="flex flex-col gap-1">
          <span className="text-white/50 text-xs uppercase tracking-[0.06em]">Переходит покупателю</span>
          <ul className="list-disc pl-5 text-white/70 text-[13px]">
            {transfers.map((t) => <li key={t}>{t}</li>)}
          </ul>
        </div>
        <p className="text-white/55 text-xs">
          Жильцы и наследник прежнего хозяина будут выписаны. {forms.name} уходит продавцу.
          {house.tax_per_season != null && ` Налог дома — ${format(house.tax_per_season)} за сезон.`}
        </p>
        {!character && <p className="text-site-red text-xs">Выберите персонажа, чтобы купить дом.</p>}
        {character && isOwner && <p className="text-site-red text-xs">Это дом вашего персонажа.</p>}
        {character && !here && (
          <p className="text-white/70 text-xs flex flex-wrap items-center gap-1">
            Дом покупают на месте — {character.name} должен дойти до локации
            <Link to={`/location/${house.location_id}`} onClick={onClose} className="site-link inline-flex items-center gap-1">
              <MapPin size={12} />{locationName}
            </Link>
          </p>
        )}
      </div>
    </ModalShell>
  );
};

export default BuyListedHouseDialog;
