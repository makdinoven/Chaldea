interface PathWaypoint {
  x: number;
  y: number;
}

interface NeighborEdge {
  from_id: number;
  to_id: number;
  energy_cost: number;
  path_data: PathWaypoint[] | null;
}

interface ArrowEdge {
  location_id: number;
  arrow_id: number;
  energy_cost: number;
  path_data: PathWaypoint[] | null;
}

interface ArrowMapItem {
  id: number;
  name: string;
  type: string;
  target_region_id?: number | null;
  target_region_name?: string | null;
}

type EditorMode = 'draw' | 'edit' | 'delete' | 'arrow';

interface PathEditorToolbarProps {
  mode: EditorMode;
  onModeChange: (mode: EditorMode) => void;
  edges: NeighborEdge[];
  arrowEdges?: ArrowEdge[];
  selectedEdgeKey: string | null;
  onSelectEdge: (key: string | null) => void;
  locationNames: Record<number, string>;
  saving: boolean;
  onSave: () => void;
  onDelete: () => void;
  energyCost: number;
  onEnergyCostChange: (cost: number) => void;
  drawingActive: boolean;
  arrowItems?: ArrowMapItem[];
  onDeleteArrow?: (arrowId: number) => void;
}

const PathEditorToolbar = ({
  mode,
  onModeChange,
  edges,
  arrowEdges = [],
  selectedEdgeKey,
  onSelectEdge,
  locationNames,
  saving,
  onSave,
  onDelete,
  energyCost,
  onEnergyCostChange,
  drawingActive,
  arrowItems = [],
  onDeleteArrow,
}: PathEditorToolbarProps) => {
  const modeButtons: { key: EditorMode; label: string; icon: string }[] = [
    { key: 'draw', label: 'Рисовать', icon: '\u270F\uFE0F' },
    { key: 'edit', label: 'Редакт.', icon: '\u2699\uFE0F' },
    { key: 'delete', label: 'Удалить', icon: '\u{1F5D1}\uFE0F' },
    { key: 'arrow', label: 'Стрелка', icon: '\u27A4' },
  ];

  return (
    <div className="flex flex-col gap-3 p-3 w-full md:w-[260px] flex-shrink-0 border-b md:border-b-0 md:border-r border-white/10 overflow-y-auto gold-scrollbar max-h-[600px]">
      {/* Mode selection */}
      <div>
        <p className="text-xs text-white/50 uppercase tracking-wide mb-2">Режим</p>
        <div className="flex gap-1">
          {modeButtons.map((btn) => (
            <button
              key={btn.key}
              className={`flex-1 px-2 py-1.5 rounded text-xs transition-colors border ${
                mode === btn.key
                  ? 'bg-amber-600/40 text-amber-200 border-amber-500/50'
                  : 'bg-white/5 text-white/70 border-white/10 hover:bg-white/10'
              }`}
              onClick={() => onModeChange(btn.key)}
            >
              <span className="mr-1">{btn.icon}</span>
              {btn.label}
            </button>
          ))}
        </div>
      </div>

      {/* Energy cost (draw mode only) */}
      {mode === 'draw' && (
        <div>
          <p className="text-xs text-white/50 uppercase tracking-wide mb-1">Стоимость энергии</p>
          <input
            type="number"
            min={1}
            max={100}
            value={energyCost}
            onChange={(e) => onEnergyCostChange(Math.max(1, parseInt(e.target.value) || 1))}
            className="input-underline w-full text-sm"
          />
        </div>
      )}

      {/* Draw mode hint */}
      {mode === 'draw' && (
        <div className="text-xs text-white/40 leading-relaxed">
          {drawingActive
            ? 'Кликайте на карту для добавления точек. Кликните на локацию/зону для завершения пути.'
            : 'Кликните на начальную локацию или зону для начала рисования пути.'}
        </div>
      )}

      {/* Edit mode hint */}
      {mode === 'edit' && !selectedEdgeKey && (
        <div className="text-xs text-white/40 leading-relaxed">
          Кликните на путь для выбора. Затем перетаскивайте точки или добавляйте новые двойным кликом.
        </div>
      )}

      {/* Delete mode hint */}
      {mode === 'delete' && (
        <div className="text-xs text-white/40 leading-relaxed">
          Кликните на путь для удаления связи между локациями.
        </div>
      )}

      {/* Arrow mode hint */}
      {mode === 'arrow' && (
        <div className="text-xs text-white/40 leading-relaxed">
          Кликните на пустое место на карте, чтобы разместить стрелку перехода в другой регион.
        </div>
      )}

      {/* Arrow items list */}
      {arrowItems.length > 0 && (
        <div>
          <p className="text-xs text-white/50 uppercase tracking-wide mb-2">
            Стрелки ({arrowItems.length})
          </p>
          <div className="flex flex-col gap-1 max-h-[150px] overflow-y-auto gold-scrollbar">
            {arrowItems.map((arrow) => (
              <div
                key={`arrow-${arrow.id}`}
                className="flex items-center justify-between px-2 py-1.5 rounded text-xs bg-cyan-900/20 text-cyan-200 border border-cyan-500/20"
              >
                <div className="min-w-0">
                  <span className="block truncate">{arrow.name}</span>
                  {arrow.target_region_name && (
                    <span className="text-[10px] text-white/40">
                      {'\u27A4'} {arrow.target_region_name}
                    </span>
                  )}
                </div>
                {onDeleteArrow && (
                  <button
                    className="shrink-0 ml-2 text-red-400 hover:text-red-300 transition-colors"
                    onClick={() => onDeleteArrow(arrow.id)}
                    title="Удалить стрелку"
                  >
                    {'\u2715'}
                  </button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Arrow edges list */}
      {arrowEdges.length > 0 && (
        <div>
          <p className="text-xs text-white/50 uppercase tracking-wide mb-2">
            Пути к стрелкам ({arrowEdges.length})
          </p>
          <div className="flex flex-col gap-1 max-h-[150px] overflow-y-auto gold-scrollbar">
            {arrowEdges.map((edge) => {
              const locName = locationNames[edge.location_id] || `#${edge.location_id}`;
              const arrowName = locationNames[edge.arrow_id] || `Стрелка #${edge.arrow_id}`;
              const key = `arrow-${edge.location_id}-${edge.arrow_id}`;
              const isSelected = selectedEdgeKey === key;

              return (
                <button
                  key={key}
                  className={`text-left px-2 py-1.5 rounded text-xs transition-colors border ${
                    isSelected
                      ? 'bg-cyan-600/30 text-cyan-200 border-cyan-500/40'
                      : 'bg-white/5 text-white/70 border-transparent hover:bg-white/10'
                  }`}
                  onClick={() => onSelectEdge(isSelected ? null : key)}
                >
                  <span className="block truncate">{locName} &rarr; {arrowName}</span>
                  <span className="text-[10px] text-white/40">
                    {'\u27A4'} стрелка
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Path list */}
      <div>
        <p className="text-xs text-white/50 uppercase tracking-wide mb-2">
          Пути ({edges.length})
        </p>
        <div className="flex flex-col gap-1 max-h-[300px] overflow-y-auto gold-scrollbar">
          {edges.length === 0 && (
            <p className="text-xs text-white/30 italic">Нет путей</p>
          )}
          {edges.map((edge) => {
            const key = `${edge.from_id}-${edge.to_id}`;
            const fromName = locationNames[edge.from_id] || `#${edge.from_id}`;
            const toName = locationNames[edge.to_id] || `#${edge.to_id}`;
            const isSelected = selectedEdgeKey === key;
            const hasCustomPath = edge.path_data && edge.path_data.length > 0;

            return (
              <button
                key={key}
                className={`text-left px-2 py-1.5 rounded text-xs transition-colors border ${
                  isSelected
                    ? 'bg-amber-600/30 text-amber-200 border-amber-500/40'
                    : 'bg-white/5 text-white/70 border-transparent hover:bg-white/10'
                }`}
                onClick={() => onSelectEdge(isSelected ? null : key)}
              >
                <span className="block truncate">{fromName} &rarr; {toName}</span>
                <span className="text-[10px] text-white/40">
                  {'\u26A1'} {edge.energy_cost}
                  {hasCustomPath ? ` \u00B7 ${edge.path_data!.length} точ.` : ' \u00B7 прямой'}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Action buttons */}
      {mode === 'edit' && selectedEdgeKey && (
        <button
          className="btn-blue text-xs py-1.5 w-full"
          onClick={onSave}
          disabled={saving}
        >
          {saving ? 'Сохранение...' : 'Сохранить изменения'}
        </button>
      )}

      {mode === 'delete' && selectedEdgeKey && (
        <button
          className="px-3 py-1.5 bg-red-600/30 text-red-300 border border-red-500/30 rounded text-xs transition-colors hover:bg-red-600/50 w-full"
          onClick={onDelete}
          disabled={saving}
        >
          {saving ? 'Удаление...' : 'Удалить выбранный путь'}
        </button>
      )}
    </div>
  );
};

export default PathEditorToolbar;
