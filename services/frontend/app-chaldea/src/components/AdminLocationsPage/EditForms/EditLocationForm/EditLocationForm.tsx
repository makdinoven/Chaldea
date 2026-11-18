import { useState, useEffect } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import axios from 'axios';
import toast from 'react-hot-toast';
import LocationSearch from '../../../CommonComponents/LocationSearch/LocationSearch';
import {
  createLocation,
  updateLocation,
  uploadLocationImage,
  uploadLocationIcon,
  updateLocationNeighbors,
  fetchLocationDetails,
  fetchLocationsList,
  fetchAllLocations,
} from '../../../../redux/actions/locationEditActions';
import { selectLocationEdit } from '../../../../redux/selectors/locationSelectors';
import LocationNeighborsEditor from './LocationNeighborsEditor/LocationNeighborsEditor';
import GatheringNodesEditor from './GatheringNodesEditor/GatheringNodesEditor';
import FactionAccessField from '../../../Admin/FactionsPage/FactionAccessField';
import type { AppDispatch } from '../../../../redux/store';
import { fetchSeaZones } from '../../../../api/seaAdmin';
import type { SeaZone } from '../../../../types/seaAdmin';

interface Neighbor {
  neighbor_id: number;
  energy_cost: number;
  /** Transition created by a region arrow; edited on the region map, never re-saved here. */
  is_auto_arrow?: boolean;
}

interface LocationFormData {
  name: string;
  district_id: string | number;
  parent_id: number | null;
  description: string;
  recommended_level: number;
  quick_travel_marker: boolean;
  no_quick_move: boolean;
  marker_type: 'safe' | 'dangerous' | 'dungeon';
  image_url?: string;
  id?: number | string;
  /**
   * FEAT-154 (rules 18, 19) — a curated starting point plus the short
   * «почему герои начинают здесь» blurb.
   *
   * ⚠️ Note N6: both fields are accepted by the create/update request bodies
   * but are NOT part of the location response schemas — the only place they can
   * be read back is `GET /locations/{id}/details`, which is what
   * `fetchLocationDetails` calls.
   */
  is_starting: boolean;
  starting_blurb: string;
  /** FEAT-213: ships stop here; `port_sea_zone_id` = the sea zone the port opens to (ports only). */
  is_port: boolean;
  /** FEAT-213: a sea zone of a hidden country (never a port / starting point). */
  is_sea_zone: boolean;
  port_sea_zone_id: number | null;
  /** FEAT-216: customs post — legal foreign caravans are inspected here (never on a ship / sea zone). */
  is_customs: boolean;
  [key: string]: unknown;
}

interface InitialData {
  district_id?: number;
  name?: string;
  description?: string;
  parent_id?: number | null;
  recommended_level?: number;
  quick_travel_marker?: boolean;
  no_quick_move?: boolean;
  marker_type?: 'safe' | 'dangerous' | 'dungeon';
  image_url?: string;
  map_icon_url?: string;
  id?: number;
  is_starting?: boolean;
  starting_blurb?: string | null;
  is_port?: boolean;
  is_sea_zone?: boolean;
  port_sea_zone_id?: number | null;
  is_customs?: boolean;
}

/** Backend `detail` of a rejected thunk (`rejectWithValue(error.response?.data || error.message)`). */
const rejectedMessage = (err: unknown, fallback: string): string => {
  if (typeof err === 'string' && err.trim()) return err;
  const detail = (err as { detail?: unknown } | null)?.detail;
  if (typeof detail === 'string' && detail.trim()) return detail;
  return fallback;
};

interface EditLocationFormProps {
  locationId?: number | string;
  initialData?: InitialData;
  onCancel: () => void;
  onSuccess: (districtId?: number | string, dispatch?: AppDispatch) => void;
}

const MARKER_TYPE_OPTIONS = [
  { value: 'safe', label: 'Безопасная' },
  { value: 'dangerous', label: 'Опасная' },
  { value: 'dungeon', label: 'Подземелье' },
] as const;

