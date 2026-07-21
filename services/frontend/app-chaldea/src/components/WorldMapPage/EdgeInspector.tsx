import { useEffect, useState } from 'react';
import type { GraphEdge, GraphLocation } from '../../api/worldGraph';
import { deleteNeighbor, editorErrorMessage, updateNeighborCost } from '../../api/mapEditor';

interface EdgeInspectorProps {
  edge: GraphEdge;
  locationById: Map<number, GraphLocation>;
  regionNames: Map<number, string>;
  canDelete: boolean;
  onCostChanged: (edge: GraphEdge, energyCost: number) => void;
  onDeleted: (edge: GraphEdge) => void;
  onClose: () => void;
  onFocusLocation: (locationId: number) => void;
}

const EdgeInspector = ({
  edge,
  locationById,
  regionNames,
  canDelete,
  onCostChanged,
  onDeleted,
  onClose,
  onFocusLocation,
}: EdgeInspectorProps) => {
  const currentCost = edge.cost_ab ?? edge.cost_ba ?? 1;
  const [cost, setCost] = useState(String(currentCost));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);

  useEffect(() => {
    setCost(String(edge.cost_ab ?? edge.cost_ba ?? 1));
    setError(null);
    setConfirmDelete(false);
  }, [edge]);

  const nameOf = (id: number) => locationById.get(id)?.name ?? `#${id}`;
  const regionOf = (id: number) => {
    const location = locationById.get(id);
    return location ? regionNames.get(location.region_id) ?? '—' : '—';
  };

  const oneWay = edge.cost_ab === null || edge.cost_ba === null;
  const parsed = Number(cost);
  const valid = Number.isInteger(parsed) && parsed >= 0 && parsed <= 1000;
  const dirty = valid && parsed !== currentCost;

  const save = async () => {
    if (!valid || busy) return;
    setBusy(true);
    setError(null);
    try {
      await updateNeighborCost(edge.a, edge.b, parsed);
      onCostChanged(edge, parsed);
    } catch (caught) {
      setError(editorErrorMessage(caught, 'Не удалось сохранить стоимость перехода.'));
    } finally {
      setBusy(false);
    }
  };

  const remove = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await deleteNeighbor(edge.a, edge.b);
      onDeleted(edge);
    } catch (caught) {
      setError(editorErrorMessage(caught, 'Не удалось удалить переход.'));
      setBusy(false);
    }
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <h2 className="gold-text text-[15px] font-semibold">Переход</h2>
        <button
          type="button"
          aria-label="Закрыть"
          className="text-white/40 transition-colors hover:text-site-red"
          onClick={onClose}
        >
          ✕
        </button>
      </div>

      <div className="gradient-line-border rounded-lg bg-black/35 p-3">
        {[edge.a, edge.b].map((id, position) => (
          <button
            key={id}
            type="button"
            className="flex w-full items-baseline gap-2 rounded px-1 py-1 text-left transition-colors hover:bg-white/5"
            onClick={() => onFocusLocation(id)}
          >
            <span className="w-4 shrink-0 text-[11px] text-white/30">{position === 0 ? 'A' : 'B'}</span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[13px] text-white/85">{nameOf(id)}</span>
              <span className="block truncate text-[10px] text-white/40">{regionOf(id)}</span>
            </span>
          </button>
        ))}
        {oneWay && (
          <p className="mt-2 text-[11px] leading-snug text-gold">
            Переход односторонний: в базе есть только одно направление.
            Сохранение стоимости изменит имеющиеся строки, не создавая обратную.
          </p>
        )}
        {edge.auto && (
          <p className="mt-2 text-[11px] leading-snug text-white/45">
            Связь создана автоматически из межрегиональной стрелки — правки может
            перезаписать пересинхронизация стрелок.
          </p>
        )}
      </div>

      <label className="flex flex-col gap-1">
        <span className="text-[10px] uppercase tracking-wide text-white/45">
          Стоимость перехода (выносливость)
        </span>
        <input
          type="number"
          min={0}
          max={1000}
          step={1}
          className="input-underline text-[14px]"
          value={cost}
          onChange={(event) => setCost(event.target.value)}
        />
        {!valid && (
          <span className="text-[11px] text-site-red">
            Введите целое число от 0 до 1000.
          </span>
        )}
      </label>

      {error && <p className="text-[12px] leading-snug text-site-red">{error}</p>}

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn-blue text-[12px] disabled:cursor-not-allowed disabled:opacity-40"
          disabled={!dirty || busy}
          onClick={save}
        >
          {busy ? 'Сохранение…' : 'Сохранить'}
        </button>
        {canDelete && (
          confirmDelete ? (
            <>
              <button
                type="button"
                className="rounded-lg border border-site-red/60 bg-site-red/15 px-2.5 py-1 text-[12px]
                           text-site-red transition-colors hover:bg-site-red/25 disabled:opacity-40"
                disabled={busy}
                onClick={remove}
              >
                Точно удалить
              </button>
              <button
                type="button"
                className="text-[12px] text-white/45 transition-colors hover:text-white/80"
                onClick={() => setConfirmDelete(false)}
              >
                Отмена
              </button>
            </>
          ) : (
            <button
              type="button"
              className="rounded-lg border border-site-red/40 px-2.5 py-1 text-[12px] text-site-red
                         transition-colors hover:bg-site-red/15"
              onClick={() => setConfirmDelete(true)}
            >
              Удалить переход
            </button>
          )
        )}
      </div>
    </div>
  );
};

export default EdgeInspector;
