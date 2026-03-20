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
  recommended_level?: number | null;
  district_id?: number | null;
  parent_district_id?: number | null;
  map_image_url?: string | null;
  sort_order?: number;
}

interface DistrictOption {
  id: number;
  name: string;
  parent_district_id?: number | null;
  marker_type?: string | null;
  recommended_level?: number | null;
  map_icon_url?: string | null;
  map_image_url?: string | null;
  x?: number | null;
  y?: number | null;
  sort_order?: number;
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
  farm: '#fb923c',
};

const MARKER_BADGES: Record<string, { icon: string; label: string; color: string }> = {
  safe: { icon: '\u{1F3E0}', label: 'Безопасная', color: 'text-green-400' },
  dangerous: { icon: '\u{2694}\uFE0F', label: 'Опасная', color: 'text-red-400' },
  dungeon: { icon: '\u{1F3F0}', label: 'Подземелье', color: 'text-purple-400' },
  farm: { icon: '\u{1F479}', label: 'Фарм', color: 'text-orange-400' },
};

const renderMarkerBadge = (markerType?: string | null, recommendedLevel?: number | null, size: 'map' | 'list' = 'list') => {
  const badge = MARKER_BADGES[markerType ?? ''];
  if (!badge && !recommendedLevel) return null;
  const icon = badge?.icon ?? '';
  const color = badge?.color ?? 'text-white/50';
  const showLevel = (markerType === 'dangerous' || markerType === 'farm') && recommendedLevel;
  const levelStr = showLevel ? `Ур.${recommendedLevel}` : '';
  const parts = [icon, levelStr].filter(Boolean).join(' ');
  if (!parts) return null;
  if (size === 'map') {
    return (
      <span className={`text-[8px] bg-black/60 px-1 rounded whitespace-nowrap pointer-events-none ${color}`}>
        {parts}
      </span>
    );
  }
  return (
    <span className={`text-[9px] bg-black/30 px-1 rounded whitespace-nowrap ${color}`}>
      {parts}
    </span>
  );
};

const getMarkerColor = (markerType?: string | null): string =>
  MARKER_COLORS[markerType ?? 'safe'] ?? MARKER_COLORS.safe;

// --- Component ---

