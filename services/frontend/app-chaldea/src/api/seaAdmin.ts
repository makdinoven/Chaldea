import axios from 'axios';
import { apiErrorMessage } from './errors';
import type {
  SeaCandidates,
  SeaLeg,
  SeaLegsPreviewRequest,
  SeaPort,
  SeaSettings,
  SeaShipAdmin,
  SeaShipCreate,
  SeaShipUpdate,
  SeaZone,
} from '../types/seaAdmin';

/**
 * FEAT-213 admin «Корабли» API. Auth header comes from axiosSetup.
 *
 * RBAC (no new permissions): reads need `locations:read`; create `locations:create`;
 * edit and settings `locations:update`; delete `locations:delete`.
 */
const BASE = '/characters/admin/sea';

/** Backend limits mirrored for client-side validation (`sea_core` ranges). */
export const SEA_LIMITS = {
  name: [1, 100],
  capacity: [0, 200],
  crew_slots: [0, 20],
  boarding_minutes: [1, 1440],
  zone_minutes: [1, 1440],
  fare_base: [0, 1_000_000],
  fare_per_zone: [0, 1_000_000],
  stops: [2, 30],
  sailor_post_min_chars: [300, 20000],
  stowaway_base_pct: [0, 100],
  stowaway_wanted_points: [1, 1000],
  path_max_zones: [10, 1000],
} as const;

export type SeaLimitKey = keyof typeof SEA_LIMITS;

/** Russian field names for validation messages (422 `loc` → label). */
export const SEA_FIELD_LABELS: Record<string, string> = {
  name: 'Название',
  captain_npc_id: 'Капитан',
  deck_location_id: 'Палуба',
  capacity: 'Мест для пассажиров',
  crew_slots: 'Мест для матросов',
  boarding_minutes: 'Сборы в порту (мин)',
  zone_minutes: 'Время на морскую зону (мин)',
  fare_base: 'Базовая цена',
  fare_per_zone: 'Цена за зону',
  is_loop: 'По кругу',
  is_active: 'Ходит',
  stops: 'Маршрут',
  port_location_id: 'Порт',
  path_override: 'Ручной путь',
  sailor_post_min_chars: 'Длина поста матроса',
  stowaway_base_pct: 'Шанс поймать зайца',
  stowaway_wanted_points: 'Очки розыска за зайца',
  path_max_zones: 'Предел зон на участок',
};

/** «Поле «X»: допустимо от A до B» when the field has known limits. */
export const seaRangeText = (key: SeaLimitKey): string => {
  const [min, max] = SEA_LIMITS[key];
  return `«${SEA_FIELD_LABELS[key] ?? key}»: допустимо от ${min.toLocaleString('ru-RU')} до ${max.toLocaleString('ru-RU')}`;
};

/**
 * Any failure → Russian text. Pydantic 422s (English `msg`) are rewritten into
 * «Неверное значение поля …» with the field's allowed range when known.
 */
export const seaAdminError = (error: unknown, fallback: string): string => {
  if (axios.isAxiosError(error) && error.response?.status === 422) {
    const detail = (error.response.data as { detail?: unknown } | undefined)?.detail;
    if (Array.isArray(detail) && detail[0]) {
      const loc = (detail[0] as { loc?: unknown }).loc;
      const parts = Array.isArray(loc) ? loc.filter((p): p is string => typeof p === 'string' && p !== 'body') : [];
      const stopIdx = Array.isArray(loc) ? loc.find((p): p is number => typeof p === 'number') : undefined;
      const field = parts[parts.length - 1];
      if (field && field in SEA_LIMITS) return `Неверное значение: ${seaRangeText(field as SeaLimitKey)}`;
      if (field && SEA_FIELD_LABELS[field]) {
        const where = stopIdx !== undefined ? ` (остановка ${stopIdx + 1})` : '';
        return `Неверное значение поля «${SEA_FIELD_LABELS[field]}»${where}`;
      }
    }
    return 'Некорректные данные — проверьте поля формы';
  }
  return apiErrorMessage(error, fallback);
};

// ---------- A1–A7 (character-service) ----------

export const fetchSeaShips = async (): Promise<SeaShipAdmin[]> => {
  const { data } = await axios.get<SeaShipAdmin[]>(`${BASE}/ships`);
  return data;
};

export const createSeaShip = async (body: SeaShipCreate): Promise<SeaShipAdmin> => {
  const { data } = await axios.post<SeaShipAdmin>(`${BASE}/ships`, body);
  return data;
};

export const updateSeaShip = async (id: number, body: SeaShipUpdate): Promise<SeaShipAdmin> => {
  const { data } = await axios.patch<SeaShipAdmin>(`${BASE}/ships/${id}`, body);
  return data;
};

export const deleteSeaShip = async (id: number): Promise<void> => {
  await axios.delete(`${BASE}/ships/${id}`);
};

export const previewSeaLegs = async (body: SeaLegsPreviewRequest): Promise<SeaLeg[]> => {
  const { data } = await axios.post<SeaLeg[]>(`${BASE}/legs/preview`, body);
  return data;
};

/** Free decks and Captains; the edited ship's own deck/Captain are included via `shipId`. */
export const fetchSeaCandidates = async (shipId?: number): Promise<SeaCandidates> => {
  const { data } = await axios.get<SeaCandidates>(`${BASE}/candidates`, {
    params: shipId ? { ship_id: shipId } : undefined,
  });
  return data;
};

export const fetchSeaSettings = async (): Promise<SeaSettings> => {
  const { data } = await axios.get<SeaSettings>(`${BASE}/settings`);
  return data;
};

export const saveSeaSettings = async (body: SeaSettings): Promise<SeaSettings> => {
  const { data } = await axios.put<SeaSettings>(`${BASE}/settings`, body);
  return data;
};

// ---------- L5 / L8 (locations-service) ----------

export const fetchSeaPorts = async (): Promise<SeaPort[]> => {
  const { data } = await axios.get<SeaPort[]>('/locations/admin/sea-ports');
  return data;
};

export const fetchSeaZones = async (): Promise<SeaZone[]> => {
  const { data } = await axios.get<SeaZone[]>('/locations/admin/sea-zones');
  return data;
};
