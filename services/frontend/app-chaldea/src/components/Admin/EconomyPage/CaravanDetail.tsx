import { useCallback, useEffect, useState, type ReactNode } from 'react';
import toast from 'react-hot-toast';
import { fetchCaravanDetail } from '../../../api/economyAdmin';
import { apiErrorMessage } from '../../../api/errors';
import RemainingText from '../../CommonComponents/RemainingText';
import type { CaravanDetail as CaravanDetailData, CaravanRaidStatus, CaravanRow } from '../../../types/economy';
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

/* ------------------------------------------------------------------ FEAT-215 sea caravans (feature file 3.10) */

/** A caravan that crosses the sea (the boarding port is set at dispatch and kept for history). */
export const isSeaCaravan = (c: CaravanRow): boolean => c.sea_board_port_id != null || !!c.sea_stage;

const portName = (name: string | null | undefined, id: number | null | undefined) =>
  name ?? (id != null ? `#${id}` : '—');

/** One-line Russian description of the sea stage of an in-transit caravan; null for a land caravan. */
export const seaStageText = (c: CaravanRow): string | null => {
  if (!isSeaCaravan(c)) return null;
  const board = portName(c.sea_board_port_name, c.sea_board_port_id);
  const alight = portName(c.sea_alight_port_name, c.sea_alight_port_id);
  const ship = c.sea_ship_name ?? (c.sea_ship_id != null ? `#${c.sea_ship_id}` : null);
  switch (c.sea_stage) {
    case 'to_port':
      return `едет в порт ${board}`;
    case 'waiting':
      return `ждёт корабль в порту ${board}`;
    case 'aboard':
      return `в трюме корабля${ship ? ` «${ship}»` : ''} → порт ${alight}`;
    case 'landed':
      return `сошёл в порту ${alight}, едет дальше по суше`;
    case 'stranded':
      return 'застрял: корабль потерян, ждёт отмены';
    default:
      return `по морю: ${board} → ${alight}`;
  }
};

const SEA_STAGE_CLS: Record<string, string> = {
  to_port: 'text-white/70',
  waiting: 'text-gold',
  aboard: 'text-site-blue',
  landed: 'text-stat-energy',
  stranded: 'text-site-red',
};

export const seaStageCls = (stage: string | null | undefined): string =>
  (stage && SEA_STAGE_CLS[stage]) || 'text-white/70';

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
  const sea = isSeaCaravan(data);
  const split = sea && data.sea_split_index != null ? data.sea_split_index : null;
  const aboard = inTransit && data.sea_stage === 'aboard';
  const freight = data.freight ?? 0;
  const freightPaid = data.freight_paid ?? 0;
  const sunk = data.sunk_units ?? 0;
  const losses = data.sea_losses ?? [];

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
                  // Aboard: the caravan is on the sea separator, the boarding port is already behind.
                  const current = !aboard && p.index === routeIndex;
                  const passed = p.index < routeIndex || (aboard && p.index === routeIndex);
                  const seaAfter = split !== null && p.index === split && i < data.route.length - 1;
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
                      {seaAfter ? (
                        <span
                          className={`rounded-full border px-2 py-0.5 text-[11px] whitespace-nowrap ${
                            aboard
                              ? 'border-site-blue/70 bg-site-blue/15 text-site-blue font-medium'
                              : 'border-site-blue/30 text-site-blue/80'
                          }`}
                        >
                          ⚓ море{aboard && data.sea_ship_name ? ` · «${data.sea_ship_name}»` : ''}
                        </span>
                      ) : (
                        i < data.route.length - 1 && <span className="text-gold/50 text-xs">→</span>
                      )}
                    </li>
                  );
                })}
              </ol>
            )}
          </div>

          {sea && (
            <div className="flex flex-col gap-1.5 rounded-card border border-site-blue/20 bg-site-blue/[0.04] p-3 min-w-0">
              <span className="text-white/60 text-[11px] uppercase tracking-[0.06em]">Морской путь</span>
              {inTransit && (
                <p className={`text-sm break-words ${seaStageCls(data.sea_stage)}`}>
                  {seaStageText(data)}
                  {data.sea_stage === 'waiting' && data.sea_wait_deadline && (
                    <span className="text-white/60">
                      {', '}
                      <RemainingText until={data.sea_wait_deadline} prefix="отмена через" doneText="срок ожидания вышел" />
                    </span>
                  )}
                </p>
              )}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-1">
                <Line label="Порт погрузки">{portName(data.sea_board_port_name, data.sea_board_port_id)}</Line>
                <Line label="Порт выгрузки">{portName(data.sea_alight_port_name, data.sea_alight_port_id)}</Line>
                {data.sea_ship_id != null && <Line label="Корабль">{data.sea_ship_name ?? `#${data.sea_ship_id}`}</Line>}
                {data.sea_waiting_since && <Line label="В порту с">{formatDateTime(data.sea_waiting_since)}</Line>}
                {data.sea_boarded_at && <Line label="Погружен">{formatDateTime(data.sea_boarded_at)}</Line>}
                {data.sea_unloaded_at && <Line label="Выгружен">{formatDateTime(data.sea_unloaded_at)}</Line>}
                <Line label="Фрахт">
                  {freight > 0 ? (
                    <>
                      {format(freight)}{' '}
                      <span className={freightPaid > 0 ? 'text-stat-energy' : 'text-white/50'}>
                        ({freightPaid > 0 ? `списан ${format(freightPaid)}` : 'в резерве'})
                      </span>
                    </>
                  ) : (
                    'нет'
                  )}
                </Line>
                {sunk > 0 && <Line label="Утонуло">{formatQty(sunk)} ед.</Line>}
              </div>
              {losses.length > 0 && (
                <ul className="flex flex-col gap-1">
                  {losses.map((l) => (
                    <li key={l.attack_key} className="text-xs text-white/70 break-words">
                      {formatDateTime(l.created_at)}: монстры утащили в пучину{' '}
                      <span className="text-site-red">{formatQty(l.units_lost)} ед.</span> ({formatDecimal(l.loss_pct)} %)
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-4 gap-y-1">
            <Line label="Сейчас">
              {data.current_location_name ?? (data.current_location_id ? `#${data.current_location_id}` : '—')} (
              {routeIndex + 1} из {data.route_len ?? data.route.length})
            </Line>
            <Line label="Охрана">{data.guard_count ?? 0}</Line>
            {inTransit && !data.arrived_at && data.next_move_at && !aboard && data.sea_stage !== 'waiting' && (
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
