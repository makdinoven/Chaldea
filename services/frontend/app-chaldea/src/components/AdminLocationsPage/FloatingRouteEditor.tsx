import { useEffect, useRef, useState, type SyntheticEvent } from 'react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import { updateFloatingStructure } from '../../redux/slices/floatingStructuresSlice';
import type { RouteWaypoint } from '../../redux/slices/floatingStructuresSlice';
import { selectAreas } from '../../redux/slices/worldMapSlice';
import { fetchAreas } from '../../redux/actions/worldMapActions';
import {
  addWaypoint,
  deleteWaypoint,
  eventToPct,
  findInsertIndex,
  insertWaypoint,
  updateWaypoint,
  waypointsToPolygonPoints,
} from './waypointUtils';

interface Props {
  structureId: number;
  initialRoute: RouteWaypoint[];
  areaId?: number | null;
  onClose: () => void;
}

/**
 * Slim dedicated waypoint editor for a floating-structure route.
 *
 * Features:
 * - Loads world-map background (areas[0].map_image_url) as the editing canvas.
 * - Renders existing route_json as an OPEN polyline (A → B, stops at B) with draggable handles.
 * - Left-click anywhere: append waypoint at end of the route.
 * - Shift + left-click: insert waypoint into the closest segment (explicit gesture).
 * - Right-click a waypoint: delete it.
 * - Drag a waypoint to reposition.
 * - Save persists route_json via PATCH (updateFloatingStructure thunk from T9).
 *
 * Per FEAT-123 §3.5 / §4.T12: this editor MUST NOT modify RegionMapEditor.tsx.
 */
