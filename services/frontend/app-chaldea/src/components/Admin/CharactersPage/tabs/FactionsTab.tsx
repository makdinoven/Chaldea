import { useCallback, useEffect, useState } from 'react';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import {
  FACTION_DELIVERY_KIND_LABEL,
  FACTION_DELIVERY_STATUS_LABEL,
  FACTION_MEMBER_STATUS_LABEL,
  adminFactionCharacter,
  adminRetryDelivery,
  type FactionAdminCharacter,
  type FactionDelivery,
} from '../../../../api/factions';
import { apiErrorMessage } from '../../../../api/errors';
import { formatServerDateTime } from '../../../../utils/serverDate';
import { useAppSelector } from '../../../../redux/store';
import { selectPermissions } from '../../../../redux/slices/userSlice';
import { hasPermission } from '../../../../utils/permissions';
import MemberActionModal, { type MemberActionTarget } from '../../FactionsPage/MemberActionModal';
import { DebtRow, PurchaseRow, usePurchaseActions } from '../../FactionsPage/FactionEconLists';

const payloadText = (d: FactionDelivery): string => {
  const p = d.payload ?? {};
  switch (d.kind) {
    case 'xp':
      return `${String(p.xp ?? '?')} опыта`;
    case 'title':
      return `титул #${String(p.title_id ?? '?')}`;
    case 'item':
      return `предмет #${String(p.item_id ?? '?')} × ${String(p.quantity ?? 1)}`;
    case 'voucher':
      return `${p.kind === 'empty' ? 'участок' : 'дом'} в локации #${String(p.location_id ?? '?')}`;
    default:
      return JSON.stringify(p);
  }
};

const statusClass = (s: string): string =>
  s === 'done' ? 'text-stat-energy' : s === 'failed' ? 'text-site-red' : 'text-gold-light';

