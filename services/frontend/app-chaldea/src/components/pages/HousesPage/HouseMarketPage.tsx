import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, Armchair, Coins, Home, MapPin, Package } from 'lucide-react';
import { getMarket, ROOM_TYPE_LABEL, type MarketHouse } from '../../../api/houses';
import { apiErrorMessage } from '../../../api/errors';
import { useAppSelector } from '../../../redux/store';
import CharAvatar from './CharAvatar';
import BuyListedHouseDialog from './BuyListedHouseDialog';

/** FEAT-180 stage 4 — «Продажа домов»: houses their owners put up for sale. */
const HouseMarketPage = () => {
  const loggedIn = useAppSelector((state) => state.user.id != null);
  const characterId = useAppSelector((state) => state.user.character?.id ?? null);
  const [houses, setHouses] = useState<MarketHouse[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [buying, setBuying] = useState<MarketHouse | null>(null);

  useEffect(() => {
    getMarket()
      .then(setHouses)
      .catch((e) => setError(apiErrorMessage(e, 'Не удалось загрузить доску продажи')));
  }, []);

  return (
    <div className="w-full max-w-container mx-auto flex flex-col gap-5 pb-10">
      {loggedIn && (
        <Link to="/houses" className="self-start text-white/60 hover:text-white text-sm flex items-center gap-1">
          <ArrowLeft size={15} />Мои дома
        </Link>
      )}
      <div className="flex flex-col gap-1.5">
        <h1 className="gold-text text-2xl sm:text-3xl font-semibold uppercase tracking-[0.06em]">Продажа домов</h1>
        <p className="text-white/60 text-sm max-w-2xl">
          Дома, которые хозяева выставили на продажу. Покупают на месте — персонаж должен стоять в локации дома.
          Мебель и вещи кладовой переходят покупателю, прежние жильцы выписываются.
        </p>
      </div>

      {error && <p className="text-site-red text-sm">{error}</p>}
      {!houses && !error && <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />}
      {houses?.length === 0 && <p className="text-white/40 text-sm italic">Сейчас никто не продаёт дом.</p>}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {houses?.map((h) => {
          const mine = characterId != null && h.owner?.id === characterId;
          return (
            <article key={h.id} className="bg-site-bg backdrop-blur-sm rounded-card border border-white/[0.07] overflow-hidden flex flex-col">
              <Link to={`/houses/${h.id}`} className="group relative aspect-[16/8] bg-black/40 overflow-hidden flex items-center justify-center">
                {h.image_url ? (
                  <img src={h.image_url} alt="" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
                ) : (
                  <Home size={36} className="text-white/15" />
                )}
                <span className="absolute top-2 right-2 px-2.5 py-0.5 rounded-full bg-black/75 text-gold text-xs font-medium">
                  {h.price.toLocaleString('ru-RU')} золота
                </span>
              </Link>
              <div className="p-4 flex flex-col gap-2 flex-1">
                <h2 className="text-white text-lg font-medium leading-tight break-words">{h.name}</h2>
                <div className="flex items-center gap-x-4 gap-y-1.5 flex-wrap text-xs text-white/55">
                  <Link to={`/location/${h.location_id}`} className="site-link flex items-center gap-1 min-w-0">
                    <MapPin size={13} className="shrink-0" /><span className="truncate">{h.location_name ?? `Локация #${h.location_id}`}</span>
                  </Link>
                  {h.owner && (
                    <span className="flex items-center gap-1.5 min-w-0">
                      <CharAvatar src={h.owner.avatar} size="w-5 h-5" />
                      <span className="truncate">{h.owner.name}</span>
                    </span>
                  )}
                </div>
                <div className="flex flex-col gap-1">
                  <span className="text-white/45 text-[11px] uppercase tracking-[0.06em]">
                    Места {h.cells.taken}/{h.cells.usable}{h.cells.total > h.cells.usable ? ` (всего ${h.cells.total})` : ''}
                  </span>
                  {h.rooms.length === 0 ? (
                    <span className="text-white/40 text-xs italic">Комнат нет</span>
                  ) : (
                    <div className="flex flex-wrap gap-1.5">
                      {h.rooms.map((r, i) => (
                        <span key={`${r.room_type}-${i}`} title={r.name}
                          className="px-2 py-0.5 rounded-full bg-white/[0.05] border border-white/[0.08] text-white/75 text-[11px]">
                          {ROOM_TYPE_LABEL[r.room_type]}{r.level >= 1 ? ` · ур. ${r.level}` : ' · стройка'}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-x-4 gap-y-1 flex-wrap text-xs text-white/55">
                  <span className="flex items-center gap-1"><Armchair size={13} />Мебель: {h.furniture_count}</span>
                  <span className="flex items-center gap-1"><Package size={13} />В кладовой: {h.stored_stacks} стоп.</span>
                  <span className="flex items-center gap-1"><Coins size={13} />Налог: {h.tax_per_season.toLocaleString('ru-RU')}/сезон</span>
                </div>
                <div className="mt-auto pt-2">
                  {mine ? (
                    <p className="text-white/45 text-xs">Это ваш дом — снять с продажи можно во вкладке «Владение».</p>
                  ) : loggedIn ? (
                    <button type="button" onClick={() => setBuying(h)} className="btn-blue !w-full !py-1.5 !text-sm">
                      Купить
                    </button>
                  ) : (
                    <p className="text-white/45 text-xs">Войдите, чтобы купить дом.</p>
                  )}
                </div>
              </div>
            </article>
          );
        })}
      </div>

      {buying && (
        <BuyListedHouseDialog
          house={{
            id: buying.id,
            name: buying.name,
            price: buying.price,
            location_id: buying.location_id,
            location_name: buying.location_name,
            owner_id: buying.owner?.id ?? null,
            owner_name: buying.owner?.name ?? null,
            furniture_count: buying.furniture_count,
            stored_stacks: buying.stored_stacks,
            tax_per_season: buying.tax_per_season,
          }}
          onClose={() => setBuying(null)}
        />
      )}
    </div>
  );
};

export default HouseMarketPage;