const MARKER_TYPE_OPTIONS = [
  { value: 'safe', label: 'Безопасная' },
  { value: 'dangerous', label: 'Опасная' },
  { value: 'dungeon', label: 'Подземелье' },
  { value: 'farm', label: 'Фарм' },
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
  parent_district_id: string;
  marker_type: string;
  recommended_level: string;
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
  parent_district_id: '__none__',
  marker_type: 'safe',
  recommended_level: '',
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
  const [expandedZones, setExpandedZones] = useState<Set<number>>(new Set());
  const [localSortOverrides, setLocalSortOverrides] = useState<Record<string, number>>({});

  // --- District map (city map) view ---
  const [viewingDistrictMap, setViewingDistrictMap] = useState<number | null>(null);
  const [districtMapUploading, setDistrictMapUploading] = useState(false);
  // Track locally uploaded map URLs to update UI without re-fetch
  const [localDistrictMapUrls, setLocalDistrictMapUrls] = useState<Record<number, string>>({});

  // Unique key for map item
  const itemKey = (item: MapItemData) => `${item.type}-${item.id}`;

  // --- Inline edit ---
  const [editingItem, setEditingItem] = useState<{ key: string; type: 'location' | 'district'; id: number } | null>(null);
  const [editForm, setEditForm] = useState({ name: '', marker_type: 'safe', recommended_level: '' });
  const [editSaving, setEditSaving] = useState(false);

  const startEdit = (item: MapItemData) => {
    setEditingItem({ key: itemKey(item), type: item.type, id: item.id });
    setEditForm({
      name: item.name,
      marker_type: item.marker_type ?? 'safe',
      recommended_level: item.recommended_level != null ? String(item.recommended_level) : '',
    });
  };

  const cancelEdit = () => {
    setEditingItem(null);
  };

  const saveEdit = async () => {
    if (!editingItem || !editForm.name.trim()) return;
    setEditSaving(true);
    try {
      const payload: Record<string, unknown> = {
        name: editForm.name.trim(),
        marker_type: editForm.marker_type,
      };
      if (editForm.marker_type === 'dangerous' || editForm.marker_type === 'farm') {
        payload.recommended_level = editForm.recommended_level ? parseInt(editForm.recommended_level, 10) : null;
      } else {
        payload.recommended_level = null;
      }

      if (editingItem.type === 'district') {
        await axios.put(`/locations/districts/${editingItem.id}/update`, payload);
      } else {
        await axios.put(`/locations/${editingItem.id}/update`, payload);
      }

      // Update local state
      setCreatedItems((prev) =>
        prev.map((i) =>
          itemKey(i) === editingItem.key
            ? { ...i, name: editForm.name.trim(), marker_type: editForm.marker_type, recommended_level: payload.recommended_level as number | null }
            : i,
        ),
      );
      toast.success('Сохранено');
      setEditingItem(null);
    } catch {
      toast.error('Не удалось сохранить');
    } finally {
      setEditSaving(false);
    }
  };

  // Get sort_order for an item, considering local overrides
  const getSortOrder = useCallback((type: string, id: number): number => {
    const key = `${type}-${id}`;
    if (key in localSortOverrides) return localSortOverrides[key];
    // Find from mapItems or districts props
    if (type === 'district') {
      const d = districts.find((dd) => dd.id === id);
      return d?.sort_order ?? 0;
    }
    const item = mapItems.find((i) => i.type === type && i.id === id);
    return (item as MapItemData)?.sort_order ?? 0;
  }, [localSortOverrides, districts, mapItems]);

  // Save sort order to API
  const saveSortOrder = useCallback(async (items: Array<{ id: number; type: string; sort_order: number }>) => {
    try {
      await axios.put(`/locations/regions/${regionId}/sort-order`, { items });
    } catch {
      toast.error('Не удалось сохранить порядок');
    }
  }, [regionId]);

  // Reorder: move item at `fromIdx` to `toIdx` within a sorted children array, then reassign sequential sort_order
  const handleReorder = useCallback((
    sortedChildren: Array<{ id: number; type: string; name: string }>,
    fromIdx: number,
    toIdx: number,
  ) => {
    const reordered = [...sortedChildren];
    const [moved] = reordered.splice(fromIdx, 1);
    reordered.splice(toIdx, 0, moved);

    const overrides: Record<string, number> = {};
    const apiItems: Array<{ id: number; type: string; sort_order: number }> = [];
    reordered.forEach((item, idx) => {
      overrides[`${item.type}-${item.id}`] = idx;
      apiItems.push({ id: item.id, type: item.type, sort_order: idx });
    });

    setLocalSortOverrides((prev) => ({ ...prev, ...overrides }));
    saveSortOrder(apiItems);
  }, [saveSortOrder]);

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

  // Unplaced items: exclude locations that belong to a zone, all districts (shown in "Зоны" section)
  const unplacedItems = dedupedItems.filter((item) => {
    const pos = getPosition(item);
    if (pos.map_x != null && pos.map_y != null) return false;
    if (item.type === 'location' && item.district_id) return false;
    if (item.type === 'district') return false;
    return true;
  });

  // All districts (from both props and created items) for zone grouping
  const allDistricts = [
    ...districts.map((d) => ({ id: d.id, name: d.name, parent_district_id: d.parent_district_id ?? null })),
    ...createdItems.filter((i) => i.type === 'district').map((d) => ({ id: d.id, name: d.name, parent_district_id: d.parent_district_id ?? null })),
  ].filter((d, i, arr) => arr.findIndex((x) => x.id === d.id) === i);

  // Sub-districts grouped by parent_district_id
  const subDistrictsByParent = allDistricts
    .filter((d) => d.parent_district_id != null)
    .reduce<Record<number, typeof allDistricts>>((acc, d) => {
      const parentId = d.parent_district_id!;
      if (!acc[parentId]) acc[parentId] = [];
      acc[parentId].push(d);
      return acc;
    }, {});

  // Locations grouped by district_id
  const locationsByZone = dedupedItems
    .filter((item) => item.type === 'location' && item.district_id)
    .reduce<Record<number, MapItemData[]>>((acc, item) => {
      const zoneId = item.district_id!;
      if (!acc[zoneId]) acc[zoneId] = [];
      acc[zoneId].push(item);
      return acc;
    }, {});

  // Top-level districts that have child locations or sub-districts (exclude sub-districts from top-level list)
  const topLevelDistricts = allDistricts
    .filter((d) => d.parent_district_id == null)
    .sort((a, b) => getSortOrder('district', a.id) - getSortOrder('district', b.id));

  // Build sorted children (sub-districts + locations mixed) for a given zone
  const getZoneChildren = useCallback((zoneId: number): Array<{ id: number; type: string; name: string }> => {
    const childSubDistricts = (subDistrictsByParent[zoneId] ?? []).map((d) => ({
      id: d.id,
      type: 'district' as const,
      name: d.name,
    }));
    const childLocations = (locationsByZone[zoneId] ?? []).map((l) => ({
      id: l.id,
      type: 'location' as const,
      name: l.name,
    }));
    return [...childSubDistricts, ...childLocations].sort(
      (a, b) => getSortOrder(a.type, a.id) - getSortOrder(b.type, b.id),
    );
  }, [subDistrictsByParent, locationsByZone, getSortOrder]);

  const toggleZone = (zoneId: number) => {
    setExpandedZones((prev) => {
      const next = new Set(prev);
      if (next.has(zoneId)) next.delete(zoneId);
      else next.add(zoneId);
      return next;
    });
  };

  // --- Create handlers ---

  const handleLocationFormChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>,
  ) => {
    const { name, value } = e.target;
    setLocationForm((prev) => ({ ...prev, [name]: value }));
  };

  const handleZoneFormChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>,
  ) => {
    const { name, value } = e.target;
    setZoneForm((prev) => {
      const next = { ...prev, [name]: value };
      // Clear recommended_level when switching to safe/dungeon
      if (name === 'marker_type' && value !== 'dangerous' && value !== 'farm') {
        next.recommended_level = '';
      }
      return next;
    });
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

  const handleDistrictMapUpload = async (districtId: number, file: File) => {
    setDistrictMapUploading(true);
    try {
      const formData = new FormData();
      formData.append('district_id', String(districtId));
      formData.append('file', file);
      const resp = await axios.post('/photo/change_district_map', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      const mapUrl = resp.data?.map_image_url;
      if (mapUrl) {
        setLocalDistrictMapUrls((prev) => ({ ...prev, [districtId]: mapUrl }));
        toast.success('Карта города загружена');
      }
    } catch {
      toast.error('Не удалось загрузить карту города');
    } finally {
      setDistrictMapUploading(false);
    }
  };

  // Get district map_image_url (with local override)
  const getDistrictMapUrl = (districtId: number): string | null => {
    if (localDistrictMapUrls[districtId]) return localDistrictMapUrls[districtId];
    const d = districts.find((dd) => dd.id === districtId);
    return d?.map_image_url ?? null;
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
        district_id: hasDistrict ? parseInt(locationForm.district_id, 10) : null,
      };
      setCreatedItems((prev) => [...prev, newItem]);
      if (hasDistrict) {
        setExpandedZones((prev) => new Set(prev).add(parseInt(locationForm.district_id, 10)));
      }
      setLocationForm(INITIAL_LOCATION_FORM);
      setLocationIconFile(null);
      setLocationIconPreview(null);
      setShowCreateForm(false);
      toast.success(hasDistrict ? 'Локация создана и привязана к зоне' : 'Локация создана — перетащите её на карту');
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

    const hasParentZone = zoneForm.parent_district_id && zoneForm.parent_district_id !== '__none__';

    setCreating(true);
    try {
      const payload: Record<string, unknown> = {
        name: zoneForm.name.trim(),
        description: zoneForm.description.trim(),
        region_id: regionId,
        marker_type: zoneForm.marker_type,
      };
      if (zoneForm.recommended_level) {
        payload.recommended_level = parseInt(zoneForm.recommended_level, 10);
      }
      if (hasParentZone) {
        payload.parent_district_id = parseInt(zoneForm.parent_district_id, 10);
      }
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
        marker_type: response.data.marker_type ?? zoneForm.marker_type,
        recommended_level: response.data.recommended_level ?? (zoneForm.recommended_level ? parseInt(zoneForm.recommended_level, 10) : null),
        parent_district_id: hasParentZone ? parseInt(zoneForm.parent_district_id, 10) : null,
      };
      setCreatedItems((prev) => [...prev, newItem]);
      if (hasParentZone) {
        setExpandedZones((prev) => new Set(prev).add(parseInt(zoneForm.parent_district_id, 10)));
      }
      setZoneForm(INITIAL_ZONE_FORM);
      setZoneIconFile(null);
      setZoneIconPreview(null);
      setShowCreateForm(false);
      toast.success(hasParentZone ? 'Подзона создана — перетащите её на карту' : 'Зона создана — перетащите её на карту');
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
    const sizeClasses = size === 'sm' ? 'w-6 h-6' : 'w-10 h-10';

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
          className={`${size === 'sm' ? 'w-4 h-4' : 'w-10 h-10'} rounded flex-shrink-0 border border-amber-400/60 bg-amber-600/40`}
        />
      );
    }

    return (
      <span
        className={`${size === 'sm' ? 'w-4 h-4' : 'w-10 h-10'} rounded-full flex-shrink-0`}
        style={{ backgroundColor: getMarkerColor(item.marker_type) }}
      />
    );
  };

  // Round icon for city map — shows image in a circle, fallback to colored circle
  const renderCityMapIcon = (item: MapItemData, size: 'sm' | 'lg') => {
    const sizeClasses = size === 'sm' ? 'w-6 h-6' : 'w-10 h-10';
    const imgUrl = item.map_icon_url || (item as MapItemData & { image_url?: string | null }).image_url;

    if (imgUrl) {
      return (
        <div className={`${sizeClasses} rounded-full overflow-hidden flex-shrink-0 border-2 border-white/30`}>
          <img
            src={imgUrl}
            alt=""
            className="w-full h-full object-cover"
            draggable={false}
          />
        </div>
      );
    }

    if (item.type === 'district') {
      return (
        <div className={`${sizeClasses} rounded-full flex-shrink-0 border-2 border-amber-400/60 bg-amber-600/40 flex items-center justify-center`}>
          <span className="text-amber-300/70 text-[8px]">&#9670;</span>
        </div>
      );
    }

    return (
      <div
        className={`${sizeClasses} rounded-full flex-shrink-0 border-2 border-white/30 flex items-center justify-center`}
        style={{ backgroundColor: getMarkerColor(item.marker_type) }}
      >
        <span className="text-white text-[10px]">{MARKER_BADGES[item.marker_type ?? '']?.icon ?? ''}</span>
      </div>
    );
  };

  const renderEditButton = (item: MapItemData) => (
    <button
      type="button"
      className="text-[10px] text-white/30 hover:text-site-blue bg-transparent border-none cursor-pointer flex-shrink-0 p-0 leading-none"
      onClick={(e) => { e.stopPropagation(); startEdit(item); }}
      title="Редактировать"
    >&#9998;</button>
  );

  const renderInlineEditForm = () => {
    if (!editingItem) return null;
    return (
      <div className="mb-2 p-2 bg-white/[0.06] rounded border border-site-blue/30 flex flex-col gap-1.5">
        <div className="flex items-center justify-between">
          <span className="text-[10px] text-site-blue uppercase">Редактирование</span>
          <button
            type="button"
            className="text-white/40 hover:text-white text-xs bg-transparent border-none cursor-pointer"
            onClick={cancelEdit}
          >&times;</button>
        </div>
        <input
          type="text"
          value={editForm.name}
          onChange={(e) => setEditForm((f) => ({ ...f, name: e.target.value }))}
          placeholder="Название"
          className="w-full px-2 py-1 bg-black/30 border border-white/10 rounded text-xs text-[#d4e6f3] focus:border-site-blue/50 focus:outline-none"
        />
        <select
          value={editForm.marker_type}
          onChange={(e) => {
            const val = e.target.value;
            setEditForm((f) => ({
              ...f,
              marker_type: val,
              recommended_level: val !== 'dangerous' && val !== 'farm' ? '' : f.recommended_level,
            }));
          }}
          className="w-full px-2 py-1 bg-black/30 border border-white/10 rounded text-xs text-[#d4e6f3] focus:border-site-blue/50 focus:outline-none"
        >
          {MARKER_TYPE_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        {(editForm.marker_type === 'dangerous' || editForm.marker_type === 'farm') && (
          <input
            type="number"
            value={editForm.recommended_level}
            onChange={(e) => setEditForm((f) => ({ ...f, recommended_level: e.target.value }))}
            placeholder="Рек. уровень"
            min={1}
            className="w-full px-2 py-1 bg-black/30 border border-white/10 rounded text-xs text-[#d4e6f3] placeholder-white/30 focus:border-site-blue/50 focus:outline-none"
          />
        )}
        <button
          type="button"
          disabled={editSaving || !editForm.name.trim()}
          className="w-full py-1 bg-site-blue/30 text-site-blue border-none rounded cursor-pointer text-[10px] font-medium transition-colors hover:bg-site-blue/40 disabled:opacity-50 disabled:cursor-not-allowed"
          onClick={saveEdit}
        >
          {editSaving ? 'Сохранение...' : 'Сохранить'}
        </button>
      </div>
    );
  };

  // --- District map (city) view data ---
  const viewingDistrictData = viewingDistrictMap != null
    ? districts.find((d) => d.id === viewingDistrictMap) ?? null
    : null;

  const viewingDistrictMapUrl = viewingDistrictMap != null
    ? getDistrictMapUrl(viewingDistrictMap)
    : null;

  const viewingDistrictMapItems: MapItemData[] = viewingDistrictMap != null
    ? dedupedItems.filter(
        (item) =>
          (item.type === 'location' && item.district_id === viewingDistrictMap) ||
          (item.type === 'district' && item.parent_district_id === viewingDistrictMap),
      )
    : [];

  // If viewing a district map, render a nested editor for that district
  if (viewingDistrictMap != null && viewingDistrictData && viewingDistrictMapUrl) {
    return (
      <div className="mt-4 bg-black/30 rounded-lg border border-white/10 overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 bg-white/[0.04] border-b border-white/10">
          <div className="flex items-center gap-3">
            <button
              className="px-2 py-1 bg-white/10 text-white border-none rounded cursor-pointer text-xs transition-colors hover:bg-white/20"
              onClick={() => setViewingDistrictMap(null)}
            >
              &#9664; Назад к региону
            </button>
            <h3 className="text-[#a8c6df] font-medium text-sm uppercase tracking-wide">
              Карта: {viewingDistrictData.name}
            </h3>
          </div>
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

        {/* District map content: left panel + map */}
        <div className="flex flex-col md:flex-row">
          {/* Left panel — items belonging to this district */}
          <div className="w-full md:w-[250px] flex-shrink-0 border-b md:border-b-0 md:border-r border-white/10 p-3 overflow-y-auto max-h-[600px]">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs text-[#8ab3d5] uppercase tracking-wide">
                Элементы города
              </p>
              <button
                type="button"
                className="px-2 py-0.5 bg-green-600/20 text-green-400 border-none rounded cursor-pointer text-[10px] transition-colors hover:bg-green-600/30"
                onClick={() => {
                  setShowCreateForm((prev) => !prev);
                  // Default to current district for both location and zone forms
                  setLocationForm((f) => ({ ...f, district_id: String(viewingDistrictMap) }));
                  setZoneForm((f) => ({ ...f, parent_district_id: String(viewingDistrictMap) }));
                }}
              >
                {showCreateForm ? 'Отмена' : '+ Создать'}
              </button>
            </div>

            {/* Inline create form for city map */}
            {showCreateForm && (
              <div className="mb-3 p-2 bg-white/[0.06] rounded border border-white/10 flex flex-col gap-2">
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
                    Подзона
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
                      placeholder="Название подзоны"
                      required
                      className="w-full px-2 py-1.5 bg-black/30 border border-white/10 rounded text-xs text-[#d4e6f3] placeholder-white/30 focus:border-site-blue/50 focus:outline-none"
                    />
                    <select
                      name="parent_district_id"
                      value={zoneForm.parent_district_id}
                      onChange={handleZoneFormChange}
                      className="w-full px-2 py-1.5 bg-black/30 border border-white/10 rounded text-xs text-[#d4e6f3] focus:border-site-blue/50 focus:outline-none"
                    >
                      <option value={String(viewingDistrictMap)}>Напрямую в городе</option>
                      {/* Existing sub-zones of this city as parent options */}
                      {[...districts.filter((d) => d.parent_district_id === viewingDistrictMap), ...createdItems.filter((i) => i.type === 'district' && i.parent_district_id === viewingDistrictMap)]
                        .reduce<{ id: number; name: string }[]>((acc, d) => {
                          if (!acc.some((x) => x.id === d.id)) acc.push({ id: d.id, name: d.name });
                          return acc;
                        }, [])
                        .map((d) => (
                          <option key={d.id} value={d.id}>↳ {d.name}</option>
                        ))}
                    </select>
                    <textarea
                      name="description"
                      value={zoneForm.description}
                      onChange={handleZoneFormChange}
                      placeholder="Описание"
                      required
                      rows={2}
                      className="w-full px-2 py-1.5 bg-black/30 border border-white/10 rounded text-xs text-[#d4e6f3] placeholder-white/30 focus:border-site-blue/50 focus:outline-none resize-y"
                    />
                    <div>
                      <label className="text-[10px] text-white/50 block mb-0.5">Иконка (PNG/JPG)</label>
                      <input
                        type="file"
                        accept="image/*"
                        onChange={handleZoneIconChange}
                        className="w-full text-[10px] text-white/60 file:mr-2 file:py-0.5 file:px-2 file:rounded file:border-0 file:text-[10px] file:bg-white/10 file:text-white/70 file:cursor-pointer"
                      />
                      {zoneIconPreview && (
                        <img src={zoneIconPreview} alt="Превью" className="mt-1 w-8 h-8 rounded-full object-cover border border-white/20" />
                      )}
                    </div>
                    <button
                      type="submit"
                      disabled={creating}
                      className="w-full py-1.5 bg-amber-600/30 text-amber-300 border-none rounded cursor-pointer text-xs font-medium transition-colors hover:bg-amber-600/40 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {creating ? 'Создание...' : 'Создать подзону'}
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
                      <option value={String(viewingDistrictMap)}>Напрямую в городе</option>
                      {/* Sub-districts of the current city */}
                      {[...districts.filter((d) => d.parent_district_id === viewingDistrictMap), ...createdItems.filter((i) => i.type === 'district' && i.parent_district_id === viewingDistrictMap)]
                        .reduce<{ id: number; name: string }[]>((acc, d) => {
                          if (!acc.some((x) => x.id === d.id)) acc.push({ id: d.id, name: d.name });
                          return acc;
                        }, [])
                        .map((d) => (
                          <option key={d.id} value={d.id}>{d.name}</option>
                        ))}
                    </select>
                    <select
                      name="marker_type"
                      value={locationForm.marker_type}
                      onChange={handleLocationFormChange}
                      className="w-full px-2 py-1.5 bg-black/30 border border-white/10 rounded text-xs text-[#d4e6f3] focus:border-site-blue/50 focus:outline-none"
                    >
                      {MARKER_TYPE_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>{opt.label}</option>
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
                      <label className="text-[10px] text-white/50 block mb-0.5">Иконка (PNG/JPG)</label>
                      <input
                        type="file"
                        accept="image/*"
                        onChange={handleLocationIconChange}
                        className="w-full text-[10px] text-white/60 file:mr-2 file:py-0.5 file:px-2 file:rounded file:border-0 file:text-[10px] file:bg-white/10 file:text-white/70 file:cursor-pointer"
                      />
                      {locationIconPreview && (
                        <img src={locationIconPreview} alt="Превью" className="mt-1 w-8 h-8 rounded-full object-cover border border-white/20" />
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

            {/* Inline edit form */}
            {renderInlineEditForm()}

            {(() => {
              // Split city map items into structured sections (like region map)
              // Include nested sub-zones: all districts in dedupedItems whose ancestor chain leads to viewingDistrictMap
              const allCityDistricts: MapItemData[] = [];
              const collectSubDistricts = (parentId: number) => {
                for (const item of dedupedItems) {
                  if (item.type === 'district' && item.parent_district_id === parentId && !allCityDistricts.some((d) => d.id === item.id)) {
                    allCityDistricts.push(item);
                    collectSubDistricts(item.id);
                  }
                }
              };
              collectSubDistricts(viewingDistrictMap!);

              const citySubZones = allCityDistricts.filter((d) => d.parent_district_id === viewingDistrictMap);
              const citySubZoneIds = new Set(allCityDistricts.map((z) => z.id));

              // Nested sub-zones grouped by parent
              const nestedSubZonesByParent: Record<number, MapItemData[]> = {};
              for (const d of allCityDistricts) {
                if (d.parent_district_id && d.parent_district_id !== viewingDistrictMap) {
                  if (!nestedSubZonesByParent[d.parent_district_id]) nestedSubZonesByParent[d.parent_district_id] = [];
                  nestedSubZonesByParent[d.parent_district_id].push(d);
                }
              }

              const cityLocationsBySubZone: Record<number, MapItemData[]> = {};
              const cityFreeLocations: MapItemData[] = [];

              // Collect ALL locations in the city's district tree
              for (const item of dedupedItems) {
                if (item.type !== 'location') continue;
                if (item.district_id && citySubZoneIds.has(item.district_id)) {
                  if (!cityLocationsBySubZone[item.district_id]) cityLocationsBySubZone[item.district_id] = [];
                  cityLocationsBySubZone[item.district_id].push(item);
                } else if (item.district_id === viewingDistrictMap) {
                  cityFreeLocations.push(item);
                }
              }

              // Unplaced free locations (not in sub-zone, no coordinates)
              const cityUnplaced = cityFreeLocations.filter((i) => {
                const pos = getPosition(i);
                return pos.map_x == null || pos.map_y == null;
              });

              // Placed items (all types with coordinates, excluding sub-zone children)
              const cityPlaced = [...cityFreeLocations, ...citySubZones].filter((i) => {
                const pos = getPosition(i);
                return pos.map_x != null && pos.map_y != null;
              });

              const hasContent = viewingDistrictMapItems.length > 0;

              return (
                <>
                  {!hasContent && !showCreateForm && (
                    <p className="text-xs text-white/30 italic">
                      Нет элементов — нажмите "+ Создать"
                    </p>
                  )}

                  {/* Unplaced free locations */}
                  {cityUnplaced.length > 0 && (
                    <div className="mb-3">
                      <p className="text-[10px] text-white/40 uppercase mb-1">Не на карте</p>
                      {cityUnplaced.map((item) => {
                        const key = itemKey(item);
                        return (
                          <div
                            key={key}
                            draggable
                            onDragStart={(e) => handleDragStart(e, key)}
                            className="flex items-center gap-2 px-2 py-1.5 mb-1 bg-white/[0.04] rounded cursor-grab hover:bg-white/10 transition-colors text-xs text-[#d4e6f3] select-none"
                          >
                            {renderCityMapIcon(item, 'sm')}
                            <span className="truncate">{item.name}</span>
                            {renderMarkerBadge(item.marker_type, item.recommended_level)}
                            {renderEditButton(item)}
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* Sub-zones (expandable) */}
                  {citySubZones.length > 0 && (
                    <div className="mb-3">
                      <p className="text-[10px] text-white/40 uppercase mb-1">Подзоны</p>
                      {citySubZones.map((subZone) => {
                        const isExpanded = expandedZones.has(subZone.id);
                        const childLocs = cityLocationsBySubZone[subZone.id] ?? [];
                        const subPos = getPosition(subZone);
                        const subIsPlaced = subPos.map_x != null && subPos.map_y != null;
                        return (
                          <div key={`city-subzone-${subZone.id}`} className="mb-1">
                            <div className="flex items-center gap-0.5">
                              <button
                                type="button"
                                className="w-full flex items-center gap-2 px-2 py-1.5 bg-amber-600/10 rounded text-xs text-amber-300/90 hover:bg-amber-600/20 transition-colors border-none cursor-pointer text-left"
                                onClick={() => toggleZone(subZone.id)}
                              >
                                <span className="text-[10px] flex-shrink-0 transition-transform" style={{ transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)' }}>&#9654;</span>
                                {subIsPlaced && <span className="text-green-400 text-[10px] flex-shrink-0">&#10003;</span>}
                                {renderCityMapIcon(subZone, 'sm')}
                                <span className="truncate">{subZone.name}</span>
                                {renderMarkerBadge(subZone.marker_type, subZone.recommended_level)}
                                <span className="ml-auto text-[9px] text-amber-400/40 flex-shrink-0">{childLocs.length || ''}</span>
                              </button>
                              {renderEditButton(subZone)}
                            </div>
                            {isExpanded && (() => {
                              const sortedItems = getZoneChildren(subZone.id);
                              if (sortedItems.length === 0) return <div className="ml-4 mt-0.5"><p className="text-[10px] text-white/20 italic py-1 px-2">Пусто</p></div>;
                              return (
                                <div className="ml-4 mt-0.5">
                                  {sortedItems.map((child, idx) => {
                                    if (child.type === 'district') {
                                      const nestedZone = dedupedItems.find((i) => i.type === 'district' && i.id === child.id);
                                      if (!nestedZone) return null;
                                      const nExpanded = expandedZones.has(nestedZone.id);
                                      const nPos = getPosition(nestedZone);
                                      const nPlaced = nPos.map_x != null && nPos.map_y != null;
                                      const nChildCount = (cityLocationsBySubZone[nestedZone.id]?.length ?? 0) + (nestedSubZonesByParent[nestedZone.id]?.length ?? 0);
                                      return (
                                        <div key={`nested-zone-${nestedZone.id}`} className="mb-0.5">
                                          <div className="flex items-center gap-0.5">
                                            <div className="flex flex-col flex-shrink-0">
                                              <button type="button" disabled={idx === 0} className="text-[10px] text-white/40 hover:text-white/70 bg-transparent border-none cursor-pointer disabled:opacity-20 disabled:cursor-default leading-none p-0" onClick={() => handleReorder(sortedItems, idx, idx - 1)} title="Вверх">&#9650;</button>
                                              <button type="button" disabled={idx === sortedItems.length - 1} className="text-[10px] text-white/40 hover:text-white/70 bg-transparent border-none cursor-pointer disabled:opacity-20 disabled:cursor-default leading-none p-0" onClick={() => handleReorder(sortedItems, idx, idx + 1)} title="Вниз">&#9660;</button>
                                            </div>
                                            <button
                                              type="button"
                                              className="flex-1 flex items-center gap-2 px-2 py-1 bg-amber-600/5 rounded text-[11px] text-amber-300/70 hover:bg-amber-600/15 transition-colors border-none cursor-pointer text-left"
                                              onClick={() => toggleZone(nestedZone.id)}
                                            >
                                              <span className="text-[9px] flex-shrink-0 transition-transform" style={{ transform: nExpanded ? 'rotate(90deg)' : 'rotate(0deg)' }}>&#9654;</span>
                                              {nPlaced && <span className="text-green-400 text-[10px] flex-shrink-0">&#10003;</span>}
                                              {renderCityMapIcon(nestedZone, 'sm')}
                                              <span className="truncate">{nestedZone.name}</span>
                                              <span className="ml-auto text-[9px] text-amber-400/40 flex-shrink-0">{nChildCount || ''}</span>
                                            </button>
                                            {renderEditButton(nestedZone)}
                                          </div>
                                          {nExpanded && (() => {
                                            const nestedSorted = getZoneChildren(nestedZone.id);
                                            if (nestedSorted.length === 0) return <div className="ml-4 mt-0.5"><p className="text-[10px] text-white/20 italic py-1 px-2">Пусто</p></div>;
                                            return (
                                              <div className="ml-4 mt-0.5">
                                                {nestedSorted.map((nChild, nIdx) => {
                                                  const nLoc = dedupedItems.find((i) => i.type === nChild.type && i.id === nChild.id);
                                                  if (!nLoc) return null;
                                                  const lp = getPosition(nLoc);
                                                  const lPlaced = lp.map_x != null && lp.map_y != null;
                                                  return (
                                                    <div key={itemKey(nLoc)} className={`flex items-center gap-0.5 mb-0.5 rounded text-[11px] text-[#d4e6f3] ${lPlaced ? 'bg-green-600/10' : 'bg-white/[0.03]'}`}>
                                                      <div className="flex flex-col flex-shrink-0">
                                                        <button type="button" disabled={nIdx === 0} className="text-[10px] text-white/40 hover:text-white/70 bg-transparent border-none cursor-pointer disabled:opacity-20 disabled:cursor-default leading-none p-0" onClick={() => handleReorder(nestedSorted, nIdx, nIdx - 1)} title="Вверх">&#9650;</button>
                                                        <button type="button" disabled={nIdx === nestedSorted.length - 1} className="text-[10px] text-white/40 hover:text-white/70 bg-transparent border-none cursor-pointer disabled:opacity-20 disabled:cursor-default leading-none p-0" onClick={() => handleReorder(nestedSorted, nIdx, nIdx + 1)} title="Вниз">&#9660;</button>
                                                      </div>
                                                      <div className="flex items-center gap-2 px-2 py-1 flex-1 min-w-0">
                                                        {lPlaced && <span className="text-green-400 text-[10px] flex-shrink-0">&#10003;</span>}
                                                        {renderCityMapIcon(nLoc, 'sm')}
                                                        <span className="truncate">{nLoc.name}</span>
                                                        {renderMarkerBadge(nLoc.marker_type, nLoc.recommended_level)}
                                                        <span className="ml-auto flex-shrink-0">{renderEditButton(nLoc)}</span>
                                                      </div>
                                                    </div>
                                                  );
                                                })}
                                              </div>
                                            );
                                          })()}
                                        </div>
                                      );
                                    }
                                    // Location child
                                    const loc = dedupedItems.find((i) => i.type === 'location' && i.id === child.id);
                                    if (!loc) return null;
                                    const locPos = getPosition(loc);
                                    const locPlaced = locPos.map_x != null && locPos.map_y != null;
                                    return (
                                      <div key={itemKey(loc)} className={`flex items-center gap-0.5 mb-0.5 rounded text-[11px] text-[#d4e6f3] ${locPlaced ? 'bg-green-600/10' : 'bg-white/[0.03]'}`}>
                                        <div className="flex flex-col flex-shrink-0">
                                          <button type="button" disabled={idx === 0} className="text-[10px] text-white/40 hover:text-white/70 bg-transparent border-none cursor-pointer disabled:opacity-20 disabled:cursor-default leading-none p-0" onClick={() => handleReorder(sortedItems, idx, idx - 1)} title="Вверх">&#9650;</button>
                                          <button type="button" disabled={idx === sortedItems.length - 1} className="text-[10px] text-white/40 hover:text-white/70 bg-transparent border-none cursor-pointer disabled:opacity-20 disabled:cursor-default leading-none p-0" onClick={() => handleReorder(sortedItems, idx, idx + 1)} title="Вниз">&#9660;</button>
                                        </div>
                                        <div className="flex items-center gap-2 px-2 py-1 flex-1 min-w-0">
                                          {locPlaced && <span className="text-green-400 text-[10px] flex-shrink-0">&#10003;</span>}
                                          {renderCityMapIcon(loc, 'sm')}
                                          <span className="truncate">{loc.name}</span>
                                          {renderMarkerBadge(loc.marker_type, loc.recommended_level)}
                                          <span className="ml-auto flex-shrink-0">{renderEditButton(loc)}</span>
                                        </div>
                                      </div>
                                    );
                                  })}
                                </div>
                              );
                            })()}
                          </div>
                        );
                      })}
                    </div>
                  )}

                  {/* Placed items */}
                  {cityPlaced.length > 0 && (
                    <div className="mb-3">
                      <p className="text-[10px] text-white/40 uppercase mb-1">На карте</p>
                      {cityPlaced.map((item) => {
                        const key = itemKey(item);
                        return (
                          <div
                            key={key}
                            className="flex items-center gap-2 px-2 py-1.5 mb-1 bg-green-600/10 rounded text-xs text-[#d4e6f3]"
                          >
                            <span className="text-green-400 text-[10px] flex-shrink-0">&#10003;</span>
                            {renderCityMapIcon(item, 'sm')}
                            <span className="truncate flex-grow">{item.name}</span>
                            {renderMarkerBadge(item.marker_type, item.recommended_level)}
                            {item.type === 'district' && (
                              <span className="text-[9px] text-amber-400/60 flex-shrink-0">подзона</span>
                            )}
                            {renderEditButton(item)}
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
                </>
              );
            })()}
          </div>

          {/* Right panel — District Map */}
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
              <img
                src={viewingDistrictMapUrl}
                alt="Карта города"
                className="w-full block rounded"
                draggable={false}
              />

              {/* Placed item icons */}
              {viewingDistrictMapItems
                .filter((item) => {
                  const pos = getPosition(item);
                  return pos.map_x != null && pos.map_y != null;
                })
                .map((item) => {
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
                      <div className="relative">
                        {renderCityMapIcon(item, 'lg')}
                        {renderMarkerBadge(item.marker_type, item.recommended_level, 'map') && (
                          <div className="absolute -top-2.5 left-1/2 pointer-events-none">
                            {renderMarkerBadge(item.marker_type, item.recommended_level, 'map')}
                          </div>
                        )}
                      </div>
                      <span className="mt-1 text-[10px] sm:text-xs text-white bg-black/60 px-1.5 py-0.5 rounded whitespace-nowrap pointer-events-none max-w-[120px] truncate">
                        {item.name}
                      </span>
                    </div>
                  );
                })}

              {viewingDistrictMapItems.filter((item) => {
                const pos = getPosition(item);
                return pos.map_x != null && pos.map_y != null;
              }).length === 0 && (
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                  <p className="text-white/20 text-sm">
                    Перетащите элемент на карту города
                  </p>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    );
  }

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
                  <select
                    name="parent_district_id"
                    value={zoneForm.parent_district_id}
                    onChange={handleZoneFormChange}
                    className="w-full px-2 py-1.5 bg-black/30 border border-white/10 rounded text-xs text-[#d4e6f3] focus:border-site-blue/50 focus:outline-none"
                  >
                    <option value="__none__">Без родительской зоны (в регион)</option>
                    {[...districts, ...createdItems.filter((i) => i.type === 'district')].reduce<DistrictOption[]>((acc, d) => {
                      if (!acc.some((x) => x.id === d.id)) acc.push({ id: d.id, name: d.name });
                      return acc;
                    }, []).map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.name}
                      </option>
                    ))}
                  </select>
                  <textarea
                    name="description"
                    value={zoneForm.description}
                    onChange={handleZoneFormChange}
                    placeholder="Описание зоны"
                    required
                    rows={2}
                    className="w-full px-2 py-1.5 bg-black/30 border border-white/10 rounded text-xs text-[#d4e6f3] placeholder-white/30 focus:border-site-blue/50 focus:outline-none resize-y"
                  />
                  <select
                    name="marker_type"
                    value={zoneForm.marker_type}
                    onChange={handleZoneFormChange}
                    className="w-full px-2 py-1.5 bg-black/30 border border-white/10 rounded text-xs text-[#d4e6f3] focus:border-site-blue/50 focus:outline-none"
                  >
                    {MARKER_TYPE_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                  {(zoneForm.marker_type === 'dangerous' || zoneForm.marker_type === 'farm') && (
                    <input
                      type="number"
                      name="recommended_level"
                      value={zoneForm.recommended_level}
                      onChange={handleZoneFormChange}
                      placeholder="Рек. уровень"
                      min={1}
                      className="w-full px-2 py-1.5 bg-black/30 border border-white/10 rounded text-xs text-[#d4e6f3] placeholder-white/30 focus:border-site-blue/50 focus:outline-none"
                    />
                  )}
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

          {/* Inline edit form */}
          {renderInlineEditForm()}

          {/* Unplaced items (only free locations + unplaced zones, NOT zone-linked locations) */}
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
                    {renderMarkerBadge(item.marker_type, item.recommended_level)}
                    {item.type === 'district' && (
                      <span className="text-[9px] text-amber-400/60 flex-shrink-0">зона</span>
                    )}
                    <span className="ml-auto flex-shrink-0">{renderEditButton(item)}</span>
                  </div>
                );
              })}
            </div>
          )}

          {/* Zones with their child locations and sub-zones */}
          {topLevelDistricts.length > 0 && (
            <div className="mb-3">
              <p className="text-[10px] text-white/40 uppercase mb-1">
                Зоны
              </p>
              {topLevelDistricts.map((zone) => {
                const isExpanded = expandedZones.has(zone.id);
                const childLocations = locationsByZone[zone.id] ?? [];
                const childSubDistricts = subDistrictsByParent[zone.id] ?? [];
                const childCount = childLocations.length + childSubDistricts.length;
                const zoneMapUrl = getDistrictMapUrl(zone.id);
                return (
                  <div key={`zone-group-${zone.id}`} className="mb-1">
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        className="flex-1 flex items-center gap-2 px-2 py-1.5 bg-amber-600/10 rounded text-xs text-amber-300/90 hover:bg-amber-600/20 transition-colors border-none cursor-pointer text-left min-w-0"
                        onClick={() => toggleZone(zone.id)}
                      >
                        <span className="text-[10px] flex-shrink-0 transition-transform" style={{ transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)' }}>
                          &#9654;
                        </span>
                        <span className="truncate">{zone.name}</span>
                        {zoneMapUrl && (
                          <span className="text-[9px] text-amber-400/70 flex-shrink-0" title="Есть карта города">&#128506;</span>
                        )}
                        <span className="ml-auto text-[9px] text-amber-400/40 flex-shrink-0">{childCount}</span>
                      </button>
                      {/* City map button */}
                      {zoneMapUrl && (
                        <button
                          type="button"
                          className="px-1.5 py-1 bg-amber-600/20 text-amber-300/80 border-none rounded cursor-pointer text-[9px] transition-colors hover:bg-amber-600/30 flex-shrink-0"
                          onClick={() => setViewingDistrictMap(zone.id)}
                          title="Открыть карту города"
                        >
                          &#128506;
                        </button>
                      )}
                    </div>
                    {/* Upload district map (city map) — shown when zone is expanded */}
                    {isExpanded && (
                      <div className="ml-4 mt-1 mb-1">
                        <label className="text-[9px] text-white/40 block mb-0.5">
                          Карта города (PNG/JPG)
                        </label>
                        <div className="flex items-center gap-2">
                          <input
                            type="file"
                            accept="image/*"
                            onChange={(e) => {
                              const file = e.target.files?.[0];
                              if (file) handleDistrictMapUpload(zone.id, file);
                              e.target.value = '';
                            }}
                            disabled={districtMapUploading}
                            className="w-full text-[9px] text-white/50 file:mr-1 file:py-0.5 file:px-2 file:rounded file:border-0 file:text-[9px] file:bg-white/10 file:text-white/60 file:cursor-pointer"
                          />
                          {districtMapUploading && (
                            <span className="text-[9px] text-site-blue animate-pulse flex-shrink-0">Загрузка...</span>
                          )}
                        </div>
                        {zoneMapUrl && (
                          <div className="flex items-center gap-2 mt-1">
                            <img src={zoneMapUrl} alt="Превью карты" className="w-12 h-8 object-cover rounded border border-white/10" />
                            <button
                              type="button"
                              className="text-[9px] text-amber-300/70 hover:text-amber-300 bg-transparent border-none cursor-pointer underline"
                              onClick={() => setViewingDistrictMap(zone.id)}
                            >
                              Редактировать карту
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                    {isExpanded && (() => {
                      const sortedChildren = getZoneChildren(zone.id);
                      return (
                        <div className="ml-4 mt-0.5">
                          {sortedChildren.map((child, idx) => {
                            if (child.type === 'district') {
                              const subZone = child;
                              const subZoneItem = dedupedItems.find((i) => i.type === 'district' && i.id === subZone.id);
                              const subPos = subZoneItem ? getPosition(subZoneItem) : { map_x: null, map_y: null };
                              const subIsPlaced = subPos.map_x != null && subPos.map_y != null;
                              const subChildLocations = locationsByZone[subZone.id] ?? [];
                              const subIsExpanded = expandedZones.has(subZone.id);
                              return (
                                <div key={`sub-zone-${subZone.id}`} className="mb-0.5">
                                  <div className="flex items-center gap-0.5">
                                    <div className="flex flex-col flex-shrink-0">
                                      <button
                                        type="button"
                                        disabled={idx === 0}
                                        className="text-[10px] text-white/40 hover:text-white/70 bg-transparent border-none cursor-pointer disabled:opacity-20 disabled:cursor-default leading-none p-0"
                                        onClick={() => handleReorder(sortedChildren, idx, idx - 1)}
                                        title="Вверх"
                                      >&#9650;</button>
                                      <button
                                        type="button"
                                        disabled={idx === sortedChildren.length - 1}
                                        className="text-[10px] text-white/40 hover:text-white/70 bg-transparent border-none cursor-pointer disabled:opacity-20 disabled:cursor-default leading-none p-0"
                                        onClick={() => handleReorder(sortedChildren, idx, idx + 1)}
                                        title="Вниз"
                                      >&#9660;</button>
                                    </div>
                                    <button
                                      type="button"
                                      className={`flex-1 flex items-center gap-2 px-2 py-1 rounded text-[11px] hover:bg-amber-600/15 transition-colors border-none cursor-pointer text-left ${
                                        subIsPlaced ? 'bg-green-600/10 text-amber-300/80' : 'bg-amber-600/5 text-amber-300/70'
                                      }`}
                                      onClick={() => toggleZone(subZone.id)}
                                    >
                                      {subChildLocations.length > 0 && (
                                        <span className="text-[9px] flex-shrink-0 transition-transform" style={{ transform: subIsExpanded ? 'rotate(90deg)' : 'rotate(0deg)' }}>
                                          &#9654;
                                        </span>
                                      )}
                                      {subIsPlaced && <span className="text-green-400 text-[10px] flex-shrink-0">&#10003;</span>}
                                      <span className="truncate">{subZone.name}</span>
                                      <span className="ml-auto text-[9px] text-amber-400/40 flex-shrink-0">
                                        {subChildLocations.length > 0 ? subChildLocations.length : ''}
                                      </span>
                                    </button>
                                    {subZoneItem && renderEditButton(subZoneItem)}
                                  </div>
                                  {subIsExpanded && subChildLocations.length > 0 && (() => {
                                    const subSorted = getZoneChildren(subZone.id);
                                    return (
                                      <div className="ml-4 mt-0.5">
                                        {subSorted.map((subChild, subIdx) => {
                                          const loc = dedupedItems.find((i) => i.type === subChild.type && i.id === subChild.id);
                                          if (!loc) return null;
                                          const pos = getPosition(loc);
                                          const isPlaced = pos.map_x != null && pos.map_y != null;
                                          return (
                                            <div
                                              key={itemKey(loc)}
                                              className={`flex items-center gap-0.5 mb-0.5 rounded text-[11px] text-[#d4e6f3] ${
                                                isPlaced ? 'bg-green-600/10' : 'bg-white/[0.03]'
                                              }`}
                                            >
                                              <div className="flex flex-col flex-shrink-0">
                                                <button
                                                  type="button"
                                                  disabled={subIdx === 0}
                                                  className="text-[10px] text-white/40 hover:text-white/70 bg-transparent border-none cursor-pointer disabled:opacity-20 disabled:cursor-default leading-none p-0"
                                                  onClick={() => handleReorder(subSorted, subIdx, subIdx - 1)}
                                                  title="Вверх"
                                                >&#9650;</button>
                                                <button
                                                  type="button"
                                                  disabled={subIdx === subSorted.length - 1}
                                                  className="text-[10px] text-white/40 hover:text-white/70 bg-transparent border-none cursor-pointer disabled:opacity-20 disabled:cursor-default leading-none p-0"
                                                  onClick={() => handleReorder(subSorted, subIdx, subIdx + 1)}
                                                  title="Вниз"
                                                >&#9660;</button>
                                              </div>
                                              <div className="flex items-center gap-2 px-2 py-1 flex-1 min-w-0">
                                                {isPlaced && <span className="text-green-400 text-[10px] flex-shrink-0">&#10003;</span>}
                                                {renderItemIcon(loc, 'sm')}
                                                <span className="truncate">{loc.name}</span>
                                                <span className="ml-auto flex-shrink-0">{renderEditButton(loc)}</span>
                                              </div>
                                            </div>
                                          );
                                        })}
                                      </div>
                                    );
                                  })()}
                                </div>
                              );
                            }
                            // Location child
                            const loc = dedupedItems.find((i) => i.type === 'location' && i.id === child.id);
                            if (!loc) return null;
                            const pos = getPosition(loc);
                            const isPlaced = pos.map_x != null && pos.map_y != null;
                            return (
                              <div
                                key={itemKey(loc)}
                                className={`flex items-center gap-0.5 mb-0.5 rounded text-[11px] text-[#d4e6f3] ${
                                  isPlaced ? 'bg-green-600/10' : 'bg-white/[0.03]'
                                }`}
                              >
                                <div className="flex flex-col flex-shrink-0">
                                  <button
                                    type="button"
                                    disabled={idx === 0}
                                    className="text-[10px] text-white/40 hover:text-white/70 bg-transparent border-none cursor-pointer disabled:opacity-20 disabled:cursor-default leading-none p-0"
                                    onClick={() => handleReorder(sortedChildren, idx, idx - 1)}
                                    title="Вверх"
                                  >&#9650;</button>
                                  <button
                                    type="button"
                                    disabled={idx === sortedChildren.length - 1}
                                    className="text-[10px] text-white/40 hover:text-white/70 bg-transparent border-none cursor-pointer disabled:opacity-20 disabled:cursor-default leading-none p-0"
                                    onClick={() => handleReorder(sortedChildren, idx, idx + 1)}
                                    title="Вниз"
                                  >&#9660;</button>
                                </div>
                                <div className="flex items-center gap-2 px-2 py-1 flex-1 min-w-0">
                                  {isPlaced && <span className="text-green-400 text-[10px] flex-shrink-0">&#10003;</span>}
                                  {renderItemIcon(loc, 'sm')}
                                  <span className="truncate">{loc.name}</span>
                                  <span className="ml-auto flex-shrink-0">{renderEditButton(loc)}</span>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      );
                    })()}
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
                    {renderMarkerBadge(item.marker_type, item.recommended_level)}
                    {item.type === 'district' && (
                      <span className="text-[9px] text-amber-400/60 flex-shrink-0">зона</span>
                    )}
                    {renderEditButton(item)}
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
                  <div className="relative">
                    {renderItemIcon(item, 'lg')}
                    {renderMarkerBadge(item.marker_type, item.recommended_level, 'map') && (
                      <div className="absolute -top-2.5 left-1/2 pointer-events-none">
                        {renderMarkerBadge(item.marker_type, item.recommended_level, 'map')}
                      </div>
                    )}
                  </div>

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
