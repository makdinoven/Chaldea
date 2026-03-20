import { useState, useRef, useEffect, useCallback } from 'react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  fetchClickableZones,
  createClickableZone,
  updateClickableZone,
  deleteClickableZone,
} from '../../../redux/actions/adminLocationsActions';
import type { ClickableZone, ZonePoint } from '../../../redux/actions/adminLocationsActions';

// --- Types ---

interface TargetOption {
  id: number;
  name: string;
}

interface AdminClickableZoneEditorProps {
  parentType: 'area' | 'country';
  parentId: number;
  mapImageUrl: string | null;
  /** Available target entities (countries for area parent, regions for country parent) */
  targetOptions: TargetOption[];
  targetType: 'country' | 'region';
  /** Available areas as targets (for per-zone target type switching) */
  areaOptions?: TargetOption[];
  onClose?: () => void;
}

interface DragState {
  startX: number;
  startY: number;
  currentX: number;
  currentY: number;
}

interface EditingZone {
  zoneId: number;
  label: string;
  targetId: string;
  strokeColor: string;
  targetType: 'country' | 'region' | 'area';
}

type DrawingMode = 'rectangle' | 'polygon';

// --- Component ---

const AdminClickableZoneEditor = ({
  parentType,
  parentId,
  mapImageUrl,
  targetOptions,
  targetType,
  areaOptions,
  onClose,
}: AdminClickableZoneEditorProps) => {
  const dispatch = useAppDispatch();
  const { clickableZones, loading } = useAppSelector((state) => state.adminLocations);

  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Drawing mode
  const [drawingMode, setDrawingMode] = useState<DrawingMode>('polygon');

  // Rectangle drawing state
  const [dragState, setDragState] = useState<DragState | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  // Polygon drawing state
  const [polygonPoints, setPolygonPoints] = useState<ZonePoint[]>([]);
  const [cursorPos, setCursorPos] = useState<{ x: number; y: number } | null>(null);
  const [polygonFinalized, setPolygonFinalized] = useState(false);

  const [selectedZoneId, setSelectedZoneId] = useState<number | null>(null);

  // New zone form
  const [newZoneLabel, setNewZoneLabel] = useState('');
  const [newZoneTargetId, setNewZoneTargetId] = useState('');
  const [newZoneColor, setNewZoneColor] = useState('#f0d95c');
  const [newZoneTargetType, setNewZoneTargetType] = useState<'country' | 'region' | 'area'>(targetType);

  // Edit zone form
  const [editingZone, setEditingZone] = useState<EditingZone | null>(null);

  // Load zones on mount
  useEffect(() => {
    dispatch(fetchClickableZones({ parentType, parentId }));
  }, [dispatch, parentType, parentId]);

  // --- Coordinate conversion ---

  const getPercentCoords = useCallback(
    (clientX: number, clientY: number): { x: number; y: number } => {
      if (!containerRef.current) return { x: 0, y: 0 };
      const rect = containerRef.current.getBoundingClientRect();
      const x = ((clientX - rect.left) / rect.width) * 100;
      const y = ((clientY - rect.top) / rect.height) * 100;
      return {
        x: Math.max(0, Math.min(100, x)),
        y: Math.max(0, Math.min(100, y)),
      };
    },
    []
  );

  // --- Polygon helpers ---

  const distanceBetween = (a: { x: number; y: number }, b: { x: number; y: number }): number => {
    return Math.sqrt((a.x - b.x) ** 2 + (a.y - b.y) ** 2);
  };

  const CLOSE_THRESHOLD = 3; // percent distance to snap to first point

  const finalizePolygon = useCallback(() => {
    if (polygonPoints.length < 3) {
      toast.error('Минимум 3 точки для полигона');
      return;
    }
    setPolygonFinalized(true);
    setCursorPos(null);
  }, [polygonPoints.length]);

  const clearPolygonDrawing = () => {
    setPolygonPoints([]);
    setCursorPos(null);
    setPolygonFinalized(false);
    setNewZoneLabel('');
    setNewZoneTargetId('');
    setNewZoneColor('#f0d95c');
    setNewZoneTargetType(targetType);
  };

  const handleUndoLastPoint = () => {
    setPolygonPoints((prev) => prev.slice(0, -1));
  };

  // --- Drawing handlers ---

  const handleMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
    if (drawingMode === 'polygon') return; // polygon uses click, not drag

    if (selectedZoneId) {
      setSelectedZoneId(null);
      return;
    }

    const coords = getPercentCoords(e.clientX, e.clientY);
    setDragState({
      startX: coords.x,
      startY: coords.y,
      currentX: coords.x,
      currentY: coords.y,
    });
    setIsDragging(true);
  };

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    const coords = getPercentCoords(e.clientX, e.clientY);

    // Polygon: update cursor position for follow-line
    if (drawingMode === 'polygon' && polygonPoints.length > 0 && !polygonFinalized) {
      setCursorPos(coords);
    }

    // Rectangle: update drag
    if (drawingMode === 'rectangle' && isDragging && dragState) {
      setDragState((prev) =>
        prev ? { ...prev, currentX: coords.x, currentY: coords.y } : null
      );
    }
  };

  const handleMouseUp = () => {
    if (drawingMode === 'polygon') return;
    if (!isDragging || !dragState) return;
    setIsDragging(false);

    const width = Math.abs(dragState.currentX - dragState.startX);
    const height = Math.abs(dragState.currentY - dragState.startY);

    // Only create if zone is big enough (at least 2% in each dimension)
    if (width < 2 || height < 2) {
      setDragState(null);
      return;
    }

    // Keep dragState for the form - user needs to fill label and target
  };

  const handleSvgClick = (e: React.MouseEvent<SVGSVGElement>) => {
    if (drawingMode !== 'polygon') return;
    if (polygonFinalized) return;

    // Deselect zone if one is selected
    if (selectedZoneId) {
      setSelectedZoneId(null);
      return;
    }

    const coords = getPercentCoords(e.clientX, e.clientY);

    // Check if clicking near first point to close
    if (polygonPoints.length >= 3) {
      const first = polygonPoints[0];
      if (distanceBetween(coords, first) < CLOSE_THRESHOLD) {
        finalizePolygon();
        return;
      }
    }

    setPolygonPoints((prev) => [...prev, coords]);
  };

  const handleSvgDoubleClick = (e: React.MouseEvent<SVGSVGElement>) => {
    // Disabled: double-click was causing accidental polygon finalization.
    // Use "click near first point" or "Завершить" button instead.
    e.preventDefault();
  };

  const handleSaveNewZone = async () => {
    if (!newZoneTargetId) {
      toast.error('Выберите целевой объект для зоны');
      return;
    }

    let zoneData: ZonePoint[];

    if (drawingMode === 'polygon') {
      if (polygonPoints.length < 3) {
        toast.error('Минимум 3 точки для зоны');
        return;
      }
      zoneData = polygonPoints;
    } else {
      if (!dragState) return;

      const x1 = Math.min(dragState.startX, dragState.currentX);
      const y1 = Math.min(dragState.startY, dragState.currentY);
      const x2 = Math.max(dragState.startX, dragState.currentX);
      const y2 = Math.max(dragState.startY, dragState.currentY);

      zoneData = [
        { x: x1, y: y1 },
        { x: x2, y: y1 },
        { x: x2, y: y2 },
        { x: x1, y: y2 },
      ];
    }

    try {
      await dispatch(
        createClickableZone({
          parent_type: parentType,
          parent_id: parentId,
          target_type: newZoneTargetType,
          target_id: Number(newZoneTargetId),
          zone_data: zoneData,
          label: newZoneLabel || undefined,
          stroke_color: newZoneColor,
        })
      ).unwrap();

      toast.success('Зона создана. Можно нарисовать ещё одну.');

      // Keep target type, target id, and color for quick multi-polygon creation
      const savedTargetType = newZoneTargetType;
      const savedTargetId = newZoneTargetId;
      const savedColor = newZoneColor;

      setDragState(null);
      clearPolygonDrawing();

      // Restore target selection so user can immediately draw another polygon for the same target
      setNewZoneTargetType(savedTargetType);
      setNewZoneTargetId(savedTargetId);
      setNewZoneColor(savedColor);

      dispatch(fetchClickableZones({ parentType, parentId }));
    } catch {
      toast.error('Ошибка создания зоны');
    }
  };

  const handleCancelNewZone = () => {
    setDragState(null);
    clearPolygonDrawing();
  };

  // --- Edit/Delete zone ---

  const handleStartEdit = (zone: ClickableZone) => {
    setEditingZone({
      zoneId: zone.id,
      label: zone.label || '',
      targetId: String(zone.target_id),
      strokeColor: zone.stroke_color || '#f0d95c',
      targetType: zone.target_type,
    });
    setSelectedZoneId(zone.id);
  };

  const handleSaveEdit = async () => {
    if (!editingZone) return;

    try {
      await dispatch(
        updateClickableZone({
          id: editingZone.zoneId,
          label: editingZone.label || undefined,
          target_type: editingZone.targetType,
          target_id: Number(editingZone.targetId),
          stroke_color: editingZone.strokeColor,
        })
      ).unwrap();

      toast.success('Зона обновлена');
      setEditingZone(null);
      setSelectedZoneId(null);
      dispatch(fetchClickableZones({ parentType, parentId }));
    } catch {
      toast.error('Ошибка обновления зоны');
    }
  };

  const handleCancelEdit = () => {
    setEditingZone(null);
    setSelectedZoneId(null);
  };

  const handleDeleteZone = async (zoneId: number) => {
    if (!window.confirm('Удалить эту зону?')) return;

    try {
      await dispatch(deleteClickableZone(zoneId)).unwrap();
      toast.success('Зона удалена');
      if (selectedZoneId === zoneId) {
        setSelectedZoneId(null);
        setEditingZone(null);
      }
      dispatch(fetchClickableZones({ parentType, parentId }));
    } catch {
      toast.error('Ошибка удаления зоны');
    }
  };

  // --- Mode switching ---

  const switchMode = (mode: DrawingMode) => {
    if (mode === drawingMode) return;
    // Clear any in-progress drawing
    setDragState(null);
    setIsDragging(false);
    clearPolygonDrawing();
    setDrawingMode(mode);
  };

  // --- Render helpers ---

  const getZoneSvgPath = (zoneData: ZonePoint[]): string => {
    if (zoneData.length < 2) return '';
    const first = zoneData[0];
    let d = `M ${first.x} ${first.y}`;
    for (let i = 1; i < zoneData.length; i++) {
      d += ` L ${zoneData[i].x} ${zoneData[i].y}`;
    }
    d += ' Z';
    return d;
  };

  const getOptionsForTargetType = (tt: 'country' | 'region' | 'area'): TargetOption[] => {
    if (tt === 'area') return areaOptions || [];
    // 'country' or 'region' use the default targetOptions passed from parent
    return targetOptions;
  };

  const getTargetTypeLabel = (tt: 'country' | 'region' | 'area'): string => {
    if (tt === 'area') return 'Область';
    if (tt === 'country') return 'Страна';
    return 'Регион';
  };

  const getTargetName = (targetId: number): string => {
    // Search across all option sets
    const allOptions = [...targetOptions, ...(areaOptions || [])];
    const found = allOptions.find((t) => t.id === targetId);
    return found ? found.name : `#${targetId}`;
  };

  // Check if new zone form should show
  const showNewZoneForm =
    (drawingMode === 'rectangle' && dragState && !isDragging) ||
    (drawingMode === 'polygon' && polygonFinalized);

  // --- Render ---

  if (!mapImageUrl) {
    return (
      <div className="p-8 text-center text-[#8ab3d5]">
        <p className="mb-4">Загрузите изображение карты для этой области, чтобы использовать редактор зон.</p>
        {onClose && (
          <button
            className="px-4 py-2 bg-white/10 text-white border-none rounded cursor-pointer transition-colors hover:bg-white/20"
            onClick={onClose}
          >
            Закрыть
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="flex flex-col lg:flex-row gap-6">
      {/* Map + SVG overlay */}
      <div className="flex-1 min-w-0">
        <h3 className="text-[#a8c6df] uppercase mb-3 text-base font-medium">
          Редактор кликабельных зон
        </h3>

        {/* Drawing mode toggle */}
        <div className="flex gap-2 mb-3">
          <button
            className={`px-3 py-1.5 rounded text-sm font-medium border-none cursor-pointer transition-colors ${
              drawingMode === 'polygon'
                ? 'bg-site-blue text-white'
                : 'bg-white/10 text-[#8ab3d5] hover:bg-white/20'
            }`}
            onClick={() => switchMode('polygon')}
          >
            Полигон
          </button>
          <button
            className={`px-3 py-1.5 rounded text-sm font-medium border-none cursor-pointer transition-colors ${
              drawingMode === 'rectangle'
                ? 'bg-site-blue text-white'
                : 'bg-white/10 text-[#8ab3d5] hover:bg-white/20'
            }`}
            onClick={() => switchMode('rectangle')}
          >
            Прямоугольник
          </button>
        </div>

        <div
          ref={containerRef}
          className="relative border border-white/20 rounded-lg overflow-hidden cursor-crosshair"
        >
          <img
            src={mapImageUrl}
            alt="Карта"
            className="w-full h-auto block select-none pointer-events-none"
            draggable={false}
          />

          <svg
            ref={svgRef}
            className="absolute inset-0 w-full h-full"
            viewBox="0 0 100 100"
            preserveAspectRatio="none"
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onClick={handleSvgClick}
            onDoubleClick={handleSvgDoubleClick}
            onMouseLeave={() => {
              if (drawingMode === 'rectangle' && isDragging) handleMouseUp();
              if (drawingMode === 'polygon') setCursorPos(null);
            }}
          >
            {/* Existing zones */}
            {clickableZones.map((zone) => (
              <g key={zone.id}>
                <path
                  d={getZoneSvgPath(zone.zone_data)}
                  fill={selectedZoneId === zone.id ? 'rgba(118,166,189,0.4)' : 'rgba(240,217,92,0.2)'}
                  stroke={selectedZoneId === zone.id ? '#76a6bd' : (zone.stroke_color || '#f0d95c')}
                  strokeWidth="0.3"
                  className="cursor-pointer transition-colors"
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelectedZoneId(zone.id === selectedZoneId ? null : zone.id);
                  }}
                />
                {/* Zone label */}
                {zone.label && zone.zone_data.length >= 2 && (
                  <text
                    x={zone.zone_data.reduce((sum, p) => sum + p.x, 0) / zone.zone_data.length}
                    y={zone.zone_data.reduce((sum, p) => sum + p.y, 0) / zone.zone_data.length}
                    textAnchor="middle"
                    dominantBaseline="middle"
                    fill="white"
                    fontSize="2.5"
                    fontWeight="bold"
                    className="pointer-events-none select-none"
                    style={{ textShadow: '0 0 3px rgba(0,0,0,0.8)' }}
                  >
                    {zone.label}
                  </text>
                )}
              </g>
            ))}

            {/* Rectangle drawing preview */}
            {drawingMode === 'rectangle' && dragState && (
              <rect
                x={Math.min(dragState.startX, dragState.currentX)}
                y={Math.min(dragState.startY, dragState.currentY)}
                width={Math.abs(dragState.currentX - dragState.startX)}
                height={Math.abs(dragState.currentY - dragState.startY)}
                fill="rgba(118,166,189,0.3)"
                stroke="#76a6bd"
                strokeWidth="0.3"
                strokeDasharray="1"
              />
            )}

            {/* Polygon drawing preview */}
            {drawingMode === 'polygon' && polygonPoints.length > 0 && (
              <g>
                {/* Filled polygon preview (when finalized or has 3+ points) */}
                {polygonPoints.length >= 3 && (
                  <polygon
                    points={polygonPoints.map((p) => `${p.x},${p.y}`).join(' ')}
                    fill="rgba(118,166,189,0.3)"
                    stroke="#76a6bd"
                    strokeWidth="0.3"
                    strokeDasharray={polygonFinalized ? '0' : '1'}
                  />
                )}

                {/* Lines between points (when < 3 points, draw as lines) */}
                {polygonPoints.length < 3 && polygonPoints.length >= 2 && (
                  <polyline
                    points={polygonPoints.map((p) => `${p.x},${p.y}`).join(' ')}
                    fill="none"
                    stroke="#76a6bd"
                    strokeWidth="0.3"
                    strokeDasharray="1"
                  />
                )}

                {/* Follow-line from last point to cursor */}
                {!polygonFinalized && cursorPos && polygonPoints.length > 0 && (
                  <line
                    x1={polygonPoints[polygonPoints.length - 1].x}
                    y1={polygonPoints[polygonPoints.length - 1].y}
                    x2={cursorPos.x}
                    y2={cursorPos.y}
                    stroke="#76a6bd"
                    strokeWidth="0.2"
                    strokeDasharray="0.5"
                    opacity={0.7}
                  />
                )}

                {/* Vertex circles */}
                {polygonPoints.map((pt, i) => (
                  <circle
                    key={i}
                    cx={pt.x}
                    cy={pt.y}
                    r={i === 0 && polygonPoints.length >= 3 && !polygonFinalized ? 1.2 : 0.7}
                    fill={i === 0 ? '#f0d95c' : '#76a6bd'}
                    stroke="white"
                    strokeWidth="0.15"
                    className="pointer-events-none"
                  />
                ))}
              </g>
            )}
          </svg>
        </div>

        {/* Hint text */}
        <div className="flex items-center justify-between mt-2">
          <p className="text-xs text-[#8ab3d5]">
            {drawingMode === 'rectangle'
              ? 'Нажмите и перетащите на карте, чтобы нарисовать прямоугольную зону.'
              : 'Кликните для добавления точек. Клик на первую точку или кнопка «Завершить» для завершения.'}
          </p>

          {/* Polygon point count and controls during drawing */}
          {drawingMode === 'polygon' && polygonPoints.length > 0 && !polygonFinalized && (
            <div className="flex items-center gap-3 ml-3 flex-shrink-0">
              <span className="text-xs text-[#8ab3d5]">Точек: {polygonPoints.length}</span>
              <button
                className="text-xs text-[#8ab3d5] hover:text-white transition-colors cursor-pointer bg-transparent border-none underline"
                onClick={handleUndoLastPoint}
              >
                Убрать последнюю точку
              </button>
              {polygonPoints.length >= 3 && (
                <button
                  className="text-xs text-[#99ffaa] hover:text-white transition-colors cursor-pointer bg-transparent border-none underline"
                  onClick={finalizePolygon}
                >
                  Завершить полигон
                </button>
              )}
              <button
                className="text-xs text-[#ff9999] hover:text-white transition-colors cursor-pointer bg-transparent border-none underline"
                onClick={clearPolygonDrawing}
              >
                Отменить рисование
              </button>
            </div>
          )}
        </div>

        {/* New zone form (after drawing) */}
        {showNewZoneForm && (
          <div className="mt-4 p-4 bg-[rgba(22,37,49,0.85)] rounded-lg border border-white/10">
            <h4 className="text-[#a8c6df] mb-3 font-medium">Новая зона</h4>
            <div className="flex flex-col gap-3">
              <div className="flex flex-col sm:flex-row gap-3">
                <div className="flex-1">
                  <label className="block mb-1 text-[#8ab3d5] text-sm">Название (необязательно):</label>
                  <input
                    type="text"
                    value={newZoneLabel}
                    onChange={(e) => setNewZoneLabel(e.target.value)}
                    placeholder="Название зоны"
                    className="w-full p-2 bg-black/30 border border-white/10 rounded text-[#d4e6f3] text-sm transition-colors focus:border-site-blue/50 focus:outline-none"
                  />
                </div>
                <div className="w-full sm:w-auto">
                  <label className="block mb-1 text-[#8ab3d5] text-sm">Цвет обводки:</label>
                  <input
                    type="color"
                    value={newZoneColor}
                    onChange={(e) => setNewZoneColor(e.target.value)}
                    className="w-full sm:w-10 h-[38px] p-0.5 bg-black/30 border border-white/10 rounded cursor-pointer"
                  />
                </div>
              </div>
              <div>
                <label className="block mb-1 text-[#8ab3d5] text-sm">Тип цели:</label>
                <select
                  value={newZoneTargetType}
                  onChange={(e) => {
                    const tt = e.target.value as 'country' | 'region' | 'area';
                    setNewZoneTargetType(tt);
                    setNewZoneTargetId('');
                  }}
                  className="w-full p-2 bg-black/30 border border-white/10 rounded text-[#d4e6f3] text-sm transition-colors focus:border-site-blue/50 focus:outline-none"
                >
                  <option value="area">Область</option>
                  <option value="country">Страна</option>
                  <option value="region">Регион</option>
                </select>
              </div>
              <div>
                <label className="block mb-1 text-[#8ab3d5] text-sm">
                  Цель ({getTargetTypeLabel(newZoneTargetType)}):
                </label>
                <select
                  value={newZoneTargetId}
                  onChange={(e) => setNewZoneTargetId(e.target.value)}
                  className="w-full p-2 bg-black/30 border border-white/10 rounded text-[#d4e6f3] text-sm transition-colors focus:border-site-blue/50 focus:outline-none"
                >
                  <option value="">Выберите...</option>
                  {getOptionsForTargetType(newZoneTargetType).map((opt) => (
                    <option key={opt.id} value={opt.id}>
                      {opt.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="flex gap-3">
                <button
                  className="px-4 py-2 bg-site-blue text-white border-none rounded cursor-pointer text-sm font-medium transition-colors hover:bg-[#5d8fa8]"
                  onClick={handleSaveNewZone}
                >
                  Сохранить
                </button>
                <button
                  className="px-4 py-2 bg-white/10 text-white border-none rounded cursor-pointer text-sm transition-colors hover:bg-white/20"
                  onClick={handleCancelNewZone}
                >
                  Отмена
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Zone list panel */}
      <div className="w-full lg:w-[320px] flex-shrink-0">
        <h3 className="text-[#a8c6df] uppercase mb-3 text-base font-medium">
          Список зон ({clickableZones.length})
        </h3>

        {onClose && (
          <button
            className="w-full mb-3 px-4 py-2 bg-white/10 text-white border-none rounded cursor-pointer text-sm transition-colors hover:bg-white/20"
            onClick={onClose}
          >
            Закрыть редактор
          </button>
        )}

        {loading && <div className="text-[#8ab3d5] text-sm">Загрузка...</div>}

        <div className="flex flex-col gap-2 gold-scrollbar overflow-y-auto max-h-[500px]">
          {clickableZones.length === 0 && !loading && (
            <div className="text-[#8ab3d5] text-sm text-center py-4">
              Нет кликабельных зон. Нарисуйте зону на карте.
            </div>
          )}

          {clickableZones.map((zone) => (
            <div
              key={zone.id}
              className={`p-3 rounded border transition-colors cursor-pointer ${
                selectedZoneId === zone.id
                  ? 'bg-site-blue/20 border-site-blue/50'
                  : 'bg-black/20 border-white/10 hover:bg-white/[0.07]'
              }`}
              onClick={() => setSelectedZoneId(zone.id === selectedZoneId ? null : zone.id)}
            >
              <div className="flex justify-between items-start mb-1">
                <span className="text-white text-sm font-medium">
                  {zone.label || `Зона #${zone.id}`}
                </span>
                <span className="text-[#8ab3d5] text-xs">ID: {zone.id}</span>
              </div>
              <div className="text-[#8ab3d5] text-xs mb-2 flex items-center gap-2">
                <span>Цель: {getTargetName(zone.target_id)} (#{zone.target_id})</span>
                <span
                  className="inline-block w-3 h-3 rounded-sm border border-white/20 flex-shrink-0"
                  style={{ backgroundColor: zone.stroke_color || '#f0d95c' }}
                  title="Цвет обводки"
                />
              </div>

              {/* Editing form for this zone */}
              {editingZone && editingZone.zoneId === zone.id ? (
                <div className="mt-2 flex flex-col gap-2">
                  <div className="flex flex-col sm:flex-row gap-2">
                    <input
                      type="text"
                      value={editingZone.label}
                      onChange={(e) =>
                        setEditingZone((prev) => (prev ? { ...prev, label: e.target.value } : null))
                      }
                      placeholder="Название"
                      className="flex-1 p-1.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] text-xs transition-colors focus:border-site-blue/50 focus:outline-none"
                    />
                    <div className="flex items-center gap-1.5">
                      <span className="text-[#8ab3d5] text-xs whitespace-nowrap">Цвет:</span>
                      <input
                        type="color"
                        value={editingZone.strokeColor}
                        onChange={(e) =>
                          setEditingZone((prev) =>
                            prev ? { ...prev, strokeColor: e.target.value } : null
                          )
                        }
                        className="w-8 h-7 p-0.5 bg-black/30 border border-white/10 rounded cursor-pointer"
                      />
                    </div>
                  </div>
                  <select
                    value={editingZone.targetType}
                    onChange={(e) => {
                      const tt = e.target.value as 'country' | 'region' | 'area';
                      setEditingZone((prev) =>
                        prev ? { ...prev, targetType: tt, targetId: '' } : null
                      );
                    }}
                    className="w-full p-1.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] text-xs transition-colors focus:border-site-blue/50 focus:outline-none"
                  >
                    <option value="area">Область</option>
                    <option value="country">Страна</option>
                    <option value="region">Регион</option>
                  </select>
                  <select
                    value={editingZone.targetId}
                    onChange={(e) =>
                      setEditingZone((prev) =>
                        prev ? { ...prev, targetId: e.target.value } : null
                      )
                    }
                    className="w-full p-1.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] text-xs transition-colors focus:border-site-blue/50 focus:outline-none"
                  >
                    <option value="">Выберите...</option>
                    {getOptionsForTargetType(editingZone.targetType).map((opt) => (
                      <option key={opt.id} value={opt.id}>
                        {opt.name}
                      </option>
                    ))}
                  </select>
                  <div className="flex gap-2">
                    <button
                      className="px-2 py-1 bg-site-blue text-white border-none rounded cursor-pointer text-xs transition-colors hover:bg-[#5d8fa8]"
                      onClick={handleSaveEdit}
                    >
                      Сохранить
                    </button>
                    <button
                      className="px-2 py-1 bg-white/10 text-white border-none rounded cursor-pointer text-xs transition-colors hover:bg-white/20"
                      onClick={handleCancelEdit}
                    >
                      Отмена
                    </button>
                  </div>
                </div>
              ) : (
                <div className="flex gap-2 mt-1">
                  <button
                    className="px-2 py-1 bg-site-blue/20 text-site-blue border-none rounded cursor-pointer text-xs transition-colors hover:bg-site-blue/30"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleStartEdit(zone);
                    }}
                  >
                    Изменить
                  </button>
                  <button
                    className="px-2 py-1 bg-site-red/20 text-[#ff9999] border-none rounded cursor-pointer text-xs transition-colors hover:bg-site-red/30"
                    onClick={(e) => {
                      e.stopPropagation();
                      handleDeleteZone(zone.id);
                    }}
                  >
                    Удалить
                  </button>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default AdminClickableZoneEditor;
