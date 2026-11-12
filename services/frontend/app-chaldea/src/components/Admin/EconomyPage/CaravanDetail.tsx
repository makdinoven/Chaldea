import { useCallback, useEffect, useState, type ReactNode } from 'react';
import toast from 'react-hot-toast';
import { fetchCaravanDetail } from '../../../api/economyAdmin';
import { apiErrorMessage } from '../../../api/errors';
import RemainingText from '../../CommonComponents/RemainingText';
import type { CaravanDetail as CaravanDetailData, CaravanRaidStatus } from '../../../types/economy';
import { formatDateTime, formatDecimal, formatQty } from './economyLabels';

/* FEAT-211 — expanded caravan row of the admin list (A5): route with the current position, hold, raid. */

export const RAID_STATUS_LABEL: Record<CaravanRaidStatus, string> = {
  starting: 'собирается',
  fighting: 'идёт бой',
  won: 'ограблен',
  repelled: 'отбился',
  aborted: 'бой прерван',
  expired: 'налёт сорвался',
};

export const RAID_STATUS_CLS: Record<CaravanRaidStatus, string> = {
  starting: 'border-gold/40 bg-gold/10 text-gold',
  fighting: 'border-orange-400/50 bg-orange-400/10 text-orange-300',
  won: 'border-site-red/50 bg-site-red/10 text-site-red',
  repelled: 'border-stat-energy/40 bg-stat-energy/10 text-stat-energy',
  aborted: 'border-white/20 text-white/50',
  expired: 'border-white/20 text-white/50',
};

export const RaidBadge = ({ status }: { status: CaravanRaidStatus }) => (
  <span
    className={`inline-flex rounded-full border px-2 py-0.5 text-[11px] whitespace-nowrap ${
      RAID_STATUS_CLS[status] ?? 'border-white/20 text-white/50'
    }`}
  >
    налёт: {RAID_STATUS_LABEL[status] ?? status}
  </span>
);

/** FEAT-212 — escort row statuses (A5). */
const ESCORT_STATUS_LABEL: Record<string, string> = {
  active: 'в охране',
  left: 'сошёл',
  fallen: 'выбыл в налёте',
  delivered: 'доставил',
  cancelled: 'караван отменён',
  released: 'снят с охраны',
};

const ESCORT_STATUS_CLS: Record<string, string> = {
  active: 'text-site-blue',
  left: 'text-white/50',
  fallen: 'text-site-red',
  delivered: 'text-stat-energy',
  cancelled: 'text-white/50',
  released: 'text-white/50',
};

const HELD_LABEL: Record<'post' | 'raid', string> = {
  post: 'ждёт: в локации открыт боевой пост на налёт',
  raid: 'стоит: на него напали',
};

const Line = ({ label, children }: { label: string; children: ReactNode }) => (
  <span className="text-xs text-white/60 break-words">
    {label}: <span className="text-white">{children}</span>
  </span>
);

interface CaravanDetailProps {
  caravanId: number;
  format: (n: number) => string;
}

