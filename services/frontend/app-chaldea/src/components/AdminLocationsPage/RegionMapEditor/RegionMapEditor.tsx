import { useState, useRef, useCallback } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useAppDispatch } from '../../../redux/store';
import { updateLocationPosition, updateDistrictPosition } from '../../../redux/actions/worldMapActions';

// --- Types ---

type CreateMode = 'location' | 'zone';

interface MapItemData {
  id: number;
  name: string;
  type: 'location' | 'district';
  map_icon_url: string | null;
  map_x: number | null;
  map_y: number | null;
  marker_type?: string | null;
}

interface DistrictOption {
  id: number;
  name: string;
  map_icon_url?: string | null;
  x?: number | null;
  y?: number | null;
}

interface RegionMapEditorProps {
  regionId: number;
  mapImageUrl: string;
  mapItems: MapItemData[];
  neighborEdges: Array<{ from_id: number; to_id: number }>;
  districts: DistrictOption[];
  onClose: () => void;
}

// --- Helpers ---

const MARKER_COLORS: Record<string, string> = {
  safe: '#4ade80',
  dangerous: '#f87171',
  dungeon: '#a78bfa',
};

const getMarkerColor = (markerType?: string | null): string =>
  MARKER_COLORS[markerType ?? 'safe'] ?? MARKER_COLORS.safe;

// --- Component ---

const MARKER_TYPE_OPTIONS = [
  { value: 'safe', label: 'Безопасная' },
  { value: 'dangerous', label: 'Опасная' },
  { value: 'dungeon', label: 'Подземелье' },
] as const;

interface CreateLocationFormState {
  name: string;
  district_id: string;
  marker_type: string;
  description: string;
}

interface CreateZoneFormState {
  name: string;
  description: string;
}

const INITIAL_LOCATION_FORM: CreateLocationFormState = {
  name: '',
  district_id: '__none__',
  marker_type: 'safe',
  description: '',
};

const INITIAL_ZONE_FORM: CreateZoneFormState = {
  name: '',
  description: '',
};