/** Admin character card «Фракции» (FEAT-205): memberships (secret included), rank grants, reward deliveries. */
const FactionsTab = ({ characterId }: { characterId: number }) => {
  const permissions = useAppSelector(selectPermissions);
  const canManage = hasPermission(permissions, 'factions:manage');
  const canEconomy = hasPermission(permissions, 'factions:economy');
  const [data, setData] = useState<FactionAdminCharacter | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState<number | null>(null);
  const [action, setAction] = useState<MemberActionTarget | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      setData(await adminFactionCharacter(characterId));
    } catch (e) {
      setError(apiErrorMessage(e, 'Не удалось загрузить фракции персонажа'));
    }
  }, [characterId]);

  useEffect(() => {
    void load();
  }, [load]);

  const purchaseActions = usePurchaseActions(() => void load());
  const openDebt = (data?.debts ?? []).filter((d) => d.status === 'open').reduce((sum, d) => sum + d.amount - d.paid, 0);

  const retry = async (d: FactionDelivery) => {
    setRetrying(d.id);
    try {
      setData(await adminRetryDelivery(d.id));
      toast.success('Выдача запущена повторно');
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось повторить выдачу'));
    } finally {
      setRetrying(null);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.2 }}
      className="flex flex-col gap-6"
    >
      {error && (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-site-red text-sm">{error}</p>
          <button type="button" className="btn-line !w-auto !text-xs !py-1 !px-3" onClick={() => void load()}>
            Повторить
          </button>
        </div>
      )}
      {!data && !error && <div className="w-6 h-6 border-4 border-white/30 border-t-gold rounded-full animate-spin" />}

      {data && (
        <>
          <section className="gray-bg p-4 sm:p-6 flex flex-col gap-3 min-w-0">
            <h2 className="gold-text text-xl font-medium uppercase tracking-[0.06em]">Членство</h2>
            {data.memberships.length === 0 && <p className="text-white/50 text-sm">Персонаж не состоял во фракциях.</p>}
            {data.memberships.map((m) => (
              <div key={m.membership_id} className="flex flex-col sm:flex-row sm:items-center gap-2 bg-white/[0.03] rounded-card p-3">
                <div className="flex-1 min-w-0">
                  <p className="text-white text-sm break-words">
                    {m.faction?.name ?? `#${m.faction_id}`}
                    {m.faction?.is_secret && <span className="text-white/40 text-xs"> · тайная</span>}
                    {m.faction && !m.faction.is_active && <span className="text-white/40 text-xs"> · фракция скрыта из каталога</span>}
                  </p>
                  <p className="text-white/50 text-xs break-words">
                    {FACTION_MEMBER_STATUS_LABEL[m.status]} · {m.rank?.name ?? 'без звания'} · <span className="text-gold">{m.points} очк.</span>
                    {m.joined_at ? ` · вступил ${formatServerDateTime(m.joined_at)}` : ''}
                  </p>
                  {m.warning && (
                    <p className="text-site-red text-xs break-words">Предупреждение: {m.warning.reasons.join('; ')}</p>
                  )}
                </div>
                {canManage && m.status === 'active' && (
                  <div className="flex gap-4 shrink-0">
                    <button
                      type="button"
                      className="text-sm text-white hover:text-site-blue transition-colors"
                      onClick={() =>
                        setAction({ mode: 'points', membershipId: m.membership_id, characterName: data.character.name, factionName: m.faction?.name ?? '', points: m.points })
                      }
                    >
                      Очки ±
                    </button>
                    <button
                      type="button"
                      className="text-sm text-site-red hover:text-white transition-colors"
                      onClick={() =>
                        setAction({ mode: 'expel', membershipId: m.membership_id, characterName: data.character.name, factionName: m.faction?.name ?? '', points: m.points })
                      }
                    >
                      Исключить
                    </button>
                  </div>
                )}
              </div>
            ))}
          </section>

          <section className="gray-bg p-4 sm:p-6 flex flex-col gap-3 min-w-0">
            <h2 className="gold-text text-xl font-medium uppercase tracking-[0.06em]">Выдача наград за звания</h2>
            {data.grants.length > 0 && (
              <p className="text-white/50 text-xs break-words">
                Полученные звания: {data.grants.map((g) => `${g.rank_name ?? `#${g.rank_id}`} (${g.faction_name ?? `#${g.faction_id}`})`).join(', ')}
              </p>
            )}
            {data.deliveries.length === 0 && <p className="text-white/50 text-sm">Выдач нет.</p>}
            <div className="flex flex-col gap-2">
              {data.deliveries.map((d) => (
                <div key={d.id} className="flex flex-col sm:flex-row sm:items-center gap-2 bg-white/[0.03] rounded-card p-3">
                  <div className="flex-1 min-w-0">
                    <p className="text-white text-sm break-words">
                      {FACTION_DELIVERY_KIND_LABEL[d.kind] ?? d.kind}: {payloadText(d)}
                      {d.rank_name ? <span className="text-white/40"> · звание «{d.rank_name}»</span> : null}
                    </p>
                    <p className="text-white/50 text-xs break-words">
                      <span className={statusClass(d.status)}>{FACTION_DELIVERY_STATUS_LABEL[d.status] ?? d.status}</span>
                      {` · попыток ${d.attempts}`}
                      {d.last_error ? ` · ${d.last_error === 'uncertain' ? 'неясно, дошёл ли предмет — проверьте инвентарь перед повтором' : d.last_error}` : ''}
                      {d.updated_at ? ` · ${formatServerDateTime(d.updated_at)}` : ''}
                    </p>
                  </div>
                  {canManage && d.status === 'failed' && (
                    <button
                      type="button"
                      disabled={retrying !== null}
                      onClick={() => void retry(d)}
                      className="btn-line !w-full sm:!w-auto !text-xs !py-1.5 !px-4 shrink-0 disabled:opacity-50"
                    >
                      {retrying === d.id ? 'Повтор...' : 'Повторить'}
                    </button>
                  )}
                </div>
              ))}
            </div>
          </section>

          <section className="gray-bg p-4 sm:p-6 flex flex-col gap-3 min-w-0">
            <h2 className="gold-text text-xl font-medium uppercase tracking-[0.06em]">Долги фракций</h2>
            {(data.debts ?? []).length === 0 ? (
              <p className="text-white/50 text-sm">Фракции ничего не должны персонажу.</p>
            ) : (
              <>
                {openDebt > 0 && (
                  <p className="text-white/60 text-xs">
                    Не выплачено всего: <span className="text-gold">{openDebt.toLocaleString('ru-RU')}</span> — выплатят из казны
                    фракций по очереди.
                  </p>
                )}
                <div className="flex flex-col gap-2">
                  {(data.debts ?? []).map((d) => (
                    <DebtRow key={d.id} d={d} showFaction />
                  ))}
                </div>
              </>
            )}
          </section>

          <section className="gray-bg p-4 sm:p-6 flex flex-col gap-3 min-w-0">
            <h2 className="gold-text text-xl font-medium uppercase tracking-[0.06em]">Покупки у интендантов</h2>
            {(data.qm_purchases ?? []).length === 0 && <p className="text-white/50 text-sm">Покупок нет.</p>}
            <div className="flex flex-col gap-2">
              {(data.qm_purchases ?? []).map((p) => (
                <PurchaseRow
                  key={p.id}
                  p={p}
                  canAct={canEconomy}
                  busy={purchaseActions.busy}
                  onRetry={purchaseActions.onRetry}
                  onRefund={purchaseActions.onRefund}
                  showCharacter={false}
                />
              ))}
            </div>
            {purchaseActions.dialog}
          </section>

          <section className="gray-bg p-4 sm:p-6 flex flex-col gap-3 min-w-0">
            <h2 className="gold-text text-xl font-medium uppercase tracking-[0.06em]">Журнал</h2>
            {data.history.length === 0 && <p className="text-white/50 text-sm">Записей нет.</p>}
            <div className="flex flex-col gap-1.5">
              {data.history.map((h) => (
                <p key={h.id} className="text-white/80 text-sm break-words">
                  <span className="text-white/40 text-xs mr-2">{formatServerDateTime(h.created_at)}</span>
                  {h.text}
                </p>
              ))}
            </div>
          </section>
        </>
      )}

      <MemberActionModal
        target={action}
        onClose={() => setAction(null)}
        onDone={() => {
          setAction(null);
          void load();
        }}
      />
    </motion.div>
  );
};

export default FactionsTab;
