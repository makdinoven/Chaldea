import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { DoorOpen, Home, Snowflake, Tag } from 'lucide-react';
import { buyPlot, enterHouse, myHouses, plotsAtLocation, type Plot } from '../../../api/houses';
import { apiErrorMessage } from '../../../api/errors';
import { useAppDispatch } from '../../../redux/store';
import { getMe } from '../../../redux/slices/userSlice';
import ConfirmDialog from './ConfirmDialog';
import BuyListedHouseDialog, { type ListedHouse } from '../HousesPage/BuyListedHouseDialog';

interface HousesSectionProps {
  locationId: number;
  characterId: number | null;
  isCharacterHere: boolean;
}

/**
 * «Дома» (FEAT-180) — the plots of this location: a free one can be bought by
 * the character standing here, a bought one leads into the house. Hidden when
 * the location has no plots.
 */
const HousesSection = ({ locationId, characterId, isCharacterHere }: HousesSectionProps) => {
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const [plots, setPlots] = useState<Plot[]>([]);
  const [buying, setBuying] = useState<Plot | null>(null);
  const [busy, setBusy] = useState(false);
  const [buyingHouse, setBuyingHouse] = useState<ListedHouse | null>(null);
  // Stage 7: houses the current character belongs to (owner, resident, guest) — it may step inside.
  const [memberOf, setMemberOf] = useState<Set<number>>(new Set());
  const [entering, setEntering] = useState<number | null>(null);

  const load = useCallback(() => {
    plotsAtLocation(locationId)
      .then(setPlots)
      .catch((e) => toast.error(apiErrorMessage(e, 'Не удалось загрузить дома локации')));
  }, [locationId]);

  useEffect(load, [load]);

  useEffect(() => {
    if (!characterId) {
      setMemberOf(new Set());
      return;
    }
    myHouses()
      .then((list) => setMemberOf(new Set(list.filter((h) => h.character?.id === characterId).map((h) => h.id))))
      .catch((e) => toast.error(apiErrorMessage(e, 'Не удалось загрузить ваши дома')));
  }, [characterId]);

  const enter = async (houseId: number) => {
    if (!characterId) return;
    setEntering(houseId);
    try {
      const r = await enterHouse(houseId, characterId);
      void dispatch(getMe()); // the header's «back to the house» link
      navigate(r.room_id != null ? `/houses/${houseId}/room/${r.room_id}` : `/houses/${houseId}`);
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось войти в дом'));
    } finally {
      setEntering(null);
    }
  };

  const buy = async (plot: Plot) => {
    if (!characterId) return;
    setBuying(null);
    setBusy(true);
    try {
      const { house_id } = await buyPlot(plot.id, characterId);
      toast.success('Дом куплен!');
      // The gold shown in the header comes from /users/me.
      void dispatch(getMe());
      navigate(`/houses/${house_id}`);
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось купить дом'));
      load();
    } finally {
      setBusy(false);
    }
  };

  if (plots.length === 0) return null;

  return (
    <section className="bg-site-bg backdrop-blur-sm rounded-card border border-gold-dark/20 shadow-card overflow-hidden">
      <div className="flex items-center gap-2.5 px-4 sm:px-5 py-3.5 border-b border-white/[0.07]">
        <Home size={18} className="text-gold shrink-0" />
        <h2 className="gold-text text-[13px] font-medium uppercase tracking-[0.08em]">Дома</h2>
        <span className="bg-white/10 text-white/60 text-[10px] font-bold px-2 py-0.5 rounded-full min-w-[20px] text-center">
          {plots.length}
        </span>
        <Link to="/houses/market" className="site-link text-xs ml-auto flex items-center gap-1 shrink-0">
          <Tag size={12} />Продажа домов
        </Link>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 p-3.5 sm:p-4">
        {plots.map((plot) => {
          const house = plot.house;
          return (
            <div key={plot.id} className="flex flex-col rounded-card bg-white/[0.03] border border-white/[0.06] overflow-hidden">
              <div className="aspect-[16/8] bg-black/40 overflow-hidden flex items-center justify-center">
                {(house?.image_url ?? plot.image_url) ? (
                  <img src={(house?.image_url ?? plot.image_url)!} alt="" className="w-full h-full object-cover" />
                ) : (
                  <Home size={32} className="text-white/15" />
                )}
              </div>
              <div className="p-3 flex flex-col gap-1.5 flex-1">
                <h3 className="text-white text-sm font-medium break-words">{house?.name ?? plot.name}</h3>
                {!house && plot.description && (
                  <p className="text-white/55 text-xs line-clamp-2 break-words">{plot.description}</p>
                )}
                {!house && plot.kind === 'empty' ? (
                  <p className="text-white/45 text-xs">
                    <span className="text-gold-light">Пустой участок</span> · мест под комнаты: {plot.cells_open}
                    {plot.cells_total > plot.cells_open ? ` (с пристройками до ${plot.cells_total})` : ''}
                  </p>
                ) : !house && (
                  // A bought house keeps its rooms private (stage 7) — only plots for sale show them.
                  <p className="text-white/45 text-xs">
                    Комнат: {plot.room_count}
                    {plot.cells_total > plot.room_count ? ` · мест на плане: ${plot.cells_total}` : ''}
                  </p>
                )}
                {house ? (
                  <>
                    <p className="text-white/60 text-xs truncate">
                      Хозяин: <span className="text-white">{house.owner?.name ?? '—'}</span>
                    </p>
                    {house.status === 'frozen' && (
                      <p className="text-site-red text-xs flex items-center gap-1"><Snowflake size={12} />Заморожен за неуплату налога</p>
                    )}
                    {house.sale_price != null && (
                      <p className="text-gold text-xs flex items-center gap-1">
                        <Tag size={12} />Продаётся за {house.sale_price.toLocaleString('ru-RU')} золота
                      </p>
                    )}
                    <div className="mt-auto flex gap-2">
                      {memberOf.has(house.id) && isCharacterHere ? (
                        <button type="button" onClick={() => void enter(house.id)} disabled={entering != null}
                          className="btn-blue !w-full !py-1.5 !text-xs flex items-center justify-center gap-1.5 disabled:opacity-50">
                          <DoorOpen size={13} />{entering === house.id ? 'Входим...' : 'Войти'}
                        </button>
                      ) : (
                        <button type="button" onClick={() => navigate(`/houses/${house.id}`)}
                          className="btn-line !w-full !py-1.5 !text-xs">
                          {memberOf.has(house.id) ? 'Открыть' : 'Осмотреть'}
                        </button>
                      )}
                      {house.sale_price != null && characterId && house.owner?.id !== characterId && (
                        <button type="button" onClick={() => setBuyingHouse({
                          id: house.id,
                          name: house.name,
                          price: house.sale_price!,
                          location_id: plot.location_id,
                          location_name: plot.location_name,
                          owner_id: house.owner?.id ?? null,
                          owner_name: house.owner?.name ?? null,
                        })}
                          className="btn-blue !w-full !py-1.5 !text-xs">
                          Купить
                        </button>
                      )}
                    </div>
                  </>
                ) : (
                  <>
                    <p className="text-gold text-xs">Свободен · {plot.price.toLocaleString('ru-RU')} золота</p>
                    {characterId ? (
                      <button type="button" disabled={!isCharacterHere || busy} onClick={() => setBuying(plot)}
                        className="btn-blue !w-full !py-1.5 !text-xs mt-auto disabled:opacity-50">
                        Купить за {plot.price.toLocaleString('ru-RU')}
                      </button>
                    ) : null}
                    {characterId && !isCharacterHere && (
                      <p className="text-white/40 text-[11px]">Чтобы купить, персонаж должен быть в этой локации</p>
                    )}
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {buyingHouse && <BuyListedHouseDialog house={buyingHouse} onClose={() => { setBuyingHouse(null); load(); }} />}

      {buying && (
        <ConfirmDialog
          title="Покупка дома"
          message={buying.kind === 'empty'
            ? `Купить «${buying.name}» за ${buying.price.toLocaleString('ru-RU')} золота? Это пустой участок: комнаты (мест: ${buying.cells_open}${buying.cells_total > buying.cells_open ? `, с пристройками и этажами до ${buying.cells_total}` : ''}) вы построите сами за золото и материалы.`
            : `Купить «${buying.name}» за ${buying.price.toLocaleString('ru-RU')} золота? Дом станет вашим, а комнаты можно будет обставить и открыть гостям.`}
          confirmLabel="Купить"
          onCancel={() => setBuying(null)}
          onConfirm={() => void buy(buying)}
        />
      )}
    </section>
  );
};

export default HousesSection;
