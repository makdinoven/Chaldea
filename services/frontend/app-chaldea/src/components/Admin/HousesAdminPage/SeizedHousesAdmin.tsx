import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { Armchair, Landmark, MapPin, Package } from 'lucide-react';
import { adminGetSeizedHouses, ROOM_TYPE_LABEL, SEIZE_REASON_LABEL, type SeizedHouse } from '../../../api/houses';
import { apiErrorMessage } from '../../../api/errors';
import { formatServerDateTime } from '../../../utils/serverDate';
import CharAvatar from '../../pages/HousesPage/CharAvatar';

/** Admin: the archive of houses the city took away (FEAT-180 stage 4). */
const SeizedHousesAdmin = () => {
  const [houses, setHouses] = useState<SeizedHouse[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminGetSeizedHouses()
      .then(setHouses)
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить изъятые дома');
        setError(msg);
        toast.error(msg);
      });
  }, []);

  if (error) return <p className="text-site-red text-sm">{error}</p>;
  if (!houses) return <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />;

  return (
    <div className="flex flex-col gap-3">
      <p className="text-white/60 text-sm max-w-3xl">
        Дома, изъятые городом: их участки снова продаются, а постройки, мебель и вещи кладовой лежат здесь, в архиве.
      </p>
      {houses.length === 0 && <p className="text-white/40 text-sm italic">Изъятых домов нет.</p>}
      {houses.map((h) => (
        <article key={h.id} className="bg-site-bg backdrop-blur-sm rounded-card border border-white/[0.07] p-3 sm:p-4 flex flex-col gap-2.5">
          <div className="flex flex-col sm:flex-row sm:items-center gap-2 sm:gap-4">
            <div className="flex items-center gap-2 min-w-0 flex-1">
              <Landmark size={16} className="text-gold shrink-0" />
              <span className="text-white text-sm font-medium truncate">{h.name}</span>
              <span className="text-white/30 text-xs shrink-0">#{h.id}</span>
            </div>
            <span className={`self-start sm:self-auto px-2 py-0.5 rounded-full text-[11px] border ${
              h.reason === 'tax' ? 'border-site-red/50 text-site-red' : 'border-gold/40 text-gold'
            }`}>
              {h.reason ? SEIZE_REASON_LABEL[h.reason] : 'причина неизвестна'}
            </span>
          </div>
          <div className="flex items-center gap-x-4 gap-y-1.5 flex-wrap text-xs text-white/55">
            {h.owner && (
              <span className="flex items-center gap-1.5 min-w-0">
                <CharAvatar src={h.owner.avatar} size="w-5 h-5" />
                <span className="truncate">{h.owner.name}</span>
              </span>
            )}
            {h.location_name && <span className="flex items-center gap-1"><MapPin size={12} />{h.location_name}</span>}
            <span>Изъят: {formatServerDateTime(h.seized_at)}</span>
            <span className="flex items-center gap-1"><Package size={12} />В кладовой: {h.stored_stacks} стоп.</span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {h.rooms.length === 0 && <span className="text-white/40 text-xs italic">Комнат не было</span>}
            {h.rooms.map((r, i) => (
              <span key={`${r.room_type}-${i}`} className="px-2 py-0.5 rounded-full bg-white/[0.05] border border-white/[0.08] text-white/75 text-[11px]">
                {r.name} · {ROOM_TYPE_LABEL[r.room_type]}{r.level >= 1 ? ` · ур. ${r.level}` : ' · стройка'}
              </span>
            ))}
          </div>
          {h.furniture.length > 0 && (
            <p className="text-white/55 text-xs flex items-start gap-1.5 break-words">
              <Armchair size={12} className="shrink-0 mt-0.5" />
              <span>Мебель: {h.furniture.join(', ')}</span>
            </p>
          )}
        </article>
      ))}
    </div>
  );
};

export default SeizedHousesAdmin;