const RegionMapEditor = ({
  regionId,
  mapImageUrl,
  mapItems,
  neighborEdges,
  districts,
  onClose,
}: RegionMapEditorProps) => {
  const dispatch = useAppDispatch();
  const mapContainerRef = useRef<HTMLDivElement>(null);

  const [saving, setSaving] = useState(false);
  const [draggingOnMap, setDraggingOnMap] = useState<string | null>(null);
  const [dragOffset, setDragOffset] = useState<{ x: number; y: number } | null>(null);
  const [localPositions, setLocalPositions] = useState<
    Record<string, { map_x: number | null; map_y: number | null }>
  >({});

  // --- Create form ---
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [createMode, setCreateMode] = useState<CreateMode>('location');
  const [locationForm, setLocationForm] = useState<CreateLocationFormState>(INITIAL_LOCATION_FORM);
  const [zoneForm, setZoneForm] = useState<CreateZoneFormState>(INITIAL_ZONE_FORM);
  const [creating, setCreating] = useState(false);
  const [createdItems, setCreatedItems] = useState<MapItemData[]>([]);
  const [locationIconFile, setLocationIconFile] = useState<File | null>(null);
  const [locationIconPreview, setLocationIconPreview] = useState<string | null>(null);
  const [zoneIconFile, setZoneIconFile] = useState<File | null>(null);
  const [zoneIconPreview, setZoneIconPreview] = useState<string | null>(null);

  // Build unified items: map_items from backend + locally created
  const allItems: MapItemData[] = [
    ...mapItems,
    ...createdItems,
  ];

  // Deduplicate: created items may overlap with districts from props
  const seen = new Set<string>();
  const dedupedItems = allItems.filter((item) => {
    const key = `${item.type}-${item.id}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });

  // Unique key for map item
  const itemKey = (item: MapItemData) => `${item.type}-${item.id}`;

  // Merge server positions with any in-flight local overrides
  const getPosition = (item: MapItemData): { map_x: number | null; map_y: number | null } => {
    const key = itemKey(item);
    if (localPositions[key]) {
      return localPositions[key];
    }
    return { map_x: item.map_x, map_y: item.map_y };
  };

  const placedItems = dedupedItems.filter((item) => {
    const pos = getPosition(item);
    return pos.map_x != null && pos.map_y != null;
  });

  const unplacedItems = dedupedItems.filter((item) => {
    const pos = getPosition(item);
    return pos.map_x == null || pos.map_y == null;
  });

  // --- Create handlers ---

  const handleLocationFormChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>,
  ) => {
    const { name, value } = e.target;
    setLocationForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleZoneFormChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
  ) => {
    const { name, value } = e.target;
    setZoneForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleLocationIconChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] ?? null;
    setLocationIconFile(file);
    if (file) {
      const url = URL.createObjectURL(file);
      setLocationIconPreview(url);
    } else {
      setLocationIconPreview(null);
    }
  };

  const handleZoneIconChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0] ?? null;
    setZoneIconFile(file);
    if (file) {
      const url = URL.createObjectURL(file);
      setZoneIconPreview(url);
    } else {
      setZoneIconPreview(null);
    }
  };

  const handleCreateLocation = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!locationForm.name.trim()) {
      toast.error('Укажите название локации');
      return;
    }

    const hasDistrict = locationForm.district_id && locationForm.district_id !== '__none__';

    setCreating(true);
    try {
      const payload: Record<string, unknown> = {
        name: locationForm.name.trim(),
        marker_type: locationForm.marker_type,
        description: locationForm.description.trim() || '',
      };
      if (hasDistrict) {
        payload.district_id = parseInt(locationForm.district_id, 10);
      } else {
        payload.region_id = regionId;
      }
      const response = await axios.post('/locations/', payload);
      let iconUrl: string | null = response.data.map_icon_url ?? null;

      // Upload icon if selected
      if (locationIconFile) {
        try {
          const formData = new FormData();
          formData.append('location_id', String(response.data.id));
          formData.append('file', locationIconFile);
          const iconResp = await axios.post('/photo/change_location_icon', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
          });
          iconUrl = iconResp.data?.icon_url ?? iconResp.data?.map_icon_url ?? iconUrl;
        } catch {
          toast.error('Локация создана, но не удалось загрузить иконку');
        }
      }

      const newItem: MapItemData = {
        id: response.data.id,
        name: response.data.name,
        type: 'location',
        map_icon_url: iconUrl,
        map_x: null,
        map_y: null,
        marker_type: response.data.marker_type ?? 'safe',
      };
      setCreatedItems((prev) => [...prev, newItem]);
      setLocationForm(INITIAL_LOCATION_FORM);
      setLocationIconFile(null);
      setLocationIconPreview(null);
      setShowCreateForm(false);
      toast.success('Локация создана — перетащите её на карту');
    } catch {
      toast.error('Не удалось создать локацию');
    } finally {
      setCreating(false);
    }
  };

  const handleCreateZone = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!zoneForm.name.trim()) {
      toast.error('Укажите название зоны');
      return;
    }
    if (!zoneForm.description.trim()) {
      toast.error('Укажите описание зоны');
      return;
    }

    setCreating(true);
    try {
      const payload = {
        name: zoneForm.name.trim(),
        description: zoneForm.description.trim(),
        region_id: regionId,
      };
      const response = await axios.post('/locations/districts', payload);
      let iconUrl: string | null = response.data.map_icon_url ?? null;

      // Upload icon if selected
      if (zoneIconFile) {
        try {
          const formData = new FormData();
          formData.append('district_id', String(response.data.id));
          formData.append('file', zoneIconFile);
          const iconResp = await axios.post('/photo/change_district_icon', formData, {
            headers: { 'Content-Type': 'multipart/form-data' },
          });
          iconUrl = iconResp.data?.icon_url ?? iconResp.data?.map_icon_url ?? iconUrl;
        } catch {
          toast.error('Зона создана, но не удалось загрузить иконку');
        }
      }

      const newItem: MapItemData = {
        id: response.data.id,
        name: response.data.name,
        type: 'district',
        map_icon_url: iconUrl,
        map_x: null,
        map_y: null,
        marker_type: null,
      };
      setCreatedItems((prev) => [...prev, newItem]);
      setZoneForm(INITIAL_ZONE_FORM);
      setZoneIconFile(null);
      setZoneIconPreview(null);
      setShowCreateForm(false);
      toast.success('Зона создана — перетащите её на карту');
    } catch {
      toast.error('Не удалось создать зону');
    } finally {
      setCreating(false);
    }
  };

  // --- Coordinate conversion ---

  const getPercentCoords = useCallback(
    (clientX: number, clientY: number): { x: number; y: number } => {
      if (!mapContainerRef.current) return { x: 0, y: 0 };
      const rect = mapContainerRef.current.getBoundingClientRect();
      const x = ((clientX - rect.left) / rect.width) * 100;
      const y = ((clientY - rect.top) / rect.height) * 100;
      return {
        x: Math.max(0, Math.min(100, x)),
        y: Math.max(0, Math.min(100, y)),
      };
    },
    [],
  );

  // --- Save position to API ---

  const savePosition = async (key: string, map_x: number, map_y: number) => {
    const [type, idStr] = key.split('-');
    const id = Number(idStr);
    setSaving(true);
    try {
      if (type === 'location') {
        await dispatch(updateLocationPosition({ locationId: id, map_x, map_y })).unwrap();
      } else {
        await dispatch(updateDistrictPosition({ districtId: id, x: map_x, y: map_y })).unwrap();
      }
      toast.success('Позиция сохранена');
    } catch {
      toast.error('Не удалось сохранить позицию');
    } finally {
      setSaving(false);
    }
  };

  const removeFromMap = async (key: string) => {
    const [type, idStr] = key.split('-');
    const id = Number(idStr);
    setSaving(true);
    try {
      if (type === 'location') {
        await dispatch(
          updateLocationPosition({ locationId: id, map_x: null, map_y: null }),
        ).unwrap();
      } else {
        await dispatch(
          updateDistrictPosition({ districtId: id, x: null, y: null }),
        ).unwrap();
      }
      // Set local override to null positions (overrides props data)
      setLocalPositions((prev) => ({
        ...prev,
        [key]: { map_x: null, map_y: null },
      }));
      // Also update createdItems to clear position
      setCreatedItems((prev) =>
        prev.map((item) =>
          itemKey(item) === key ? { ...item, map_x: null, map_y: null } : item,
        ),
      );
      toast.success('Элемент убран с карты');
    } catch {
      toast.error('Не удалось убрать элемент с карты');
    } finally {
      setSaving(false);
    }
  };

  // --- HTML5 Drag and Drop: from list to map ---

  const handleDragStart = (e: React.DragEvent, key: string) => {
    e.dataTransfer.setData('text/plain', key);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
  };

  const handleDropOnMap = (e: React.DragEvent) => {
    e.preventDefault();
    const key = e.dataTransfer.getData('text/plain');
    if (!key) return;

    const coords = getPercentCoords(e.clientX, e.clientY);

    // Set local position immediately for responsive UI
    setLocalPositions((prev) => ({
      ...prev,
      [key]: { map_x: coords.x, map_y: coords.y },
    }));

    savePosition(key, coords.x, coords.y);
  };

  // --- Mouse drag for repositioning placed icons ---

  const handleIconMouseDown = (e: React.MouseEvent, key: string) => {
    if (e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();

    const coords = getPercentCoords(e.clientX, e.clientY);
    const item = dedupedItems.find((i) => itemKey(i) === key)!;
    const pos = getPosition(item);

    setDraggingOnMap(key);
    setDragOffset({
      x: coords.x - (pos.map_x ?? 0),
      y: coords.y - (pos.map_y ?? 0),
    });
  };

  const handleMapMouseMove = (e: React.MouseEvent) => {
    if (draggingOnMap == null || !dragOffset) return;

    const coords = getPercentCoords(e.clientX, e.clientY);
    const newX = Math.max(0, Math.min(100, coords.x - dragOffset.x));
    const newY = Math.max(0, Math.min(100, coords.y - dragOffset.y));

    setLocalPositions((prev) => ({
      ...prev,
      [draggingOnMap]: { map_x: newX, map_y: newY },
    }));
  };

  const handleMapMouseUp = () => {
    if (draggingOnMap == null) return;

    const pos = localPositions[draggingOnMap];
    if (pos) {
      savePosition(draggingOnMap, pos.map_x, pos.map_y);
    }

    setDraggingOnMap(null);
    setDragOffset(null);
  };

  // --- Render SVG neighbor lines ---

  const renderNeighborLines = () => {
    const posMap: Record<number, { x: number; y: number }> = {};
    for (const item of placedItems) {
      if (item.type !== 'location') continue;
      const pos = getPosition(item);
      if (pos.map_x != null && pos.map_y != null) {
        posMap[item.id] = { x: pos.map_x, y: pos.map_y };
      }
    }

    return neighborEdges
      .filter((edge) => posMap[edge.from_id] && posMap[edge.to_id])
      .map((edge) => {
        const from = posMap[edge.from_id];
        const to = posMap[edge.to_id];
        return (
          <line
            key={`${edge.from_id}-${edge.to_id}`}
            x1={`${from.x}%`}
            y1={`${from.y}%`}
            x2={`${to.x}%`}
            y2={`${to.y}%`}
            stroke="rgba(255,255,255,0.3)"
            strokeWidth="2"
            strokeDasharray="6 4"
          />
        );
      });
  };

  // --- Item rendering helper ---

  const renderItemIcon = (item: MapItemData, size: 'sm' | 'lg') => {
    const sizeClasses = size === 'sm' ? 'w-6 h-6' : 'w-14 h-14 sm:w-16 sm:h-16 md:w-20 md:h-20';

    if (item.map_icon_url) {
      return (
        <img
          src={item.map_icon_url}
          alt=""
          className={`${sizeClasses} object-contain flex-shrink-0`}
          draggable={false}
        />
      );
    }

    if (item.type === 'district') {
      return (
        <span
          className={`${size === 'sm' ? 'w-4 h-4' : 'w-8 h-8 sm:w-10 sm:h-10 md:w-12 md:h-12'} rounded flex-shrink-0 border border-amber-400/60 bg-amber-600/40`}
        />
      );
    }

    return (
      <span
        className={`${size === 'sm' ? 'w-4 h-4' : 'w-8 h-8 sm:w-10 sm:h-10 md:w-12 md:h-12'} rounded-full flex-shrink-0`}
        style={{ backgroundColor: getMarkerColor(item.marker_type) }}
      />
    );
  };

  // --- Render ---

  return (
    <div className="mt-4 bg-black/30 rounded-lg border border-white/10 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-white/[0.04] border-b border-white/10">
        <h3 className="text-[#a8c6df] font-medium text-sm uppercase tracking-wide">
          Редактор карты региона
        </h3>
        <div className="flex items-center gap-3">
          {saving && (
            <span className="text-xs text-site-blue animate-pulse">Сохранение...</span>
          )}
          <button
            className="px-3 py-1 bg-white/10 text-white border-none rounded cursor-pointer text-xs transition-colors hover:bg-white/20"
            onClick={onClose}
          >
            Закрыть
          </button>
        </div>
      </div>

      {/* Main content: left panel + map */}
      <div className="flex flex-col md:flex-row">
        {/* Left panel — item list */}
        <div className="w-full md:w-[250px] flex-shrink-0 border-b md:border-b-0 md:border-r border-white/10 p-3 overflow-y-auto max-h-[600px]">
          <div className="flex items-center justify-between mb-2">
            <p className="text-xs text-[#8ab3d5] uppercase tracking-wide">
              Элементы
            </p>
            <button
              type="button"
              className="px-2 py-0.5 bg-green-600/20 text-green-400 border-none rounded cursor-pointer text-[10px] transition-colors hover:bg-green-600/30"
              onClick={() => setShowCreateForm((prev) => !prev)}
            >
              {showCreateForm ? 'Отмена' : '+ Создать'}
            </button>
          </div>

          {/* Inline create form */}
          {showCreateForm && (
            <div className="mb-3 p-2 bg-white/[0.06] rounded border border-white/10 flex flex-col gap-2">
              {/* Toggle: Zone / Location */}
              <div className="flex gap-1">
                <button
                  type="button"
                  className={`flex-1 py-1 text-[10px] font-medium rounded transition-colors border-none cursor-pointer ${
                    createMode === 'zone'
                      ? 'bg-amber-600/30 text-amber-300'
                      : 'bg-white/[0.06] text-white/50 hover:bg-white/10'
                  }`}
                  onClick={() => setCreateMode('zone')}
                >
                  Зона
                </button>
                <button
                  type="button"
                  className={`flex-1 py-1 text-[10px] font-medium rounded transition-colors border-none cursor-pointer ${
                    createMode === 'location'
                      ? 'bg-green-600/30 text-green-300'
                      : 'bg-white/[0.06] text-white/50 hover:bg-white/10'
                  }`}
                  onClick={() => setCreateMode('location')}
                >
                  Локация
                </button>
              </div>

              {createMode === 'zone' ? (
                <form onSubmit={handleCreateZone} className="flex flex-col gap-2">
                  <input
                    type="text"
                    name="name"
                    value={zoneForm.name}
                    onChange={handleZoneFormChange}
                    placeholder="Название зоны"
                    required
                    className="w-full px-2 py-1.5 bg-black/30 border border-white/10 rounded text-xs text-[#d4e6f3] placeholder-white/30 focus:border-site-blue/50 focus:outline-none"
                  />
                  <textarea
                    name="description"
                    value={zoneForm.description}
                    onChange={handleZoneFormChange}
                    placeholder="Описание зоны"
                    required
                    rows={2}
                    className="w-full px-2 py-1.5 bg-black/30 border border-white/10 rounded text-xs text-[#d4e6f3] placeholder-white/30 focus:border-site-blue/50 focus:outline-none resize-y"
                  />
                  <div>
                    <label className="text-[10px] text-white/50 block mb-0.5">Иконка (PNG)</label>
                    <input
                      type="file"
                      accept="image/*"
                      onChange={handleZoneIconChange}
                      className="w-full text-[10px] text-white/60 file:mr-2 file:py-0.5 file:px-2 file:rounded file:border-0 file:text-[10px] file:bg-white/10 file:text-white/70 file:cursor-pointer"
                    />
                    {zoneIconPreview && (
                      <img src={zoneIconPreview} alt="Превью" className="mt-1 w-8 h-8 object-contain rounded" />
                    )}
                  </div>
                  <button
                    type="submit"
                    disabled={creating}
                    className="w-full py-1.5 bg-amber-600/30 text-amber-300 border-none rounded cursor-pointer text-xs font-medium transition-colors hover:bg-amber-600/40 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {creating ? 'Создание...' : 'Создать зону'}
                  </button>
                </form>
              ) : (
                <form onSubmit={handleCreateLocation} className="flex flex-col gap-2">
                  <input
                    type="text"
                    name="name"
                    value={locationForm.name}
                    onChange={handleLocationFormChange}
                    placeholder="Название локации"
                    required
                    className="w-full px-2 py-1.5 bg-black/30 border border-white/10 rounded text-xs text-[#d4e6f3] placeholder-white/30 focus:border-site-blue/50 focus:outline-none"
                  />
                  <select
                    name="district_id"
                    value={locationForm.district_id}
                    onChange={handleLocationFormChange}
                    className="w-full px-2 py-1.5 bg-black/30 border border-white/10 rounded text-xs text-[#d4e6f3] focus:border-site-blue/50 focus:outline-none"
                  >
                    <option value="__none__">Без зоны (напрямую в регионе)</option>
                    {[...districts, ...createdItems.filter((i) => i.type === 'district')].reduce<DistrictOption[]>((acc, d) => {
                      if (!acc.some((x) => x.id === d.id)) acc.push({ id: d.id, name: d.name });
                      return acc;
                    }, []).map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name}
                      </option>
                    ))}
                  </select>
                  <select
                    name="marker_type"
                    value={locationForm.marker_type}
                    onChange={handleLocationFormChange}
                    className="w-full px-2 py-1.5 bg-black/30 border border-white/10 rounded text-xs text-[#d4e6f3] focus:border-site-blue/50 focus:outline-none"
                  >
                    {MARKER_TYPE_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                  <textarea
                    name="description"
                    value={locationForm.description}
                    onChange={handleLocationFormChange}
                    placeholder="Описание (необязательно)"
                    rows={2}
                    className="w-full px-2 py-1.5 bg-black/30 border border-white/10 rounded text-xs text-[#d4e6f3] placeholder-white/30 focus:border-site-blue/50 focus:outline-none resize-y"
                  />
                  <div>
                    <label className="text-[10px] text-white/50 block mb-0.5">Иконка (PNG)</label>
                    <input
                      type="file"
                      accept="image/*"
                      onChange={handleLocationIconChange}
                      className="w-full text-[10px] text-white/60 file:mr-2 file:py-0.5 file:px-2 file:rounded file:border-0 file:text-[10px] file:bg-white/10 file:text-white/70 file:cursor-pointer"
                    />
                    {locationIconPreview && (
                      <img src={locationIconPreview} alt="Превью" className="mt-1 w-8 h-8 object-contain rounded" />
                    )}
                  </div>
                  <button
                    type="submit"
                    disabled={creating}
                    className="w-full py-1.5 bg-green-600/30 text-green-300 border-none rounded cursor-pointer text-xs font-medium transition-colors hover:bg-green-600/40 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {creating ? 'Создание...' : 'Создать локацию'}
                  </button>
                </form>
              )}
            </div>
          )}

          {/* Unplaced items */}
          {unplacedItems.length > 0 && (
            <div className="mb-3">
              <p className="text-[10px] text-white/40 uppercase mb-1">
                Не на карте — перетащите на карту
              </p>
              {unplacedItems.map((item) => {
                const key = itemKey(item);
                return (
                  <div
                    key={key}
                    draggable
                    onDragStart={(e) => handleDragStart(e, key)}
                    className="flex items-center gap-2 px-2 py-1.5 mb-1 bg-white/[0.04] rounded cursor-grab hover:bg-white/10 transition-colors text-xs text-[#d4e6f3] select-none"
                  >
                    {renderItemIcon(item, 'sm')}
                    <span className="truncate">{item.name}</span>
                    {item.type === 'district' && (
                      <span className="ml-auto text-[9px] text-amber-400/60 flex-shrink-0">зона</span>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Placed items */}
          {placedItems.length > 0 && (
            <div>
              <p className="text-[10px] text-white/40 uppercase mb-1">
                На карте
              </p>
              {placedItems.map((item) => {
                const key = itemKey(item);
                return (
                  <div
                    key={key}
                    className="flex items-center gap-2 px-2 py-1.5 mb-1 bg-green-600/10 rounded text-xs text-[#d4e6f3]"
                  >
                    <span className="text-green-400 text-[10px] flex-shrink-0">&check;</span>
                    {renderItemIcon(item, 'sm')}
                    <span className="truncate flex-grow">{item.name}</span>
                    {item.type === 'district' && (
                      <span className="text-[9px] text-amber-400/60 flex-shrink-0">зона</span>
                    )}
                    <button
                      className="text-[#ff9999] hover:text-site-red text-[10px] flex-shrink-0 bg-transparent border-none cursor-pointer"
                      onClick={() => removeFromMap(key)}
                      title="Убрать с карты"
                      disabled={saving}
                    >
                      &times;
                    </button>
                  </div>
                );
              })}
            </div>
          )}

          {dedupedItems.length === 0 && (
            <p className="text-xs text-white/30 italic">Нет элементов в регионе</p>
          )}
        </div>

        {/* Right panel — Map */}
        <div className="flex-grow p-3 min-h-[300px]">
          <div
            ref={mapContainerRef}
            className="relative w-full select-none"
            onDragOver={handleDragOver}
            onDrop={handleDropOnMap}
            onMouseMove={handleMapMouseMove}
            onMouseUp={handleMapMouseUp}
            onMouseLeave={handleMapMouseUp}
          >
            {/* Map background image */}
            <img
              src={mapImageUrl}
              alt="Карта региона"
              className="w-full block rounded"
              draggable={false}
            />

            {/* SVG overlay for neighbor lines */}
            <svg
              className="absolute inset-0 w-full h-full pointer-events-none"
              preserveAspectRatio="none"
            >
              {renderNeighborLines()}
            </svg>

            {/* Placed item icons */}
            {placedItems.map((item) => {
              const key = itemKey(item);
              const pos = getPosition(item);
              if (pos.map_x == null || pos.map_y == null) return null;

              const isDragging = draggingOnMap === key;

              return (
                <div
                  key={key}
                  className={`absolute flex flex-col items-center -translate-x-1/2 -translate-y-1/2 group ${
                    isDragging ? 'z-50 opacity-80' : 'z-10'
                  }`}
                  style={{
                    left: `${pos.map_x}%`,
                    top: `${pos.map_y}%`,
                    cursor: isDragging ? 'grabbing' : 'grab',
                  }}
                  onMouseDown={(e) => handleIconMouseDown(e, key)}
                  draggable
                  onDragStart={(e) => handleDragStart(e, key)}
                >
                  {/* Remove button */}
                  <button
                    className="absolute -top-1 -right-1 w-4 h-4 bg-site-red/80 text-white rounded-full text-[8px] leading-none flex items-center justify-center cursor-pointer border-none opacity-0 group-hover:opacity-100 transition-opacity z-20"
                    onClick={(e) => {
                      e.stopPropagation();
                      e.preventDefault();
                      removeFromMap(key);
                    }}
                    onMouseDown={(e) => e.stopPropagation()}
                    title="Убрать с карты"
                    disabled={saving}
                  >
                    &times;
                  </button>

                  {/* Icon or fallback marker */}
                  {renderItemIcon(item, 'lg')}

                  {/* Label */}
                  <span className="mt-1 text-[10px] sm:text-xs text-white bg-black/60 px-1.5 py-0.5 rounded whitespace-nowrap pointer-events-none max-w-[120px] truncate">
                    {item.name}
                  </span>
                </div>
              );
            })}

            {/* Drop zone hint when nothing is placed */}
            {placedItems.length === 0 && (
              <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                <p className="text-white/20 text-sm">
                  Перетащите элемент на карту
                </p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default RegionMapEditor;
