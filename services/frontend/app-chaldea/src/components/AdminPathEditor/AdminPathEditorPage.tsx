import { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchRegionDetails,
  createNeighborWithPath,
  updateNeighborPath,
  deleteNeighborEdge,
} from '../../redux/actions/adminLocationsActions';
import type { NeighborEdge, PathWaypoint } from '../../redux/actions/worldMapActions';
import toast from 'react-hot-toast';
import PathEditorCanvas from './PathEditorCanvas';
import PathEditorToolbar from './PathEditorToolbar';

type EditorMode = 'draw' | 'edit' | 'delete';

const AdminPathEditorPage = () => {
  const { regionId } = useParams<{ regionId: string }>();
  const navigate = useNavigate();
  const dispatch = useAppDispatch();
  const regionIdNum = regionId ? parseInt(regionId) : null;

  const regionDetails = useAppSelector(
    (state) => regionIdNum ? state.adminLocations.regionDetails[regionIdNum] : null
  );
  const loading = useAppSelector((state) => state.adminLocations.loading);

  const [mode, setMode] = useState<EditorMode>('draw');
  const [selectedEdgeKey, setSelectedEdgeKey] = useState<string | null>(null);
  const [editWaypoints, setEditWaypoints] = useState<PathWaypoint[]>([]);
  const [drawStartId, setDrawStartId] = useState<number | null>(null);
  const [drawWaypoints, setDrawWaypoints] = useState<PathWaypoint[]>([]);
  const [energyCost, setEnergyCost] = useState(1);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch region details on mount
  useEffect(() => {
    if (regionIdNum) {
      dispatch(fetchRegionDetails(regionIdNum));
    }
  }, [dispatch, regionIdNum]);

  // Build edges list
  const edges: NeighborEdge[] = useMemo(
    () => regionDetails?.neighbor_edges ?? [],
    [regionDetails]
  );

  // Build location name map
  const locationNames = useMemo(() => {
    const map: Record<number, string> = {};
    if (!regionDetails) return map;
    for (const item of regionDetails.map_items) {
      if (item.type === 'location') {
        map[item.id] = item.name;
      }
    }
    // Also include locations from districts
    for (const d of regionDetails.districts) {
      for (const loc of d.locations) {
        map[loc.id] = loc.name;
      }
    }
    return map;
  }, [regionDetails]);

  // Collect district IDs that have city maps (and all their descendants)
  const cityMapDistrictIds = useMemo(() => {
    if (!regionDetails) return new Set<number>();
    const rootIds = new Set(
      regionDetails.districts.filter((d: any) => d.map_image_url).map((d: any) => d.id as number)
    );
    for (const item of regionDetails.map_items) {
      if (item.type === 'district' && (item as any).map_image_url) {
        rootIds.add(item.id);
      }
    }
    const allIds = new Set(rootIds);
    const collect = (parentId: number) => {
      for (const d of regionDetails.districts) {
        if ((d as any).parent_district_id === parentId && !allIds.has(d.id)) {
          allIds.add(d.id);
          collect(d.id);
        }
      }
      for (const item of regionDetails.map_items) {
        if (item.type === 'district' && (item as any).parent_district_id === parentId && !allIds.has(item.id)) {
          allIds.add(item.id);
          collect(item.id);
        }
      }
    };
    for (const rootId of rootIds) collect(rootId);
    return allIds;
  }, [regionDetails]);

  // Filter out city-level items
  const filteredMapItems = useMemo(() => {
    if (!regionDetails) return [];
    return regionDetails.map_items.filter((item: any) => {
      if (item.type === 'location' && item.district_id && cityMapDistrictIds.has(item.district_id)) return false;
      if (item.type === 'district' && item.parent_district_id && cityMapDistrictIds.has(item.parent_district_id)) return false;
      return true;
    });
  }, [regionDetails, cityMapDistrictIds]);

  // Build districts data for the canvas
  // Regular districts: show with their direct locations
  // City-map districts: show as markers with ALL their locations (including nested city locations)
  const districtsData = useMemo(() => {
    if (!regionDetails) return [];
    const result: { id: number; name: string; x: number; y: number; locations: { id: number; name: string; map_x?: number; map_y?: number }[] }[] = [];

    for (const d of regionDetails.districts) {
      // Skip sub-districts of city-map districts (they live inside the city, not on region map)
      if ((d as any).parent_district_id && cityMapDistrictIds.has((d as any).parent_district_id)) continue;

      if (cityMapDistrictIds.has(d.id)) {
        // City-map district: collect ALL locations from it and its sub-districts
        const cityLocations: { id: number; name: string }[] = [...d.locations.map((l: any) => ({ id: l.id, name: l.name }))];
        // Also collect locations from sub-districts of this city
        for (const sub of regionDetails.districts) {
          if ((sub as any).parent_district_id === d.id) {
            for (const loc of sub.locations) {
              cityLocations.push({ id: loc.id, name: loc.name });
            }
          }
        }
        result.push({
          id: d.id,
          name: d.name,
          x: d.x,
          y: d.y,
          locations: cityLocations,
        });
      } else {
        // Regular district: show with direct locations
        result.push({
          id: d.id,
          name: d.name,
          x: d.x,
          y: d.y,
          locations: d.locations.map((l: any) => ({
            id: l.id,
            name: l.name,
            map_x: l.map_x,
            map_y: l.map_y,
          })),
        });
      }
    }
    return result;
  }, [regionDetails, cityMapDistrictIds]);

  // When selecting an edge in edit mode, load its waypoints
  useEffect(() => {
    if (mode === 'edit' && selectedEdgeKey) {
      const edge = edges.find((e) => `${e.from_id}-${e.to_id}` === selectedEdgeKey);
      if (edge) {
        setEditWaypoints(edge.path_data ? [...edge.path_data] : []);
      }
    }
  }, [selectedEdgeKey, mode, edges]);

  // Reset drawing when mode changes
  useEffect(() => {
    setDrawStartId(null);
    setDrawWaypoints([]);
    setSelectedEdgeKey(null);
    setEditWaypoints([]);
  }, [mode]);

  // Handle draw click on a location
  const handleDrawClick = useCallback((locId: number) => {
    if (mode !== 'draw' || saving) return;

    if (drawStartId === null) {
      // Start drawing
      setDrawStartId(locId);
      setDrawWaypoints([]);
      return;
    }

    if (locId === drawStartId) {
      // Clicked same location — cancel
      setDrawStartId(null);
      setDrawWaypoints([]);
      return;
    }

    // End drawing — save the path
    setSaving(true);
    setError(null);
    dispatch(
      createNeighborWithPath({
        locationId: drawStartId,
        neighbor_id: locId,
        energy_cost: energyCost,
        path_data: drawWaypoints.length > 0 ? drawWaypoints : null,
      })
    )
      .unwrap()
      .then(async () => {
        toast.success('Путь создан');
        setDrawStartId(null);
        setDrawWaypoints([]);
        // Refresh region data
        if (regionIdNum) await dispatch(fetchRegionDetails(regionIdNum));
      })
      .catch((err) => {
        const msg = typeof err === 'string' ? err : 'Ошибка создания пути';
        toast.error(msg);
        setError(msg);
      })
      .finally(() => setSaving(false));
  }, [mode, drawStartId, drawWaypoints, energyCost, dispatch, regionIdNum]);

  // Handle save in edit mode
  const handleSave = useCallback(() => {
    if (!selectedEdgeKey) return;
    const edge = edges.find((e) => `${e.from_id}-${e.to_id}` === selectedEdgeKey);
    if (!edge) return;

    setSaving(true);
    setError(null);
    dispatch(
      updateNeighborPath({
        fromId: edge.from_id,
        toId: edge.to_id,
        path_data: editWaypoints,
      })
    )
      .unwrap()
      .then(async () => {
        toast.success('Путь обновлён');
        if (regionIdNum) await dispatch(fetchRegionDetails(regionIdNum));
      })
      .catch((err) => {
        const msg = typeof err === 'string' ? err : 'Ошибка обновления пути';
        toast.error(msg);
        setError(msg);
      })
      .finally(() => setSaving(false));
  }, [selectedEdgeKey, edges, editWaypoints, dispatch, regionIdNum]);

  // Handle delete
  const handleDelete = useCallback(() => {
    if (!selectedEdgeKey) return;
    const edge = edges.find((e) => `${e.from_id}-${e.to_id}` === selectedEdgeKey);
    if (!edge) return;

    const fromName = locationNames[edge.from_id] || `#${edge.from_id}`;
    const toName = locationNames[edge.to_id] || `#${edge.to_id}`;

    if (!window.confirm(`Удалить путь ${fromName} \u2194 ${toName}? Связь между локациями будет удалена.`)) {
      return;
    }

    setSaving(true);
    setError(null);
    dispatch(deleteNeighborEdge({ locationId: edge.from_id, neighborId: edge.to_id }))
      .unwrap()
      .then(async () => {
        toast.success('Путь удалён');
        setSelectedEdgeKey(null);
        if (regionIdNum) await dispatch(fetchRegionDetails(regionIdNum));
      })
      .catch((err) => {
        const msg = typeof err === 'string' ? err : 'Ошибка удаления пути';
        toast.error(msg);
        setError(msg);
      })
      .finally(() => setSaving(false));
  }, [selectedEdgeKey, edges, locationNames, dispatch, regionIdNum]);

  // Handle delete from canvas click
  const handleDeleteFromCanvas = useCallback((fromId: number, toId: number) => {
    const fromName = locationNames[fromId] || `#${fromId}`;
    const toName = locationNames[toId] || `#${toId}`;

    if (!window.confirm(`Удалить путь ${fromName} \u2194 ${toName}? Связь между локациями будет удалена.`)) {
      return;
    }

    setSaving(true);
    setError(null);
    dispatch(deleteNeighborEdge({ locationId: fromId, neighborId: toId }))
      .unwrap()
      .then(async () => {
        toast.success('Путь удалён');
        if (regionIdNum) await dispatch(fetchRegionDetails(regionIdNum));
      })
      .catch((err) => {
        const msg = typeof err === 'string' ? err : 'Ошибка удаления пути';
        toast.error(msg);
        setError(msg);
      })
      .finally(() => setSaving(false));
  }, [locationNames, dispatch, regionIdNum]);

  // Zone location select handler (for draw mode via district)
  const handleZoneLocationSelect = useCallback((_districtId: number, _locationId: number) => {
    // The actual draw click is handled by onDrawClick in the canvas after zone select
  }, []);

  if (!regionIdNum) {
    return (
      <div className="p-6">
        <p className="text-site-red text-lg">Неверный ID региона</p>
      </div>
    );
  }

  if (loading && !regionDetails) {
    return (
      <div className="p-6 flex items-center justify-center min-h-[300px]">
        <div className="flex flex-col items-center gap-3">
          <div className="w-8 h-8 border-2 border-gold/30 border-t-gold rounded-full animate-spin" />
          <p className="text-white/50 text-sm">Загрузка региона...</p>
        </div>
      </div>
    );
  }

  if (!regionDetails) {
    return (
      <div className="p-6">
        <p className="text-site-red text-lg">Не удалось загрузить данные региона</p>
        <button className="btn-line mt-4 text-sm" onClick={() => navigate('/admin/locations')}>
          Назад к локациям
        </button>
      </div>
    );
  }

  if (!regionDetails.map_image_url) {
    return (
      <div className="p-6">
        <p className="text-white text-lg">Для этого региона не загружена карта</p>
        <button className="btn-line mt-4 text-sm" onClick={() => navigate('/admin/locations')}>
          Назад к локациям
        </button>
      </div>
    );
  }

  return (
    <div className="py-4 px-2 sm:px-4">
      {/* Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 mb-4">
        <div>
          <h1 className="gold-text text-xl sm:text-2xl font-medium uppercase">
            Редактор путей
          </h1>
          <p className="text-white/50 text-sm mt-1">{regionDetails.name}</p>
        </div>
        <button
          className="btn-line text-sm"
          onClick={() => navigate('/admin/locations')}
        >
          Назад к локациям
        </button>
      </div>

      {/* Error display */}
      {error && (
        <div className="mb-4 px-3 py-2 bg-red-600/20 border border-red-500/30 rounded text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Main editor area */}
      <div className="bg-black/30 rounded-lg border border-white/10 overflow-hidden">
        <div className="flex flex-col md:flex-row">
          {/* Toolbar */}
          <PathEditorToolbar
            mode={mode}
            onModeChange={setMode}
            edges={edges}
            selectedEdgeKey={selectedEdgeKey}
            onSelectEdge={setSelectedEdgeKey}
            locationNames={locationNames}
            saving={saving}
            onSave={handleSave}
            onDelete={handleDelete}
            energyCost={energyCost}
            onEnergyCostChange={setEnergyCost}
            drawingActive={drawStartId !== null}
          />

          {/* Canvas */}
          <PathEditorCanvas
            mapImageUrl={regionDetails.map_image_url}
            mapItems={filteredMapItems}
            districts={districtsData}
            edges={edges}
            mode={mode}
            selectedEdgeKey={selectedEdgeKey}
            onSelectEdge={setSelectedEdgeKey}
            editWaypoints={editWaypoints}
            onEditWaypointsChange={setEditWaypoints}
            drawStartId={drawStartId}
            drawWaypoints={drawWaypoints}
            onDrawClick={handleDrawClick}
            onDrawWaypointAdd={(pt) => setDrawWaypoints((prev) => [...prev, pt])}
            onDeleteEdge={handleDeleteFromCanvas}
            onZoneLocationSelect={handleZoneLocationSelect}
          />
        </div>
      </div>
    </div>
  );
};

export default AdminPathEditorPage;
