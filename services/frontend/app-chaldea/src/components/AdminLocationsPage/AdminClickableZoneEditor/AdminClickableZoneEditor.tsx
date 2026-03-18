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
}

// --- Component ---

const AdminClickableZoneEditor = ({
  parentType,
  parentId,
  mapImageUrl,
  targetOptions,
  targetType,
  onClose,
}: AdminClickableZoneEditorProps) => {
  const dispatch = useAppDispatch();
  const { clickableZones, loading } = useAppSelector((state) => state.adminLocations);

  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const [dragState, setDragState] = useState<DragState | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [selectedZoneId, setSelectedZoneId] = useState<number | null>(null);

  // New zone form
  const [newZoneLabel, setNewZoneLabel] = useState('');
  const [newZoneTargetId, setNewZoneTargetId] = useState('');

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

  // --- Drawing handlers ---

  const handleMouseDown = (e: React.MouseEvent<SVGSVGElement>) => {
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
    if (!isDragging || !dragState) return;
    const coords = getPercentCoords(e.clientX, e.clientY);
    setDragState((prev) =>
      prev ? { ...prev, currentX: coords.x, currentY: coords.y } : null
    );
  };

  const handleMouseUp = () => {
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

  const handleSaveNewZone = async () => {
    if (!dragState) return;

    if (!newZoneTargetId) {
      toast.error('Выберите целевой объект для зоны');
      return;
    }

    const x1 = Math.min(dragState.startX, dragState.currentX);
    const y1 = Math.min(dragState.startY, dragState.currentY);
    const x2 = Math.max(dragState.startX, dragState.currentX);
    const y2 = Math.max(dragState.startY, dragState.currentY);

    const zoneData: ZonePoint[] = [
      { x: x1, y: y1 },
      { x: x2, y: y1 },
      { x: x2, y: y2 },
      { x: x1, y: y2 },
    ];

    try {
      await dispatch(
        createClickableZone({
          parent_type: parentType,
          parent_id: parentId,
          target_type: targetType,
          target_id: Number(newZoneTargetId),
          zone_data: zoneData,
          label: newZoneLabel || undefined,
        })
      ).unwrap();

      toast.success('Зона создана');
      setDragState(null);
      setNewZoneLabel('');
      setNewZoneTargetId('');
      dispatch(fetchClickableZones({ parentType, parentId }));
    } catch {
      toast.error('Ошибка создания зоны');
    }
  };

  const handleCancelNewZone = () => {
    setDragState(null);
    setNewZoneLabel('');
    setNewZoneTargetId('');
  };

  // --- Edit/Delete zone ---

  const handleStartEdit = (zone: ClickableZone) => {
    setEditingZone({
      zoneId: zone.id,
      label: zone.label || '',
      targetId: String(zone.target_id),
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
          target_type: targetType,
          target_id: Number(editingZone.targetId),
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

  const getTargetName = (targetId: number): string => {
    const found = targetOptions.find((t) => t.id === targetId);
    return found ? found.name : `#${targetId}`;
  };

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
            onMouseLeave={() => {
              if (isDragging) handleMouseUp();
            }}
          >
            {/* Existing zones */}
            {clickableZones.map((zone) => (
              <g key={zone.id}>
                <path
                  d={getZoneSvgPath(zone.zone_data)}
                  fill={selectedZoneId === zone.id ? 'rgba(118,166,189,0.4)' : 'rgba(240,217,92,0.2)'}
                  stroke={selectedZoneId === zone.id ? '#76a6bd' : '#f0d95c'}
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

            {/* Drawing preview */}
            {dragState && (
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
          </svg>
        </div>

        <p className="text-xs text-[#8ab3d5] mt-2">
          Нажмите и перетащите на карте, чтобы нарисовать прямоугольную зону.
        </p>

        {/* New zone form (after drawing) */}
        {dragState && !isDragging && (
          <div className="mt-4 p-4 bg-[rgba(22,37,49,0.85)] rounded-lg border border-white/10">
            <h4 className="text-[#a8c6df] mb-3 font-medium">Новая зона</h4>
            <div className="flex flex-col gap-3">
              <div>
                <label className="block mb-1 text-[#8ab3d5] text-sm">Название (необязательно):</label>
                <input
                  type="text"
                  value={newZoneLabel}
                  onChange={(e) => setNewZoneLabel(e.target.value)}
                  placeholder="Название зоны"
                  className="w-full p-2 bg-black/30 border border-white/10 rounded text-[#d4e6f3] text-sm transition-colors focus:border-site-blue/50 focus:outline-none"
                />
              </div>
              <div>
                <label className="block mb-1 text-[#8ab3d5] text-sm">
                  Цель ({targetType === 'country' ? 'Страна' : 'Регион'}):
                </label>
                <select
                  value={newZoneTargetId}
                  onChange={(e) => setNewZoneTargetId(e.target.value)}
                  className="w-full p-2 bg-black/30 border border-white/10 rounded text-[#d4e6f3] text-sm transition-colors focus:border-site-blue/50 focus:outline-none"
                >
                  <option value="">Выберите...</option>
                  {targetOptions.map((opt) => (
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
              <div className="text-[#8ab3d5] text-xs mb-2">
                Цель: {getTargetName(zone.target_id)} (#{zone.target_id})
              </div>

              {/* Editing form for this zone */}
              {editingZone && editingZone.zoneId === zone.id ? (
                <div className="mt-2 flex flex-col gap-2">
                  <input
                    type="text"
                    value={editingZone.label}
                    onChange={(e) =>
                      setEditingZone((prev) => (prev ? { ...prev, label: e.target.value } : null))
                    }
                    placeholder="Название"
                    className="w-full p-1.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] text-xs transition-colors focus:border-site-blue/50 focus:outline-none"
                  />
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
                    {targetOptions.map((opt) => (
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
