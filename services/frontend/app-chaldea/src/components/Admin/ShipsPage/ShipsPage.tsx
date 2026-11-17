import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { Anchor, ArrowLeft, RefreshCw, Trash2 } from 'lucide-react';
import { deleteSeaShip, fetchSeaPorts, fetchSeaShips, fetchSeaZones, seaAdminError } from '../../../api/seaAdmin';
import type { SeaPort, SeaShipAdmin, SeaZone } from '../../../types/seaAdmin';
import { useAppSelector } from '../../../redux/store';
import { hasPermission } from '../../../utils/permissions';
import { formatServerDateTime } from '../../../utils/serverDate';
import ConfirmDialog from '../../pages/LocationPage/ConfirmDialog';
import { ExpandableRow, ExpandedPanelShell } from '../ExpandableList';
import ShipForm from './ShipForm';
import SeaSettingsCard from './SeaSettingsCard';

type Tab = 'ships' | 'settings';

const TAB_LABEL: Record<Tab, string> = { ships: 'Корабли', settings: 'Настройки моря' };

const BLOCKED_LABEL: Record<string, string> = {
  no_path: 'Нет морского пути к следующему порту',
  no_valid_stop: 'В маршруте не осталось рабочих портов',
  no_deck: 'Палуба корабля удалена',
};

const TIME_OPTS: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' };

const GRID = 'sm:grid-cols-[minmax(0,1.6fr)_minmax(0,1.6fr)_minmax(0,1fr)_minmax(0,1.3fr)_auto]';

/** One-line state: docked / at sea / off. */
const stateText = (ship: SeaShipAdmin): string => {
  if (ship.status === 'sailing') {
    const zone = ship.current_zone
      ? `${ship.current_zone.name ?? '—'}${ship.current_zone.sea_name ? `, ${ship.current_zone.sea_name}` : ''}`
      : 'открытое море';
    return `В море: ${zone} → ${ship.next_port?.name ?? '—'}`;
  }
  return `У причала: ${ship.docked_port?.name ?? '—'}`;
};

const timeText = (ship: SeaShipAdmin): string | null => {
  if (!ship.is_active) return 'Не ходит (выключен)';
  if (ship.status === 'sailing') {
    return ship.arrives_at ? `прибытие ≈ ${formatServerDateTime(ship.arrives_at, TIME_OPTS)}` : null;
  }
  return ship.departs_at ? `отплытие ${formatServerDateTime(ship.departs_at, TIME_OPTS)}` : null;
};

const problemsOf = (ship: SeaShipAdmin): string[] => {
  const out: string[] = [];
  if (ship.blocked_reason) out.push(BLOCKED_LABEL[ship.blocked_reason] ?? `Корабль стоит: ${ship.blocked_reason}`);
  if (ship.captain_problem) out.push(ship.captain_problem);
  ship.legs
    .filter((l) => !l.ok || l.problem)
    .forEach((l) =>
      out.push(`Участок ${l.index + 1} (${l.from?.name ?? '—'} → ${l.to?.name ?? '—'}): ${l.problem_text ?? 'проблема пути'}`),
    );
  return out;
};

