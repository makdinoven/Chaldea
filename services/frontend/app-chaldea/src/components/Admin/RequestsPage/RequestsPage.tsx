import { useEffect, useMemo, useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import Request from '../Request/Request';
import type { RequestData } from '../Request/Request';
import { apiErrorMessage } from '../../../api/errors';
import { fetchOrigins } from '../../../api/origins';
import type { OriginCountry } from '../../../api/origins';
import { fetchStartingPoints } from '../../../api/startingPoints';
import { fetchGameTime } from '../../../redux/actions/gameTimeActions';
import { fetchRaces } from '../../../redux/slices/racesSlice';
import { selectCurrentGameYear } from '../../../redux/slices/gameTimeSlice';
import { useAppDispatch, useAppSelector } from '../../../redux/store';

/**
 * FEAT-154 (task #21) — the reference data the passport needs is loaded ONCE
 * here, never per request row: origins (rule 11), subrace typical origins, and
 * the curated starting points that name `start_location_id`.
 */
interface ModerationRequest extends RequestData {
  user_id: number;
  id_class: number;
  id_race: number;
  request_type: string;
}

export default function RequestsPage() {
  const dispatch = useAppDispatch();

  const [data, setData] = useState<ModerationRequest[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const [origins, setOrigins] = useState<OriginCountry[]>([]);
  const [locationNames, setLocationNames] = useState<Map<number, string>>(new Map());

  const races = useAppSelector((state) => state.races.races);
  const racesError = useAppSelector((state) => state.races.error);
  const currentGameYear = useAppSelector(selectCurrentGameYear);
  const gameTimeLoaded = useAppSelector((state) => state.gameTime.computed !== null);

  useEffect(() => {
    axios
      .get('/characters/moderation-requests')
      .then((response) => {
        const dataArray = Object.values(response.data ?? {}) as ModerationRequest[];
        setData(dataArray);
        setLoading(false);
      })
      .catch((err) => {
        setError(apiErrorMessage(err, 'Не удалось загрузить заявки. Попробуйте позже.'));
        setLoading(false);
      });
  }, []);

  // Reference data — one request each, for the whole page.
  useEffect(() => {
    fetchOrigins()
      .then(setOrigins)
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'Не удалось загрузить происхождения.');
      });

    fetchStartingPoints()
      .then((points) => setLocationNames(new Map(points.map((p) => [p.id, p.name]))))
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'Не удалось загрузить стартовые точки.');
      });
  }, []);

  useEffect(() => {
    if (races.length === 0) dispatch(fetchRaces());
  }, [dispatch, races.length]);

  useEffect(() => {
    if (!gameTimeLoaded) dispatch(fetchGameTime());
  }, [dispatch, gameTimeLoaded]);

  useEffect(() => {
    if (racesError) toast.error(racesError);
  }, [racesError]);

  /** subrace id → `typical_origin_ids` (rule 11). */
  const typicalBySubrace = useMemo(() => {
    const map = new Map<number, number[]>();
    races.forEach((race) => {
      race.subraces?.forEach((subrace) => {
        if (subrace.typical_origin_ids?.length) {
          map.set(subrace.id_subrace, subrace.typical_origin_ids);
        }
      });
    });
    return map;
  }, [races]);

  if (loading) {
    return <span className="text-white text-lg">Загрузка...</span>;
  }

  if (error) {
    return (
      <div className="flex flex-col items-center gap-4 mt-8">
        <p className="text-site-red text-xl font-semibold text-center">{error}</p>
      </div>
    );
  }

  const handleStatusChange = (requestId: number) => {
    setData((prev) => prev.filter((item) => item.request_id !== requestId));
  };

  const pendingRequests = data.filter((item) => item.status === 'pending');

  return (
    <>
      <h1 className="gold-text mb-6 text-center text-2xl font-semibold uppercase sm:text-[32px]">
        Заявки на персонажей
      </h1>
      <div className="flex flex-col gap-10 sm:gap-20">
        {pendingRequests.length > 0 ? (
          pendingRequests.map((item) => (
            <Request
              key={item.request_id}
              data={item}
              requestType={item.request_type}
              onStatusChange={handleStatusChange}
              origins={origins}
              typicalOriginIds={
                item.id_subrace ? typicalBySubrace.get(item.id_subrace) ?? null : null
              }
              startLocationName={
                item.start_location_id ? locationNames.get(item.start_location_id) ?? null : null
              }
              currentGameYear={currentGameYear}
            />
          ))
        ) : (
          <h2 className="gold-text text-center text-xl font-semibold sm:text-[26px]">
            Заявок нет
          </h2>
        )}
      </div>
    </>
  );
}