const CaravanDetail = ({ caravanId, format }: CaravanDetailProps) => {
  const [data, setData] = useState<CaravanDetailData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    fetchCaravanDetail(caravanId)
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить караван');
        setError(msg);
        toast.error(msg);
      })
      .finally(() => setLoading(false));
  }, [caravanId]);

  useEffect(load, [load]);

  if (loading && !data) {
    return <div className="w-6 h-6 border-4 border-white/30 border-t-gold rounded-full animate-spin" />;
  }
  if (!data) {
    return (
      <div className="flex flex-col items-start gap-2">
        <p className="text-site-red text-sm">{error ?? 'Не удалось загрузить караван'}</p>
        <button type="button" className="btn-line !text-sm" onClick={load}>
          Повторить
        </button>
      </div>
    );
  }

  const raid = data.raid;
  const routeIndex = data.route_index ?? 0;
  const inTransit = data.status === 'in_transit';

  return (
    <div className="flex flex-col gap-4 min-w-0 border-t border-white/10 pt-3">
      {!data.is_physical ? (
        <p className="text-white/50 text-xs">Абстрактный караван — едет без маршрута, по пересчётам.</p>
      ) : (
        <>
          <div className="flex flex-col gap-1.5">
            <span className="text-white/60 text-[11px] uppercase tracking-[0.06em]">Маршрут</span>
            {data.route.length === 0 ? (
              <p className="text-white/40 text-xs">Маршрут не сохранён.</p>
            ) : (
              <ol className="flex flex-wrap items-center gap-1">
                {data.route.map((p, i) => {
                  const current = p.index === routeIndex;
                  const passed = p.index < routeIndex;
                  return (
                    <li key={`${p.index}-${p.location_id}`} className="flex items-center gap-1 min-w-0">
                      <span
                        title={p.region_name ?? undefined}
                        className={`rounded-full border px-2 py-0.5 text-[11px] break-words ${
                          current
                            ? 'border-gold/70 bg-gold/15 text-gold font-medium'
                            : passed
                              ? 'border-white/10 text-white/35'
                              : 'border-white/15 text-white/70'
                        }`}
                      >
                        {p.name ?? `Локация #${p.location_id}`}
                        {(i === 0 || i === data.route.length - 1) && p.region_name && (
                          <span className="text-white/40"> · {p.region_name}</span>
                        )}
                      </span>
                      {i < data.route.length - 1 && <span className="text-gold/50 text-xs">→</span>}
                    </li>
                  );
                })}
              </ol>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-1">
            <Line label="Сейчас">
              {data.current_location_name ?? (data.current_location_id ? `#${data.current_location_id}` : '—')} (
              {routeIndex + 1} из {data.route_len ?? data.route.length})
            </Line>
            <Line label="Охрана">{data.guard_count ?? 0}</Line>
            {inTransit && !data.arrived_at && data.next_move_at && (
              <Line label="Следующий переход">
                <RemainingText until={data.next_move_at} prefix="через" doneText="ждёт фонового шага" />
              </Line>
            )}
            {data.arrived_at && <Line label="Прибыл">{formatDateTime(data.arrived_at)}</Line>}
            {data.held_by && <Line label="Удержание">{HELD_LABEL[data.held_by]}</Line>}
            {data.hold_started_at && <Line label="Окно ожидания начато">{formatDateTime(data.hold_started_at)}</Line>}
            {(data.stolen_units ?? 0) > 0 && (
              <Line label="Украдено">
                {formatQty(data.stolen_units ?? 0)} ед., {format(data.raid_paid ?? 0)}
              </Line>
            )}
          </div>
        </>
      )}

      {(data.escorts?.length ?? 0) > 0 && (
        <div className="flex flex-col gap-1.5 min-w-0">
          <span className="text-white/60 text-[11px] uppercase tracking-[0.06em]">
            Охрана из игроков ({data.escorts?.length ?? 0})
          </span>
          <ul className="flex flex-col gap-1.5">
            {(data.escorts ?? []).map((e) => (
              <li
                key={e.character_id}
                className="flex flex-col sm:flex-row sm:flex-wrap sm:items-center gap-x-3 gap-y-0.5 rounded-card border border-white/10 bg-white/[0.03] px-2.5 py-1.5 text-xs min-w-0"
              >
                <span className="text-white break-words">{e.name ?? `#${e.character_id}`}</span>
                <span className={ESCORT_STATUS_CLS[e.status] ?? 'text-white/60'}>
                  {ESCORT_STATUS_LABEL[e.status] ?? e.status}
                </span>
                {e.in_raid && (
                  <span className="inline-flex self-start rounded-full border border-orange-400/50 bg-orange-400/10 px-2 py-0.5 text-[11px] text-orange-300 whitespace-nowrap">
                    в бою
                  </span>
                )}
                <span className="text-white/50">
                  с {formatDateTime(e.joined_at)}
                  {e.ended_at && ` по ${formatDateTime(e.ended_at)}`}
                </span>
                {(e.fee > 0 || e.bonus > 0) && (
                  <span className="text-white/60 sm:ml-auto">
                    плата <span className="text-white">{format(e.fee)}</span>
                    {e.bonus > 0 && (
                      <>
                        {' '}
                        + надбавка <span className="text-white">{format(e.bonus)}</span>
                      </>
                    )}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </div>
      )}

      {raid && (
        <div className="flex flex-col gap-2 rounded-card border border-site-red/20 bg-site-red/[0.04] p-3 min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <RaidBadge status={raid.status} />
            <span className="text-white/40 text-xs">
              налёт #{raid.id} · {formatDateTime(raid.created_at)}
              {raid.finished_at && ` — ${formatDateTime(raid.finished_at)}`}
            </span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-1">
            <Line label="Вожак">
              {raid.leader_name ?? `#${raid.leader_id}`}
              {raid.is_group ? ' (группой)' : ''}
            </Line>
            {raid.battle_id && <Line label="Бой">#{raid.battle_id}</Line>}
            <Line label="Стражи">
              {raid.guard_template_name ?? (raid.guard_template_id ? `шаблон #${raid.guard_template_id}` : '—')}
              {raid.guard_mult !== null && raid.guard_mult !== undefined && ` ×${formatDecimal(raid.guard_mult, 3)}`}
            </Line>
            {(raid.escort_ids?.length ?? 0) > 0 && (
              <Line label="Охранники-игроки в бою">{raid.escort_ids?.length ?? 0}</Line>
            )}
            <Line label="Добыча">
              {format(raid.marks)}, тюков {raid.bales}
            </Line>
            <Line label="Украдено товара">
              {formatQty(raid.stolen_units)} ед. на {format(raid.stolen_value)}
            </Line>
          </div>
          {raid.attackers.length > 0 && (
            <ul className="flex flex-col gap-1">
              {raid.attackers.map((a) => (
                <li key={a.id} className="text-xs text-white/70 break-words">
                  {a.name ?? `#${a.id}`}: <span className="text-white">{format(a.marks)}</span>, тюков{' '}
                  <span className="text-white">{a.bales}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
};

export default CaravanDetail;