/** Admin: ships = deck locations moving between ports by sea zones (FEAT-213). */
const ShipsPage = () => {
  const permissions = useAppSelector((state) => state.user.permissions) as string[];
  const canCreate = hasPermission(permissions, 'locations:create');
  const canUpdate = hasPermission(permissions, 'locations:update');
  const canDelete = hasPermission(permissions, 'locations:delete');

  const [tab, setTab] = useState<Tab>('ships');
  const [ships, setShips] = useState<SeaShipAdmin[] | null>(null);
  const [ports, setPorts] = useState<SeaPort[]>([]);
  const [zones, setZones] = useState<SeaZone[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [geoError, setGeoError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<number | 'new' | null>(null);
  const [deleting, setDeleting] = useState<SeaShipAdmin | null>(null);
  const [loading, setLoading] = useState(false);
  const openRowRef = useRef<HTMLDivElement>(null);

  const load = useCallback(() => {
    setLoading(true);
    const shipsReq = fetchSeaShips()
      .then((rows) => {
        setShips(rows);
        setError(null);
      })
      .catch((e) => setError(seaAdminError(e, 'Не удалось загрузить корабли')));
    const geoReq = Promise.all([fetchSeaPorts(), fetchSeaZones()])
      .then(([p, z]) => {
        setPorts(p);
        setZones(z);
        setGeoError(null);
      })
      .catch((e) => setGeoError(seaAdminError(e, 'Не удалось загрузить порты и морские зоны')));
    void Promise.all([shipsReq, geoReq]).finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  const zonesById = useMemo(() => new Map(zones.map((z) => [z.id, z])), [zones]);

  const onSaved = (saved: SeaShipAdmin) => {
    setShips((prev) => {
      if (!prev) return [saved];
      return prev.some((s) => s.id === saved.id) ? prev.map((s) => (s.id === saved.id ? saved : s)) : [...prev, saved];
    });
    setOpenId(saved.id);
  };

  const remove = async (ship: SeaShipAdmin) => {
    setDeleting(null);
    try {
      await deleteSeaShip(ship.id);
      toast.success(`Корабль «${ship.name}» удалён`);
      setOpenId(null);
      setShips((prev) => prev?.filter((s) => s.id !== ship.id) ?? prev);
    } catch (e) {
      toast.error(seaAdminError(e, 'Не удалось удалить корабль'));
    }
  };

  return (
    <div className="w-full max-w-container mx-auto flex flex-col gap-5 pb-10">
      <Link to="/admin" className="self-start text-white/60 hover:text-white text-sm flex items-center gap-1">
        <ArrowLeft size={15} />
        Админ-панель
      </Link>
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div className="flex flex-col gap-1.5">
          <h1 className="gold-text text-2xl sm:text-3xl font-semibold uppercase tracking-[0.06em]">Корабли</h1>
          <p className="text-white/60 text-sm max-w-2xl">
            Корабль — это локация-палуба с НПС-капитаном. Он ходит между портами по морским зонам скрытой страны
            «Моря»: стоит в каждом порту время сборов, затем отплывает. Порты и морские зоны настраиваются в
            редакторе локаций.
          </p>
        </div>
        <div className="flex flex-col sm:flex-row gap-2 shrink-0">
          <button
            type="button"
            onClick={load}
            disabled={loading}
            className="btn-line !w-full sm:!w-auto flex items-center justify-center gap-2"
          >
            <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
            Обновить
          </button>
          {canCreate && tab === 'ships' && (
            <button type="button" onClick={() => setOpenId('new')} className="btn-blue !w-full sm:!w-auto !px-6">
              Новый корабль
            </button>
          )}
        </div>
      </div>

      <div className="flex gap-1 sm:gap-2 border-b border-white/10 overflow-x-auto gold-scrollbar">
        {(['ships', 'settings'] as Tab[]).map((t) => (
          <button
            key={t}
            type="button"
            onClick={() => setTab(t)}
            className={`px-3 sm:px-4 py-2 -mb-px border-b-2 text-sm uppercase tracking-[0.06em] whitespace-nowrap transition-colors ${
              t === tab ? 'border-gold text-gold' : 'border-transparent text-white/50 hover:text-white'
            }`}
          >
            {TAB_LABEL[t]}
          </button>
        ))}
      </div>

      {tab === 'settings' && <SeaSettingsCard canUpdate={canUpdate} />}

      {tab === 'ships' && (
        <>
          {geoError && <p className="text-site-red text-sm">{geoError}</p>}
          {error && <p className="text-site-red text-sm">{error}</p>}

          {openId === 'new' && canCreate && (
            <section className="bg-site-bg backdrop-blur-sm rounded-card gold-outline relative p-3 sm:p-5 flex flex-col gap-4">
              <h2 className="gold-text text-lg sm:text-xl font-medium uppercase tracking-[0.06em]">Новый корабль</h2>
              <ShipForm ports={ports} zones={zones} canSave={canCreate} onSaved={onSaved} onCancel={() => setOpenId(null)} />
            </section>
          )}

          {!ships && !error && <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />}
          {ships?.length === 0 && <p className="text-white/40 text-sm italic">Кораблей пока нет.</p>}

          {ships && ships.length > 0 && (
            <div className="bg-site-bg backdrop-blur-sm rounded-card border border-white/[0.07] flex flex-col p-1 sm:p-2 gap-1">
              <div className={`hidden sm:grid ${GRID} gap-4 px-4 py-2 text-white/40 text-[11px] uppercase tracking-[0.06em]`}>
                <span>Корабль</span>
                <span>Где сейчас</span>
                <span>На борту</span>
                <span>Проблемы</span>
                <span className="w-5" />
              </div>
              {ships.map((ship) => {
                const open = openId === ship.id;
                const problems = problemsOf(ship);
                const when = timeText(ship);
                return (
                  <ExpandableRow
                    key={ship.id}
                    open={open}
                    onToggle={() => setOpenId(open ? null : ship.id)}
                    rowRef={open ? openRowRef : undefined}
                    gridClassName={GRID}
                    avatar={
                      ship.captain?.avatar ? (
                        <img src={ship.captain.avatar} alt="" className="w-10 h-10 rounded-full object-cover shrink-0" />
                      ) : (
                        <span className="w-10 h-10 rounded-full bg-white/[0.07] flex items-center justify-center shrink-0">
                          <Anchor size={18} className="text-gold/80" />
                        </span>
                      )
                    }
                    title={ship.name}
                    subtitle={`#${ship.id} · ${ship.captain?.name ? `кап. ${ship.captain.name}` : 'без капитана'} · рейсов ${ship.trip_no}`}
                    cells={
                      <>
                        <span className="pl-[52px] sm:pl-0 flex flex-col min-w-0 text-sm">
                          <span className={`truncate ${ship.is_active ? 'text-white/85' : 'text-white/40'}`}>{stateText(ship)}</span>
                          {when && <span className="text-white/40 text-xs truncate">{when}</span>}
                        </span>
                        <span className="pl-[52px] sm:pl-0 text-white/70 text-xs sm:text-sm">
                          {ship.passengers_count} чел. · мест {ship.active_passes}/{ship.capacity + ship.crew_slots}
                        </span>
                        <span className="pl-[52px] sm:pl-0 text-xs min-w-0">
                          {problems.length ? (
                            <span className="text-site-red line-clamp-2">{problems[0]}{problems.length > 1 ? ` (+${problems.length - 1})` : ''}</span>
                          ) : (
                            <span className="text-stat-energy">нет</span>
                          )}
                        </span>
                      </>
                    }
                  >
                    <ExpandedPanelShell
                      title={ship.name}
                      bodyKey={`ship-${ship.id}-${ship.updated_at}`}
                      scrollTargetRef={openRowRef}
                      actions={
                        canDelete ? (
                          <button
                            type="button"
                            onClick={() => setDeleting(ship)}
                            className="flex items-center gap-1.5 text-sm text-white/60 hover:text-site-red transition-colors"
                          >
                            <Trash2 size={15} />
                            Удалить
                          </button>
                        ) : undefined
                      }
                    >
                      <div className="flex flex-col gap-5">
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
                          <div className="flex flex-col gap-1 rounded-card border border-white/[0.07] bg-white/[0.03] p-3">
                            <span className="text-white/85">{stateText(ship)}</span>
                            {when && <span className="text-white/50 text-xs">{when}</span>}
                            {ship.status === 'sailing' && ship.leg_path && ship.leg_path.length > 0 && (
                              <span className="text-white/50 text-xs break-words">
                                Путь участка:{' '}
                                {ship.leg_path.map((id, i) => (
                                  <span key={`${id}-${i}`} className={i === ship.leg_pos ? 'text-gold' : ''}>
                                    {i > 0 ? ' → ' : ''}
                                    {zonesById.get(id)?.name ?? `#${id}`}
                                  </span>
                                ))}
                                {ship.next_zone_at && ` · следующая зона ${formatServerDateTime(ship.next_zone_at, TIME_OPTS)}`}
                              </span>
                            )}
                            <span className="text-white/50 text-xs">
                              Палуба:{' '}
                              <Link to={`/location/${ship.deck.id}`} className="site-link">
                                {ship.deck.name ?? `#${ship.deck.id}`}
                              </Link>
                              {ship.captain && (
                                <>
                                  {' '}· капитан сейчас: {ship.captain.location_name ?? '—'}
                                </>
                              )}
                            </span>
                            <span className="text-white/50 text-xs">
                              На палубе {ship.passengers_count} чел. · действующих мест {ship.active_passes} · рейсов{' '}
                              {ship.trip_no}
                            </span>
                          </div>
                          <div className="flex flex-col gap-1 rounded-card border border-white/[0.07] bg-white/[0.03] p-3">
                            <span className="text-white/50 text-[11px] uppercase tracking-[0.06em]">Проблемы</span>
                            {problems.length ? (
                              problems.map((p) => (
                                <span key={p} className="text-site-red text-xs">
                                  {p}
                                </span>
                              ))
                            ) : (
                              <span className="text-stat-energy text-xs">Всё в порядке</span>
                            )}
                          </div>
                        </div>
                        <ShipForm
                          ship={ship}
                          ports={ports}
                          zones={zones}
                          canSave={canUpdate}
                          onSaved={onSaved}
                          onCancel={() => setOpenId(null)}
                        />
                      </div>
                    </ExpandedPanelShell>
                  </ExpandableRow>
                );
              })}
            </div>
          )}
        </>
      )}

      {deleting && (
        <ConfirmDialog
          title="Удалить корабль"
          message={`«${deleting.name}» будет удалён: пассажиров высадят на берег, неначатые билеты вернут. Корабль в море удалить нельзя — сначала выключите его и дождитесь швартовки. Локация палубы и НПС-капитан останутся.`}
          confirmLabel="Удалить"
          danger
          onCancel={() => setDeleting(null)}
          onConfirm={() => void remove(deleting)}
        />
      )}
    </div>
  );
};

export default ShipsPage;