const EditLocationForm = ({
  locationId = 'new',
  initialData,
  onCancel,
  onSuccess,
}: EditLocationFormProps) => {
  const dispatch = useDispatch<AppDispatch>();
  const { currentLocation, allLocations } = useSelector(selectLocationEdit) as {
    currentLocation: Record<string, unknown> | null;
    districtLocations: { id: number; name: string }[];
    allLocations: { id: number; name: string }[];
  };

  const [formData, setFormData] = useState<LocationFormData>({
    name: '',
    district_id: '',
    parent_id: null,
    description: '',
    recommended_level: 1,
    quick_travel_marker: false,
    no_quick_move: false,
    marker_type: 'safe',
    ...initialData,
    is_starting: initialData?.is_starting ?? false,
    starting_blurb: initialData?.starting_blurb ?? '',
    is_port: initialData?.is_port ?? false,
    is_sea_zone: initialData?.is_sea_zone ?? false,
    port_sea_zone_id: initialData?.port_sea_zone_id ?? null,
    is_customs: initialData?.is_customs ?? false,
  });
  const [seaZones, setSeaZones] = useState<SeaZone[]>([]);
  const [seaZonesError, setSeaZonesError] = useState<string | null>(null);
  /** Is the location's country hidden (sea zones live there); null = unknown (e.g. a new location). */
  const [hiddenCountry, setHiddenCountry] = useState<boolean | null>(null);

  const [isUploading, setIsUploading] = useState(false);
  const [selectedImage, setSelectedImage] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string>(initialData?.image_url || '');
  const [iconFile, setIconFile] = useState<File | null>(null);
  const [iconPreview, setIconPreview] = useState<string | null>(initialData?.map_icon_url || null);
  const [neighbors, setNeighbors] = useState<Neighbor[]>([]);

  useEffect(() => {
    if (locationId !== 'new') {
      dispatch(fetchLocationDetails(locationId as number) as unknown as ReturnType<typeof fetchLocationDetails>);
    }
  }, [dispatch, locationId]);

  useEffect(() => {
    if (locationId !== 'new' && formData.district_id) {
      dispatch(fetchLocationsList(formData.district_id as number) as unknown as ReturnType<typeof fetchLocationsList>);
    }
  }, [dispatch, formData.district_id, locationId]);

  useEffect(() => {
    dispatch(fetchAllLocations() as unknown as ReturnType<typeof fetchAllLocations>);
  }, [dispatch]);

  // FEAT-213: sea zones for the port's «выход в море» select (L8)
  useEffect(() => {
    let cancelled = false;
    fetchSeaZones()
      .then((rows) => {
        if (!cancelled) setSeaZones(rows);
      })
      .catch(() => {
        if (!cancelled) setSeaZonesError('Не удалось загрузить морские зоны');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // FEAT-213: the «Морская зона» flag is offered only for locations of hidden countries
  useEffect(() => {
    if (locationId === 'new' || typeof locationId !== 'number') return undefined;
    let cancelled = false;
    Promise.all([
      axios.get<{ country_id?: number | null }>(`/locations/${locationId}/client/details`),
      axios.get<{ id: number; is_hidden?: boolean }[]>('/locations/countries/list'),
    ])
      .then(([details, countries]) => {
        if (cancelled) return;
        const country = countries.data.find((c) => c.id === details.data.country_id);
        setHiddenCountry(country ? Boolean(country.is_hidden) : null);
      })
      .catch(() => {
        // Unknown → the flag stays offered; the backend refuses it outside a hidden country (409 shown).
        if (!cancelled) setHiddenCountry(null);
      });
    return () => {
      cancelled = true;
    };
  }, [locationId]);

  useEffect(() => {
    if (currentLocation && locationId !== 'new') {
      setFormData({
        ...(currentLocation as unknown as LocationFormData),
        recommended_level: (currentLocation.recommended_level as number) || 1,
        parent_id: (currentLocation.parent_id as number) || null,
        quick_travel_marker: (currentLocation.quick_travel_marker as boolean) ?? false,
        no_quick_move: (currentLocation.no_quick_move as boolean) ?? false,
        marker_type: (currentLocation.marker_type as 'safe' | 'dangerous' | 'dungeon') || 'safe',
        // N6: these two only ever come back from `/details`.
        is_starting: (currentLocation.is_starting as boolean) ?? false,
        starting_blurb: (currentLocation.starting_blurb as string | null) ?? '',
        is_port: Boolean(currentLocation.is_port),
        is_sea_zone: Boolean(currentLocation.is_sea_zone),
        port_sea_zone_id: (currentLocation.port_sea_zone_id as number | null) ?? null,
        is_customs: Boolean(currentLocation.is_customs),
      });
      if (currentLocation.map_icon_url && !iconFile) {
        setIconPreview(currentLocation.map_icon_url as string);
      }
      if (Array.isArray(currentLocation.neighbors)) {
        setNeighbors(
          (currentLocation.neighbors as Neighbor[]).map((n) => ({
            neighbor_id: n.neighbor_id,
            energy_cost: n.energy_cost || 1,
            is_auto_arrow: Boolean(n.is_auto_arrow),
          }))
        );
      } else {
        setNeighbors([]);
      }
    }
  }, [currentLocation, locationId]);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>
  ) => {
    if (!e.target || !e.target.name) return;
    const { name, value, type } = e.target;
    setFormData((prev) => ({
      ...prev,
      [name]: type === 'number' ? (value === '' ? '' : Number(value)) : value,
    }));
  };

  const handleParentChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const { value } = e.target;
    setFormData((prev) => ({
      ...prev,
      parent_id: value ? Number(value) : null,
    }));
  };

  const handleQuickTravelChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData((prev) => ({
      ...prev,
      quick_travel_marker: e.target.checked,
    }));
  };

  const handleNoQuickMoveChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData((prev) => ({
      ...prev,
      no_quick_move: e.target.checked,
    }));
  };

  const handleIsStartingChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData((prev) => ({
      ...prev,
      is_starting: e.target.checked,
    }));
  };

  // FEAT-213: only valid combinations — a sea zone is never a port or a starting point.
  const handleIsPortChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const checked = e.target.checked;
    setFormData((prev) => ({
      ...prev,
      is_port: checked,
      is_sea_zone: checked ? false : prev.is_sea_zone,
      port_sea_zone_id: checked ? prev.port_sea_zone_id : null,
    }));
  };

  const handleIsSeaZoneChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const checked = e.target.checked;
    setFormData((prev) => ({
      ...prev,
      is_sea_zone: checked,
      is_port: checked ? false : prev.is_port,
      port_sea_zone_id: checked ? null : prev.port_sea_zone_id,
      is_starting: checked ? false : prev.is_starting,
      is_customs: checked ? false : prev.is_customs,
    }));
  };

  // FEAT-216: a customs post never stands in a sea zone (the backend refuses it with 400).
  const handleIsCustomsChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const checked = e.target.checked;
    setFormData((prev) => ({ ...prev, is_customs: checked }));
  };

  const handlePortZoneChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const { value } = e.target;
    setFormData((prev) => ({ ...prev, port_sea_zone_id: value ? Number(value) : null }));
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setSelectedImage(file);
        setImagePreview(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleIconFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setIconFile(file);
        setIconPreview(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleNeighborAdd = (neighbor: Neighbor) => {
    if (!neighbor || neighbors.some((n) => n.neighbor_id === neighbor.neighbor_id)) return;
    setNeighbors((prev) => [...prev, neighbor]);
  };

  const handleNeighborRemove = (neighborId: number) => {
    setNeighbors((prev) => prev.filter((n) => n.neighbor_id !== neighborId));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isUploading) return;

    if (!formData.name) {
      toast.error('Заполните обязательное поле: название');
      return;
    }

    setIsUploading(true);
    try {
      const { parent_id, ...rest } = formData;
      const locationData = {
        ...rest,
        ...(parent_id ? { parent_id: Number(parent_id) } : {}),
        recommended_level: formData.recommended_level ? Number(formData.recommended_level) : 1,
        type: 'location',
        quick_travel_marker: Boolean(formData.quick_travel_marker),
        no_quick_move: Boolean(formData.no_quick_move),
        district_id: formData.district_id ? Number(formData.district_id) : null,
        marker_type: formData.marker_type || 'safe',
        is_starting: Boolean(formData.is_starting),
        // An empty blurb is sent as null so the backend stores NULL, not ''.
        starting_blurb: formData.starting_blurb?.trim() ? formData.starting_blurb.trim() : null,
        // FEAT-213: a port's zone 0 = clear; non-ports send null (the backend clears it).
        is_port: Boolean(formData.is_port) && !formData.is_sea_zone,
        is_sea_zone: Boolean(formData.is_sea_zone),
        port_sea_zone_id:
          formData.is_port && !formData.is_sea_zone
            ? formData.port_sea_zone_id ?? (locationId === 'new' ? null : 0)
            : null,
        is_customs: Boolean(formData.is_customs) && !formData.is_sea_zone,
      };

      const action = locationId !== 'new' ? updateLocation : createLocation;
      const result = await dispatch(action(locationData as never) as unknown as ReturnType<typeof action>).unwrap();

      if (locationId === 'new' && formData.parent_id) {
        try {
          await dispatch(
            updateLocation({ id: formData.parent_id, type: 'subdistrict' } as never) as unknown as ReturnType<typeof updateLocation>
          ).unwrap();
        } catch {
          console.error('Ошибка при обновлении типа родителя');
        }
      }

      if (selectedImage) {
        try {
          await dispatch(
            uploadLocationImage({
              locationId: (result as { id: number }).id,
              file: selectedImage,
            } as never) as unknown as ReturnType<typeof uploadLocationImage>
          ).unwrap();
        } catch {
          toast.error('Ошибка при загрузке изображения');
        }
      }

      if (iconFile) {
        try {
          await dispatch(
            uploadLocationIcon({
              locationId: (result as { id: number }).id,
              file: iconFile,
            } as never) as unknown as ReturnType<typeof uploadLocationIcon>
          ).unwrap();
        } catch {
          toast.error('Ошибка при загрузке иконки для карты');
        }
      }

      const newLocationId = locationId === 'new' ? (result as { id: number }).id : locationId;
      // Arrow transitions belong to the region map; sending them here
      // re-created them as manual links and duplicated the transition.
      const manualNeighbors = neighbors.filter((n) => !n.is_auto_arrow);
      if (manualNeighbors.length > 0) {
        try {
          await dispatch(
            updateLocationNeighbors({
              locationId: newLocationId,
              neighbors: manualNeighbors,
            } as never) as unknown as ReturnType<typeof updateLocationNeighbors>
          ).unwrap();
        } catch {
          toast.error('Ошибка при обновлении соседей');
        }
      }

      toast.success(locationId === 'new' ? 'Локация создана' : 'Локация обновлена');
      onSuccess(formData.district_id, dispatch);
    } catch (err) {
      // 409s (ports / sea zones / decks) carry a Russian `detail` — show it as is.
      toast.error(rejectedMessage(err, 'Ошибка при сохранении локации'));
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div
      className="text-[#d4e6f3]"
      onClick={(e) => e.stopPropagation()}
    >
      <form onSubmit={handleSubmit}>
        <div className="mb-6">
          <h3 className="text-white mb-4 pb-2 border-b border-white/10">Основная информация</h3>

          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">НАЗВАНИЕ:</label>
            <input
              type="text"
              name="name"
              value={formData.name || ''}
              onChange={handleChange}
              required
              className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none"
            />
          </div>

          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">ОПИСАНИЕ:</label>
            <textarea
              name="description"
              value={formData.description || ''}
              onChange={handleChange}
              rows={4}
              className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none resize-y min-h-[100px]"
            />
          </div>

          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">ТИП МАРКЕРА:</label>
            <select
              name="marker_type"
              value={formData.marker_type}
              onChange={handleChange}
              className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none"
            >
              {MARKER_TYPE_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>

          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">РЕКОМЕНДУЕМЫЙ УРОВЕНЬ:</label>
            <input
              type="number"
              name="recommended_level"
              value={formData.recommended_level || ''}
              onChange={handleChange}
              min="1"
              className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none"
            />
          </div>

          <div className="mb-4">
            <label className="flex items-center gap-2 text-[#d4e6f3] cursor-pointer">
              <input
                type="checkbox"
                name="quick_travel_marker"
                checked={formData.quick_travel_marker}
                onChange={handleQuickTravelChange}
                className="w-4 h-4"
              />
              Возможность быстрого перехода
            </label>
          </div>

          <div className="mb-4">
            <label className="flex items-center gap-2 text-[#d4e6f3] cursor-pointer">
              <input
                type="checkbox"
                name="no_quick_move"
                checked={formData.no_quick_move}
                onChange={handleNoQuickMoveChange}
                className="w-4 h-4"
              />
              Запретить быстрое перемещение
            </label>
          </div>

          <div className="mb-4 p-3 sm:p-4 rounded border border-white/10 bg-black/20">
            <label className="flex items-start gap-2 text-[#d4e6f3] cursor-pointer">
              <input
                type="checkbox"
                name="is_starting"
                checked={Boolean(formData.is_starting)}
                onChange={handleIsStartingChange}
                disabled={Boolean(formData.is_sea_zone)}
                className="w-4 h-4 mt-0.5 flex-shrink-0"
              />
              <span>Стартовая точка Скитальцев</span>
            </label>
            <p className="mt-1 ml-6 text-[#8ab3d5]/70 text-xs">
              Локация попадёт в курируемый список первого назначения при создании персонажа.
            </p>

            {formData.is_starting && (
              <div className="mt-4">
                <label className="block mb-2 text-[#8ab3d5] font-medium">
                  ПОЧЕМУ ГЕРОИ НАЧИНАЮТ ЗДЕСЬ:
                </label>
                <textarea
                  name="starting_blurb"
                  value={(formData.starting_blurb as string) || ''}
                  onChange={handleChange}
                  rows={3}
                  maxLength={1000}
                  placeholder="Короткий текст, который увидит игрок на шаге «Контракт»"
                  className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none resize-y"
                />
              </div>
            )}
          </div>

          {/* FEAT-213: port / sea zone */}
          <div className="mb-4 p-3 sm:p-4 rounded border border-white/10 bg-black/20 flex flex-col gap-3">
            <div>
              <label className="flex items-start gap-2 text-[#d4e6f3] cursor-pointer">
                <input
                  type="checkbox"
                  name="is_port"
                  checked={Boolean(formData.is_port)}
                  onChange={handleIsPortChange}
                  disabled={Boolean(formData.is_sea_zone)}
                  className="w-4 h-4 mt-0.5 flex-shrink-0"
                />
                <span>Порт (здесь швартуются корабли)</span>
              </label>
              {formData.is_port && (
                <div className="mt-3 sm:ml-6">
                  <label className="block mb-2 text-[#8ab3d5] font-medium">ВЫХОД В МОРЕ (МОРСКАЯ ЗОНА):</label>
                  <select
                    value={formData.port_sea_zone_id ?? ''}
                    onChange={handlePortZoneChange}
                    className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none"
                  >
                    <option value="">— не задан (корабли сюда не заходят) —</option>
                    {seaZones.map((z) => (
                      <option key={z.id} value={z.id}>
                        {z.name}
                        {z.region_name ? ` (${z.region_name})` : ''}
                      </option>
                    ))}
                  </select>
                  {seaZonesError && <p className="mt-1 text-site-red text-xs">{seaZonesError}</p>}
                  {!seaZonesError && seaZones.length === 0 && (
                    <p className="mt-1 text-[#8ab3d5]/70 text-xs">
                      Морских зон пока нет — создайте их в скрытой стране (например, «Моря»).
                    </p>
                  )}
                </div>
              )}
            </div>

            {/* FEAT-216: customs post */}
            <div>
              <label className="flex items-start gap-2 text-[#d4e6f3] cursor-pointer">
                <input
                  type="checkbox"
                  name="is_customs"
                  checked={Boolean(formData.is_customs)}
                  onChange={handleIsCustomsChange}
                  disabled={Boolean(formData.is_sea_zone)}
                  className="w-4 h-4 mt-0.5 flex-shrink-0"
                />
                <span>Таможня (пост досмотра караванов)</span>
              </label>
              <p className="mt-1 ml-6 text-[#8ab3d5]/70 text-xs">
                Законный караван из другой страны идёт через пост страны назначения, стоит на досмотре и платит
                пошлину в казну. Порт с таможней досматривает всё, что приходит морем. Контрабандисты посты обходят.
                Нельзя ставить на корабле и в морской зоне.
              </p>
            </div>

            {(hiddenCountry !== false || formData.is_sea_zone) && (
              <div>
                <label className="flex items-start gap-2 text-[#d4e6f3] cursor-pointer">
                  <input
                    type="checkbox"
                    name="is_sea_zone"
                    checked={Boolean(formData.is_sea_zone)}
                    onChange={handleIsSeaZoneChange}
                    disabled={Boolean(formData.is_port)}
                    className="w-4 h-4 mt-0.5 flex-shrink-0"
                  />
                  <span>Морская зона</span>
                </label>
                <p className="mt-1 ml-6 text-[#8ab3d5]/70 text-xs">
                  Только в скрытой стране (например, «Моря»): здесь ходят корабли, игроки сюда не заходят.
                  Соединяется только с другими морскими зонами; не порт и не стартовая точка.
                </p>
              </div>
            )}
          </div>

          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">РОДИТЕЛЬСКАЯ ЛОКАЦИЯ:</label>
            <LocationSearch
              name="parent_id"
              value={formData.parent_id}
              onChange={handleParentChange}
              locations={allLocations || []}
              placeholder="Выберите родительскую локацию (необязательно)"
            />
          </div>

          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">ИЗОБРАЖЕНИЕ:</label>
            <input
              type="file"
              accept="image/*"
              onChange={handleFileChange}
              className="text-[#d4e6f3] text-sm"
            />
            {(imagePreview || formData.image_url) && (
              <div className="mt-2">
                <img
                  src={imagePreview || formData.image_url}
                  alt="Preview"
                  className="max-w-full max-h-[200px] rounded border border-white/10"
                />
              </div>
            )}
          </div>

          <div className="mb-4">
            <label className="block mb-2 text-[#8ab3d5] font-medium">ИКОНКА НА КАРТЕ (PNG):</label>
            <input
              type="file"
              accept="image/*"
              onChange={handleIconFileChange}
              className="text-[#d4e6f3] text-sm"
            />
            {(iconPreview || (currentLocation as Record<string, unknown> | null)?.map_icon_url) && (
              <div className="mt-2">
                <img
                  src={iconPreview || String((currentLocation as Record<string, unknown>)?.map_icon_url || '')}
                  alt="Иконка на карте"
                  className="max-h-[80px] w-auto object-contain"
                />
              </div>
            )}
          </div>
        </div>

        <div className="mb-6">
          <h3 className="text-white mb-4 pb-2 border-b border-white/10">Соседние локации</h3>
          <LocationNeighborsEditor
            formData={{ id: (formData.id as number) || 'new' }}
            neighbors={neighbors}
            onAdd={handleNeighborAdd}
            onRemove={handleNeighborRemove}
          />
        </div>

        {locationId !== 'new' && typeof locationId === 'number' && (
          <div className="mb-6">
            <h3 className="text-white mb-4 pb-2 border-b border-white/10">Ноды добычи</h3>
            <GatheringNodesEditor locationId={locationId} />
          </div>
        )}

        {/* FEAT-207: closed faction territory (saved separately from the form) */}
        {locationId !== 'new' && typeof locationId === 'number' && (
          <div className="mb-6">
            <FactionAccessField kind="location" targetId={locationId} />
          </div>
        )}

        <div className="flex gap-4 mt-8">
          <button
            type="button"
            onClick={onCancel}
            className="flex-1 py-3 bg-white/10 text-white border-none rounded cursor-pointer font-medium transition-colors hover:bg-white/20"
          >
            Отмена
          </button>
          <button
            type="submit"
            className="flex-1 py-3 bg-site-blue text-white border-none rounded cursor-pointer font-medium transition-colors hover:bg-[#5d8fa8] disabled:opacity-50 disabled:cursor-not-allowed"
            disabled={isUploading}
          >
            {isUploading ? 'Сохранение...' : 'Сохранить'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default EditLocationForm;
