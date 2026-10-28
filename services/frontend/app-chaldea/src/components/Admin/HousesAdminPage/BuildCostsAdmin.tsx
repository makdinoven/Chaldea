import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { Pencil } from 'lucide-react';
import {
  findCost,
  getBuildCosts,
  ROOM_LEVELS,
  ROOM_TYPE_LABEL,
  ROOM_TYPES,
  type BuildCost,
  type RoomType,
} from '../../../api/houses';
import { apiErrorMessage } from '../../../api/errors';
import { CostView, levelPerk, ROOM_TYPE_ICON } from '../../pages/HousesPage/building';
import BuildCostModal from './BuildCostModal';

interface BuildCostsAdminProps {
  canUpdate: boolean;
}

/** Admin: price of every build step — every room type × levels 1..3 (FEAT-180 stages 2 and 6a). */
const BuildCostsAdmin = ({ canUpdate }: BuildCostsAdminProps) => {
  const [costs, setCosts] = useState<BuildCost[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<{ roomType: RoomType; level: number } | null>(null);

  const load = useCallback(() => {
    getBuildCosts()
      .then((c) => {
        setCosts(c);
        setError(null);
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить стоимость стройки');
        setError(msg);
        toast.error(msg);
      });
  }, []);

  useEffect(load, [load]);

  if (error) return <p className="text-site-red text-sm">{error}</p>;
  if (!costs) return <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />;

  return (
    <div className="flex flex-col gap-4">
      <p className="text-white/60 text-sm max-w-3xl">
        Уровень 1 — постройка новой комнаты (на пустом участке или на свободном месте), 2 и 3 — улучшения.
        Без заданной стоимости ступень недоступна игрокам.
      </p>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {ROOM_TYPES.map((type) => {
          const Icon = ROOM_TYPE_ICON[type];
          return (
          <section key={type} className="bg-site-bg backdrop-blur-sm rounded-card border border-white/[0.07] p-3 sm:p-4 flex flex-col gap-2">
            <h2 className="gold-text text-sm font-medium uppercase tracking-[0.08em] flex items-center gap-2">
              <Icon size={15} className="text-gold shrink-0" />{ROOM_TYPE_LABEL[type]}
            </h2>
            {ROOM_LEVELS.map((level) => {
              const cost = findCost(costs, type, level);
              return (
                <div key={level} className="flex items-start gap-3 py-2 border-t border-white/[0.06] first:border-t-0">
                  <span className="text-white/70 text-xs w-14 shrink-0 pt-0.5" title={levelPerk(type, level) ?? undefined}>Ур. {level}</span>
                  <div className="flex-1 min-w-0">
                    {cost ? <CostView cost={cost} /> : <span className="text-white/35 text-xs italic">Не задано</span>}
                  </div>
                  {canUpdate && (
                    <button type="button" title="Изменить" onClick={() => setEditing({ roomType: type, level })}
                      className="w-8 h-8 flex items-center justify-center rounded-[8px] text-white/50 hover:text-gold transition-colors shrink-0">
                      <Pencil size={15} />
                    </button>
                  )}
                </div>
              );
            })}
          </section>
          );
        })}
      </div>

      {editing && (
        <BuildCostModal
          roomType={editing.roomType}
          level={editing.level}
          cost={findCost(costs, editing.roomType, editing.level)}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}
    </div>
  );
};

export default BuildCostsAdmin;