const FloatingRouteEditor = ({ structureId, initialRoute, areaId, onClose }: Props) => {
  const dispatch = useAppDispatch();
  const areas = useAppSelector(selectAreas);
  const matchedArea = areaId != null ? areas.find((a) => a.id === areaId) : null;
  const worldMapUrl = matchedArea?.map_image_url
    ?? (areas.length > 0 ? areas[0]?.map_image_url ?? null : null);

  const [waypoints, setWaypoints] = useState<RouteWaypoint[]>(initialRoute ?? []);
  const [draggingIdx, setDraggingIdx] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);
  const [aspectRatio, setAspectRatio] = useState<string>('16 / 9');
  const containerRef = useRef<HTMLDivElement | null>(null);

  const handleImgLoad = (e: SyntheticEvent<HTMLImageElement>) => {
    const img = e.currentTarget;
    if (img.naturalWidth > 0 && img.naturalHeight > 0) {
      setAspectRatio(`${img.naturalWidth} / ${img.naturalHeight}`);
    }
  };

  useEffect(() => {
    if (areas.length === 0) {
      dispatch(fetchAreas());
    }
  }, [areas.length, dispatch]);

  const handleCanvasClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!containerRef.current) return;
    if (draggingIdx !== null) return;
    const target = e.target as HTMLElement;
    // Ignore clicks on waypoint handles (they have data-waypoint="1")
    if (target.dataset.waypoint === '1') return;
    const point = eventToPct(e, containerRef.current);
    // Default: always append. Mid-segment insertion requires explicit Shift+LMB.
    if (e.shiftKey) {
      // Generous threshold so the explicit insert gesture rarely fails; if
      // there are <2 waypoints or no segment nearby, fall back to append.
      const insertIdx = findInsertIndex(waypoints, point, 100);
      if (insertIdx !== null) {
        setWaypoints((prev) => insertWaypoint(prev, insertIdx, point));
        return;
      }
    }
    setWaypoints((prev) => addWaypoint(prev, point));
  };

  const handleWaypointMouseDown = (idx: number) => (e: React.MouseEvent) => {
    e.stopPropagation();
    if (e.button !== 0) return;
    setDraggingIdx(idx);
  };

  const handleWaypointContextMenu = (idx: number) => (e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setWaypoints((prev) => deleteWaypoint(prev, idx));
  };

  useEffect(() => {
    if (draggingIdx === null) return;
    const onMove = (ev: MouseEvent) => {
      if (!containerRef.current) return;
      const point = eventToPct(ev, containerRef.current);
      setWaypoints((prev) => updateWaypoint(prev, draggingIdx, point));
    };
    const onUp = () => setDraggingIdx(null);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, [draggingIdx]);

  const handleSave = async () => {
    if (waypoints.length < 2) {
      toast.error('Маршрут должен содержать минимум 2 точки');
      return;
    }
    setSaving(true);
    try {
      const result = await dispatch(
        updateFloatingStructure({
          id: structureId,
          payload: { route_json: waypoints, started_at: new Date().toISOString() },
        }),
      );
      if (updateFloatingStructure.fulfilled.match(result)) {
        onClose();
      }
    } finally {
      setSaving(false);
    }
  };

  const handleClear = () => {
    if (waypoints.length === 0) return;
    if (window.confirm('Удалить все точки маршрута?')) {
      setWaypoints([]);
    }
  };

  return (
    <div className="modal-overlay fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-2 sm:p-4">
      <div className="modal-content relative w-full max-w-6xl max-h-[95vh] overflow-y-auto rounded-lg bg-site-bg p-4 sm:p-6">
        <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <h2 className="gold-text text-xl sm:text-2xl font-medium uppercase">
            Редактор маршрута
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="text-white/70 hover:text-white text-sm self-end sm:self-auto"
          >
            Закрыть
          </button>
        </div>

        <div className="mb-3 text-white/70 text-xs sm:text-sm space-y-1">
          <p>ЛКМ — добавить точку в конец маршрута.</p>
          <p>Shift + ЛКМ — вставить точку между существующими (в ближайший сегмент).</p>
          <p>ПКМ по точке — удалить точку.</p>
          <p>Перетаскивание точки — переместить её.</p>
          <p>Маршрут: структура движется A → B и останавливается в конце. Первая точка — A, последняя — B.</p>
        </div>

        {worldMapUrl ? (
          <div
            ref={containerRef}
            onClick={handleCanvasClick}
            className="relative w-full overflow-hidden rounded-md border border-white/20 bg-site-dark select-none"
            style={{ aspectRatio }}
          >
            <img
              src={worldMapUrl}
              alt="Карта мира"
              className="w-full h-full object-cover pointer-events-none"
              draggable={false}
              onLoad={handleImgLoad}
            />
            {waypoints.length >= 2 && (
              <svg
                className="absolute inset-0 h-full w-full pointer-events-none"
                viewBox="0 0 100 100"
                preserveAspectRatio="none"
              >
                <polyline
                  points={waypointsToPolygonPoints(waypoints)}
                  fill="none"
                  stroke="rgba(255, 215, 0, 0.9)"
                  strokeWidth="0.3"
                  vectorEffect="non-scaling-stroke"
                />
              </svg>
            )}
            {waypoints.map((w, idx) => {
              const isFirst = idx === 0;
              const isLast = idx === waypoints.length - 1 && waypoints.length > 1;
              const colorClass = isFirst
                ? 'border-green-300 bg-green-500/80 hover:bg-green-400'
                : isLast
                ? 'border-red-300 bg-red-500/80 hover:bg-red-400'
                : 'border-yellow-300 bg-yellow-500/80 hover:bg-yellow-400';
              const label = isFirst ? 'A' : isLast ? 'B' : `${idx + 1}`;
              return (
                <button
                  key={idx}
                  type="button"
                  data-waypoint="1"
                  onMouseDown={handleWaypointMouseDown(idx)}
                  onContextMenu={handleWaypointContextMenu(idx)}
                  className={`absolute z-10 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 cursor-move flex items-center justify-center text-[9px] font-bold text-black ${colorClass}`}
                  style={{
                    left: `${w.x}%`,
                    top: `${w.y}%`,
                    width: '16px',
                    height: '16px',
                  }}
                  title={isFirst ? 'A (старт)' : isLast ? 'B (конец)' : `Точка ${idx + 1}`}
                >
                  <span data-waypoint="1">{label}</span>
                </button>
              );
            })}
          </div>
        ) : (
          <div className="flex h-64 items-center justify-center rounded-md border border-white/20 bg-site-dark text-white/50 text-sm">
            Загрузка карты мира...
          </div>
        )}

        <div className="mt-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div className="text-white/70 text-sm">
            Точек: <span className="text-white">{waypoints.length}</span>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={handleClear}
              className="btn-line px-4 py-2 text-sm"
              disabled={saving}
            >
              Очистить
            </button>
            <button
              type="button"
              onClick={onClose}
              className="btn-line px-4 py-2 text-sm"
              disabled={saving}
            >
              Отмена
            </button>
            <button
              type="button"
              onClick={handleSave}
              className="btn-blue px-4 py-2 text-sm"
              disabled={saving || waypoints.length < 2}
            >
              {saving ? 'Сохранение...' : 'Сохранить'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default FloatingRouteEditor;
