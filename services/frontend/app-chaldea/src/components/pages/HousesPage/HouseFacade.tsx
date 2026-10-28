import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Lock, MapPin, Snowflake, Tag } from 'lucide-react';
import { type HouseFacade as HouseFacadeData } from '../../../api/houses';
import { useAppSelector } from '../../../redux/store';
import { useBodyBackground } from '../../../hooks/useBodyBackground';
import CharAvatar from './CharAvatar';
import BuyListedHouseDialog from './BuyListedHouseDialog';

/*
  FEAT-180 stage 7 — a house seen from the street: picture, name, owner and
  the sale offer. Only the owner, residents and guests may step inside.
*/

interface HouseFacadeProps {
  house: HouseFacadeData;
  onChanged: () => void;
}

const HouseFacade = ({ house, onChanged }: HouseFacadeProps) => {
  const characterId = useAppSelector((state) => state.user.character?.id ?? null);
  const [buying, setBuying] = useState(false);
  useBodyBackground(house.image_url);

  const canBuy = house.sale_price != null && characterId != null && house.owner?.id !== characterId;

  return (
    <div className="w-full max-w-container mx-auto flex flex-col gap-4 sm:gap-5 pb-10">
      <Link to={`/location/${house.location_id}`} className="self-start text-white/60 hover:text-white text-sm flex items-center gap-1 min-w-0">
        <ArrowLeft size={15} className="shrink-0" /><span className="truncate">{house.location_name ?? 'К локации'}</span>
      </Link>

      <section className="bg-site-bg backdrop-blur-sm rounded-card border border-gold-dark/20 shadow-card p-4 sm:p-7 flex flex-col sm:flex-row gap-4 sm:gap-6">
        {house.image_url && (
          <div className="w-full sm:w-72 aspect-[16/9] sm:aspect-[4/3] rounded-card overflow-hidden bg-black/40 shrink-0">
            <img src={house.image_url} alt="" className="w-full h-full object-cover" />
          </div>
        )}
        <div className="flex flex-col gap-3 min-w-0 flex-1">
          <h1 className="text-white text-2xl sm:text-4xl font-medium uppercase leading-tight break-words"
            style={{ textShadow: '0 6px 26px rgba(0,0,0,.8)' }}>
            {house.name}
          </h1>
          {house.description && (
            <p className="text-white/80 text-sm sm:text-[15px] font-light leading-relaxed whitespace-pre-wrap break-words max-w-3xl">
              {house.description}
            </p>
          )}
          <div className="flex items-center gap-x-5 gap-y-2 flex-wrap text-xs text-white/55">
            <Link to={`/location/${house.location_id}`} className="site-link flex items-center gap-1">
              <MapPin size={13} />{house.location_name ?? `Локация #${house.location_id}`}
            </Link>
            {house.owner && (
              <span className="flex items-center gap-2 min-w-0">
                Хозяин:
                <CharAvatar src={house.owner.avatar} size="w-6 h-6" />
                <span className="text-white truncate">{house.owner.name}</span>
              </span>
            )}
            {house.status === 'frozen' && (
              <span className="flex items-center gap-1 text-site-red"><Snowflake size={12} />Заморожен за неуплату налога</span>
            )}
          </div>

          <p className="flex items-start gap-2 text-white/65 text-sm bg-white/[0.03] border border-white/[0.07] rounded-card px-3 py-2.5">
            <Lock size={15} className="text-gold shrink-0 mt-0.5" />
            Внутрь могут войти только хозяин, жильцы и гости.
          </p>

          {house.sale_price != null && (
            <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
              <span className="flex items-center gap-1.5 text-gold text-sm">
                <Tag size={14} className="shrink-0" />Продаётся за {house.sale_price.toLocaleString('ru-RU')} золота
              </span>
              {canBuy && (
                <button type="button" onClick={() => setBuying(true)} className="btn-blue !w-full sm:!w-auto !px-6 !py-1.5 !text-sm">
                  Купить
                </button>
              )}
            </div>
          )}
        </div>
      </section>

      {buying && house.sale_price != null && (
        <BuyListedHouseDialog
          house={{
            id: house.id,
            name: house.name,
            price: house.sale_price,
            location_id: house.location_id,
            location_name: house.location_name,
            owner_id: house.owner?.id ?? null,
            owner_name: house.owner?.name ?? null,
          }}
          onClose={() => {
            setBuying(false);
            onChanged();
          }}
        />
      )}
    </div>
  );
};

export default HouseFacade;
