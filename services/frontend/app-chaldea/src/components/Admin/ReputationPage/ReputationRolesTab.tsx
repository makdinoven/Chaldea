import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { X } from 'lucide-react';
import { fetchReputationNpcRoles, putReputationNpcRoles, type ReputationRoleWeight } from '../../../api/reputationAdmin';
import { apiErrorMessage } from '../../../api/errors';
import { NPC_ROLES, NPC_ROLE_LABELS } from '../../../constants/npc';
import { invalidateReputationRefs } from './useReputationRefs';

interface ReputationRolesTabProps {
  canEdit: boolean;
}

interface RoleRow {
  role: string;
  points: string;
}

const LABEL = 'text-white/50 text-xs font-medium uppercase tracking-[0.06em]';
const FALLBACK_ROLE = '*';
const POINTS_LIMIT = 1000;
const ROLE_RE = /^[a-z][a-z0-9_]{0,49}$/;
const INT_RE = /^-?\d*$/;

const roleLabel = (role: string): string =>
  role === FALLBACK_ROLE ? 'Любая другая роль (*)' : NPC_ROLE_LABELS[role] ?? role;

const sortRows = (rows: RoleRow[]): RoleRow[] =>
  [...rows].sort((a, b) => {
    if (a.role === FALLBACK_ROLE) return 1;
    if (b.role === FALLBACK_ROLE) return -1;
    return roleLabel(a.role).localeCompare(roleLabel(b.role), 'ru');
  });

/** «Роли НПС»: kill weight per NPC role (a single NPC can override it in its form). Saved as the whole set. */
const ReputationRolesTab = ({ canEdit }: ReputationRolesTabProps) => {
  const [rows, setRows] = useState<RoleRow[] | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [newRole, setNewRole] = useState('');
  const [customRole, setCustomRole] = useState('');

  const apply = (list: ReputationRoleWeight[]) =>
    setRows(sortRows(list.map((r) => ({ role: r.role, points: String(r.points) }))));

  useEffect(() => {
    let cancelled = false;
    fetchReputationNpcRoles()
      .then((list) => {
        if (!cancelled) apply(list);
      })
      .catch((e) => {
        if (cancelled) return;
        const msg = apiErrorMessage(e, 'Не удалось загрузить веса ролей НПС');
        setLoadError(msg);
        toast.error(msg);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (loadError && !rows) return <p className="text-site-red text-sm">{loadError}</p>;
  if (!rows) return <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />;

  const present = new Set(rows.map((r) => r.role));
  const freeRoles = NPC_ROLES.filter((r) => !present.has(r.value));

  const setPoints = (role: string, value: string) => {
    if (!INT_RE.test(value)) return;
    setRows((list) => (list ? list.map((r) => (r.role === role ? { ...r, points: value } : r)) : list));
  };

  const removeRole = (role: string) => setRows((list) => (list ? list.filter((r) => r.role !== role) : list));

  const addRole = () => {
    const role = (newRole === '__custom' ? customRole : newRole).trim();
    if (!ROLE_RE.test(role)) {
      toast.error('Код роли — латиница в нижнем регистре, цифры и «_», начинается с буквы');
      return;
    }
    if (present.has(role)) {
      toast.error('Такая роль уже есть в списке');
      return;
    }
    setRows((list) => sortRows([...(list ?? []), { role, points: '0' }]));
    setNewRole('');
    setCustomRole('');
  };

  const save = async () => {
    for (const r of rows) {
      const n = Number(r.points);
      if (r.points.trim() === '' || r.points === '-' || !Number.isInteger(n) || Math.abs(n) > POINTS_LIMIT) {
        toast.error(`«${roleLabel(r.role)}»: очки — целое число от −${POINTS_LIMIT} до ${POINTS_LIMIT}`);
        return;
      }
    }
    if (!present.has(FALLBACK_ROLE)) {
      toast.error('Строка «Любая другая роль (*)» обязательна');
      return;
    }
    setSaving(true);
    try {
      const saved = await putReputationNpcRoles(rows.map((r) => ({ role: r.role, points: Number(r.points) })));
      apply(saved);
      invalidateReputationRefs();
      toast.success('Веса ролей НПС сохранены');
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить веса ролей НПС'));
    } finally {
      setSaving(false);
    }
  };

  const disabled = !canEdit || saving;

  return (
    <div className="flex flex-col gap-5">
      {!canEdit && (
        <p className="text-white/50 text-sm">Только просмотр: менять веса может администратор (право reputation:settings).</p>
      )}
      <p className="text-white/50 text-sm">
        Сколько репутации получает каждый победитель за убийство мирного НПС этой роли в регионе НПС (отрицательное —
        потеря; у разбойников может быть положительным). У конкретного НПС вес можно переопределить в его карточке.
      </p>

      <section className="bg-site-bg rounded-card border border-white/[0.07] p-3 sm:p-4 flex flex-col divide-y divide-white/[0.06] min-w-0">
        {rows.map((r) => (
          <div key={r.role} className="flex items-center gap-3 py-2 min-w-0">
            <div className="flex-1 min-w-0">
              <div className="text-white text-sm truncate">{roleLabel(r.role)}</div>
              {r.role !== FALLBACK_ROLE && <div className="text-white/30 text-[11px] font-mono truncate">{r.role}</div>}
            </div>
            <input
              aria-label={`Очки для роли ${roleLabel(r.role)}`}
              className="input-underline w-20 sm:w-28 text-right"
              inputMode="numeric"
              value={r.points}
              disabled={disabled}
              onChange={(e) => setPoints(r.role, e.target.value)}
            />
            {canEdit && (
              r.role === FALLBACK_ROLE ? (
                <span className="w-6 shrink-0" />
              ) : (
                <button type="button" title="Убрать роль" aria-label="Убрать роль" disabled={saving}
                  onClick={() => removeRole(r.role)}
                  className="w-6 h-6 shrink-0 flex items-center justify-center text-white/40 hover:text-site-red transition-colors">
                  <X size={16} />
                </button>
              )
            )}
          </div>
        ))}
      </section>

      {canEdit && (
        <div className="flex flex-col sm:flex-row sm:items-end gap-3">
          <label className="flex flex-col gap-1 sm:w-64">
            <span className={LABEL}>Добавить роль</span>
            <select className="input-underline w-full" value={newRole} disabled={saving}
              onChange={(e) => setNewRole(e.target.value)}>
              <option value="" className="bg-site-dark text-white">Выберите роль</option>
              {freeRoles.map((r) => (
                <option key={r.value} value={r.value} className="bg-site-dark text-white">{r.label}</option>
              ))}
              <option value="__custom" className="bg-site-dark text-white">Другая (ввести код)</option>
            </select>
          </label>
          {newRole === '__custom' && (
            <label className="flex flex-col gap-1 sm:w-48">
              <span className={LABEL}>Код роли</span>
              <input className="input-underline w-full font-mono" maxLength={50} value={customRole}
                onChange={(e) => setCustomRole(e.target.value.toLowerCase())} />
            </label>
          )}
          <button type="button" className="btn-line w-full sm:w-auto !px-5 disabled:opacity-50"
            disabled={saving || !newRole} onClick={addRole}>
            Добавить
          </button>
        </div>
      )}

      {canEdit && (
        <div>
          <button type="button" className="btn-blue w-full sm:w-auto !px-8 disabled:opacity-50" disabled={saving}
            onClick={() => void save()}>
            {saving ? 'Сохранение...' : 'Сохранить'}
          </button>
        </div>
      )}
    </div>
  );
};

export default ReputationRolesTab;
