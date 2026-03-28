import { useState, useEffect, useCallback, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  fetchRegionDetails,
  createNeighborWithPath,
  updateNeighborPath,
  deleteNeighborEdge,
  createTransitionArrow,
  deleteTransitionArrow,
  createArrowNeighbor,
  deleteArrowNeighbor,
} from '../../redux/actions/adminLocationsActions';
import { fetchHierarchyTree } from '../../redux/actions/worldMapActions';
import type { NeighborEdge, PathWaypoint, ArrowEdge } from '../../redux/actions/worldMapActions';
import toast from 'react-hot-toast';
import PathEditorCanvas from './PathEditorCanvas';
import PathEditorToolbar from './PathEditorToolbar';

type EditorMode = 'draw' | 'edit' | 'delete' | 'arrow';

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

  // Arrow-related state
  const [arrowPlacementPos, setArrowPlacementPos] = useState<{ x: number; y: number } | null>(null);
  const [arrowTargetRegionId, setArrowTargetRegionId] = useState<number | ''>('');
  const [arrowLabel, setArrowLabel] = useState('');
  const [showArrowForm, setShowArrowForm] = useState(false);

  // Hierarchy tree for region selection (used in arrow creation)
  const hierarchyTree = useAppSelector((state) => state.worldMap.hierarchyTree);

  // Fetch region details and hierarchy tree on mount
  useEffect(() => {
    if (regionIdNum) {
      dispatch(fetchRegionDetails(regionIdNum));
    }
    dispatch(fetchHierarchyTree());
  }, [dispatch, regionIdNum]);

  // Build list of all regions from hierarchy tree for arrow target selection
  const allRegions = useMemo(() => {
    const regions: { id: number; name: string }[] = [];
    const collectRegions = (nodes: typeof hierarchyTree) => {
      for (const node of nodes) {
        if (node.type === 'region' && node.id !== regionIdNum) {
          regions.push({ id: node.id, name: node.name });
        }
        if (node.children) {
          collectRegions(node.children);
        }
      }
    };
    collectRegions(hierarchyTree);
    return regions;
  }, [hierarchyTree, regionIdNum]);

  // Build edges list
  const edges: NeighborEdge[] = useMemo(
    () => regionDetails?.neighbor_edges ?? [],
    [regionDetails]
  );

  // Build arrow edges list
  const arrowEdges: ArrowEdge[] = useMemo(
    () => regionDetails?.arrow_edges ?? [],
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
    // Also include arrow items
    for (const item of regionDetails.map_items) {
      if (item.type === 'arrow') {
        map[item.id] = item.name;
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
    setShowArrowForm(false);
    setArrowPlacementPos(null);
  }, [mode]);

  // Handle draw click on a location
  const handleDrawClick = useCallback((locId: number) => {
    if ((mode !== 'draw' && mode !== 'arrow') || saving) return;

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

  // Handle delete from canvas click — supports both location and arrow edges
  const handleDeleteFromCanvas = useCallback((fromId: number, toId: number) => {
    // Check if this is an arrow edge key (format: "arrow-{locationId}-{arrowId}" split gives 3 parts)
    // But this callback gets numeric fromId/toId from edge key splitting.
    // Regular edges: fromId-toId
    // Arrow edges are handled separately through selectedEdgeKey
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

  // Handle arrow draw click — when user clicks an arrow marker in draw mode
  const handleArrowDrawClick = useCallback((arrowId: number) => {
    if ((mode !== 'draw' && mode !== 'arrow') || saving) return;

    if (drawStartId === null) {
      // Cannot start drawing from an arrow — arrows are endpoints only
      // Use arrowId as the startId but mark it as arrow
      // Actually, we can allow starting from arrow too
      setDrawStartId(arrowId);
      setDrawWaypoints([]);
      return;
    }

    // End drawing: one end is a location, other is an arrow
    // Determine which is which
    const startIsLocation = regionDetails?.map_items.some(
      (item) => item.type === 'location' && item.id === drawStartId
    ) || regionDetails?.districts.some(
      (d) => d.locations.some((l: { id: number }) => l.id === drawStartId)
    );
    const endIsArrow = regionDetails?.map_items.some(
      (item) => item.type === 'arrow' && item.id === arrowId
    );

    if (startIsLocation && endIsArrow) {
      // Location -> Arrow path
      setSaving(true);
      setError(null);
      dispatch(
        createArrowNeighbor({
          arrowId,
          location_id: drawStartId,
          energy_cost: energyCost,
          path_data: drawWaypoints.length > 0 ? drawWaypoints : null,
        })
      )
        .unwrap()
        .then(async () => {
          toast.success('Путь к стрелке создан');
          setDrawStartId(null);
          setDrawWaypoints([]);
          if (regionIdNum) await dispatch(fetchRegionDetails(regionIdNum));
        })
        .catch((err) => {
          const msg = typeof err === 'string' ? err : 'Ошибка создания пути к стрелке';
          toast.error(msg);
          setError(msg);
        })
        .finally(() => setSaving(false));
    } else {
      // Invalid combination
      toast.error('Путь можно создать только между локацией и стрелкой');
      setDrawStartId(null);
      setDrawWaypoints([]);
    }
  }, [mode, saving, drawStartId, drawWaypoints, energyCost, dispatch, regionIdNum, regionDetails]);

  // Also handle when draw starts from an arrow and ends on a location
  const handleDrawClickWithArrowSupport = useCallback((locId: number) => {
    if ((mode !== 'draw' && mode !== 'arrow') || saving) return;

    // Check if drawStartId is an arrow
    const startIsArrow = drawStartId !== null && regionDetails?.map_items.some(
      (item) => item.type === 'arrow' && item.id === drawStartId
    );

    if (startIsArrow && drawStartId !== null) {
      // Arrow -> Location path
      setSaving(true);
      setError(null);
      dispatch(
        createArrowNeighbor({
          arrowId: drawStartId,
          location_id: locId,
          energy_cost: energyCost,
          path_data: drawWaypoints.length > 0 ? [...drawWaypoints].reverse() : null,
        })
      )
        .unwrap()
        .then(async () => {
          toast.success('Путь к стрелке создан');
          setDrawStartId(null);
          setDrawWaypoints([]);
          if (regionIdNum) await dispatch(fetchRegionDetails(regionIdNum));
        })
        .catch((err) => {
          const msg = typeof err === 'string' ? err : 'Ошибка создания пути к стрелке';
          toast.error(msg);
          setError(msg);
        })
        .finally(() => setSaving(false));
      return;
    }

    // Normal location-to-location draw
    handleDrawClick(locId);
  }, [mode, saving, drawStartId, drawWaypoints, energyCost, dispatch, regionIdNum, regionDetails, handleDrawClick]);

  // Handle arrow creation — first set position, then show form for target region
  const handleArrowPlacement = useCallback((x: number, y: number) => {
    setArrowPlacementPos({ x, y });
    setShowArrowForm(true);
    setArrowTargetRegionId('');
    setArrowLabel('');
  }, []);

  // Confirm arrow creation
  const handleArrowCreate = useCallback(() => {
    if (!arrowPlacementPos || !arrowTargetRegionId || !regionIdNum) return;

    setSaving(true);
    setError(null);
    dispatch(
      createTransitionArrow({
        region_id: regionIdNum,
        target_region_id: Number(arrowTargetRegionId),
        x: arrowPlacementPos.x,
        y: arrowPlacementPos.y,
        label: arrowLabel || null,
      })
    )
      .unwrap()
      .then(async () => {
        toast.success('Стрелка перехода создана');
        setShowArrowForm(false);
        setArrowPlacementPos(null);
        setMode('draw');
        if (regionIdNum) await dispatch(fetchRegionDetails(regionIdNum));
      })
      .catch((err) => {
        const msg = typeof err === 'string' ? err : 'Ошибка создания стрелки';
        toast.error(msg);
        setError(msg);
      })
      .finally(() => setSaving(false));
  }, [arrowPlacementPos, arrowTargetRegionId, arrowLabel, regionIdNum, dispatch]);

  // Handle arrow deletion from canvas
  const handleDeleteArrow = useCallback((arrowId: number) => {
    const arrowItem = regionDetails?.map_items.find(
      (item) => item.type === 'arrow' && item.id === arrowId
    );
    const arrowName = arrowItem?.name || `#${arrowId}`;

    if (!window.confirm(`Удалить стрелку "${arrowName}" и парную стрелку в целевом регионе?`)) {
      return;
    }

    setSaving(true);
    setError(null);
    dispatch(deleteTransitionArrow(arrowId))
      .unwrap()
      .then(async () => {
        toast.success('Стрелка удалена');
        if (regionIdNum) await dispatch(fetchRegionDetails(regionIdNum));
      })
      .catch((err) => {
        const msg = typeof err === 'string' ? err : 'Ошибка удаления стрелки';
        toast.error(msg);
        setError(msg);
      })
      .finally(() => setSaving(false));
  }, [regionDetails, dispatch, regionIdNum]);

  // Handle arrow edge deletion
  const handleDeleteArrowEdge = useCallback((locationId: number, arrowId: number) => {
    const locName = locationNames[locationId] || `#${locationId}`;
    const arrowItem = regionDetails?.map_items.find(
      (item) => item.type === 'arrow' && item.id === arrowId
    );
    const arrowName = arrowItem?.name || `#${arrowId}`;

    if (!window.confirm(`Удалить путь ${locName} \u2194 ${arrowName}?`)) {
      return;
    }

    setSaving(true);
    setError(null);
    dispatch(deleteArrowNeighbor({ locationId, arrowId }))
      .unwrap()
      .then(async () => {
        toast.success('Путь к стрелке удалён');
        if (regionIdNum) await dispatch(fetchRegionDetails(regionIdNum));
      })
      .catch((err) => {
        const msg = typeof err === 'string' ? err : 'Ошибка удаления пути к стрелке';
        toast.error(msg);
        setError(msg);
      })
      .finally(() => setSaving(false));
  }, [locationNames, regionDetails, dispatch, regionIdNum]);

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
            arrowEdges={arrowEdges}
            selectedEdgeKey={selectedEdgeKey}
            onSelectEdge={setSelectedEdgeKey}
            locationNames={locationNames}
            saving={saving}
            onSave={handleSave}
            onDelete={handleDelete}
            energyCost={energyCost}
            onEnergyCostChange={setEnergyCost}
            drawingActive={drawStartId !== null}
            arrowItems={regionDetails.map_items.filter((i) => i.type === 'arrow')}
            onDeleteArrow={handleDeleteArrow}
          />

          {/* Canvas */}
          <PathEditorCanvas
            mapImageUrl={regionDetails.map_image_url}
            mapItems={filteredMapItems}
            districts={districtsData}
            edges={edges}
            arrowEdges={arrowEdges}
            mode={mode === 'arrow' ? 'draw' : mode}
            selectedEdgeKey={selectedEdgeKey}
            onSelectEdge={setSelectedEdgeKey}
            editWaypoints={editWaypoints}
            onEditWaypointsChange={setEditWaypoints}
            drawStartId={drawStartId}
            drawWaypoints={drawWaypoints}
            onDrawClick={handleDrawClickWithArrowSupport}
            onDrawWaypointAdd={(pt) => setDrawWaypoints((prev) => [...prev, pt])}
            onDeleteEdge={handleDeleteFromCanvas}
            onDeleteArrowEdge={handleDeleteArrowEdge}
            onZoneLocationSelect={handleZoneLocationSelect}
            onArrowDrawClick={mode === 'delete' ? handleDeleteArrow : handleArrowDrawClick}
            onEmptyMapClick={mode === 'arrow' ? (x, y) => handleArrowPlacement(x, y) : undefined}
          />
        </div>
      </div>
      {/* Arrow creation form */}
      {showArrowForm && arrowPlacementPos && (
        <div
          className="modal-overlay"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              setShowArrowForm(false);
              setArrowPlacementPos(null);
            }
          }}
        >
          <div className="modal-content max-w-sm w-full mx-4">
            <h3 className="gold-text text-lg font-medium uppercase mb-4">
              Создать стрелку перехода
            </h3>
            <div className="space-y-3">
              <div>
                <label className="text-xs text-white/50 uppercase tracking-wide block mb-1">
                  Целевой регион
                </label>
                <select
                  value={arrowTargetRegionId}
                  onChange={(e) => setArrowTargetRegionId(e.target.value ? Number(e.target.value) : '')}
                  className="w-full bg-black/40 border border-white/20 rounded px-3 py-2 text-white text-sm focus:border-gold/50 focus:outline-none"
                >
                  <option value="">Выберите регион...</option>
                  {allRegions.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-xs text-white/50 uppercase tracking-wide block mb-1">
                  Метка (необязательно)
                </label>
                <input
                  type="text"
                  value={arrowLabel}
                  onChange={(e) => setArrowLabel(e.target.value)}
                  placeholder="Например: К региону..."
                  className="input-underline w-full text-sm"
                  maxLength={255}
                />
              </div>
              <div className="text-xs text-white/40">
                Позиция: ({arrowPlacementPos.x.toFixed(1)}, {arrowPlacementPos.y.toFixed(1)})
              </div>
              <div className="flex gap-2">
                <button
                  className="btn-blue text-sm py-1.5 flex-1"
                  onClick={handleArrowCreate}
                  disabled={saving || !arrowTargetRegionId}
                >
                  {saving ? 'Создание...' : 'Создать'}
                </button>
                <button
                  className="btn-line text-sm py-1.5 flex-1"
                  onClick={() => {
                    setShowArrowForm(false);
                    setArrowPlacementPos(null);
                  }}
                >
                  Отмена
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminPathEditorPage;
