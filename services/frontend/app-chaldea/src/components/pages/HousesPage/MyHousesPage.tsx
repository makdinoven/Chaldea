import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Home, MapPin, Tag } from 'lucide-react';
import { myHouses, type MyHouse } from '../../../api/houses';
import { apiErrorMessage } from '../../../api/errors';

const MY_HOUSE_STATUS_LABEL: Record<MyHouse['status'], string> = {
  owner: 'Хозяин',
  resident: 'Жилец',
  guest: 'Гость',
};

/** «Мои дома» — houses the user's characters own, live in or visit as guests (stage 6b). */
const MyHousesPage = () => {
  const [houses, setHouses] = useState<MyHouse[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    myHouses()
      .then(setHouses)
      .catch((e) => setError(apiErrorMessage(e, 'Не удалось загрузить дома')));
  }, []);

  return (
    <div className="w-full max-w-container mx-auto flex flex-col gap-5 pb-10">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
      <div className="flex flex-col gap-1.5">
        <h1 className="gold-text text-2xl sm:text-3xl font-semibold uppercase tracking-[0.06em]">Мои дома</h1>
        <p className="text-white/60 text-sm max-w-2xl">
          Дома ваших персонажей — свои, те, куда их пустили жить, и те, где они в гостях. Купить дом можно на участке в городской локации
          или у другого игрока на доске продажи.
        </p>
      </div>
        <Link to="/houses/market" className="btn-line !w-full sm:!w-auto !px-5 shrink-0 flex items-center justify-center gap-1.5">
          <Tag size={14} />Продажа домов
        </Link>
      </div>

      {error && <p className="text-site-red text-sm">{error}</p>}
      {!houses && !error && <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />}
      {houses?.length === 0 && (
        <p className="text-white/40 text-sm italic">
          У ваших персонажей пока нет дома. Свободные участки отмечены на картах регионов и в разделе «Дома» на странице локации.
        </p>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {houses?.map((h) => (
          <Link key={`${h.id}-${h.character?.id ?? 0}`} to={`/houses/${h.id}`}
            className="group bg-site-bg backdrop-blur-sm rounded-card border border-white/[0.07] hover:border-gold-dark/50 overflow-hidden flex flex-col transition-colors">
            <div className="relative aspect-[16/8] bg-black/40 overflow-hidden flex items-center justify-center">
              {h.image_url ? (
                <img src={h.image_url} alt="" className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500" />
              ) : (
                <Home size={36} className="text-white/15" />
              )}
              <span className={`absolute top-2 left-2 px-2 py-0.5 rounded-full bg-black/70 text-[11px] ${
                h.status === 'owner' ? 'text-gold' : h.status === 'guest' ? 'text-site-blue' : 'text-white/80'
              }`}>
                {MY_HOUSE_STATUS_LABEL[h.status]}
              </span>
            </div>
            <div className="p-4 flex flex-col gap-2 flex-1">
              <h2 className="text-white text-lg font-medium leading-tight break-words">{h.name}</h2>
              <div className="mt-auto flex items-center gap-3 text-xs text-white/50 flex-wrap">
                {h.character && (
                  <span className="flex items-center gap-1.5 min-w-0">
                    <span className="w-5 h-5 rounded-full overflow-hidden bg-black/40 shrink-0">
                      {h.character.avatar && <img src={h.character.avatar} alt="" className="w-full h-full object-cover" />}
                    </span>
                    <span className="truncate">{h.character.name}</span>
                  </span>
                )}
                {h.location_name && (
                  <span className="flex items-center gap-1 ml-auto min-w-0"><MapPin size={13} className="shrink-0" /><span className="truncate">{h.location_name}</span></span>
                )}
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
};

export default MyHousesPage;
