import { useCallback, useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import {
  createReputationAction,
  deleteReputationAction,
  fetchReputationActions,
  updateReputationAction,
  type ReputationAction,
} from '../../../api/reputationAdmin';
import { apiErrorMessage } from '../../../api/errors';
import ConfirmDialog from '../../pages/LocationPage/ConfirmDialog';

interface ReputationActionsTabProps {
  canEdit: boolean;
}

interface RowForm {
  name: string;
  points: string;
  daily_cap: string;
  sort_order: string;
}

const LABEL = 'text-white/50 text-xs font-medium uppercase tracking-[0.06em]';
const POINTS_LIMIT = 1000;
const CODE_RE = /^[a-z][a-z0-9_]{2,39}$/;
const INT_RE = /^-?\d*$/;
const UINT_RE = /^\d*$/;

/** Actions whose weight is not taken from «Очки» (explained next to the row). */
const ACTION_NOTES: Record<string, string> = {
  npc_kill: 'Вес берётся из вкладки «Роли НПС» или из поля НПС «Репутация за убийство».',
  quest_complete: 'Вес по умолчанию; у задания можно задать свой в редакторе заданий.',
  admin_manual: 'Ручная правка числом — очки здесь не используются.',
};

const toRow = (a: ReputationAction): RowForm => ({
  name: a.name,
  points: String(a.points),
  daily_cap: a.daily_cap == null ? '' : String(a.daily_cap),
  sort_order: String(a.sort_order),
});

const rowError = (r: RowForm): string | null => {
  if (!r.name.trim()) return 'Название обязательно';
  if (r.name.trim().length > 100) return 'Название — не длиннее 100 символов';
  const p = Number(r.points);
  if (r.points.trim() === '' || r.points === '-' || !Number.isInteger(p) || Math.abs(p) > POINTS_LIMIT) {
    return `Очки — целое число от −${POINTS_LIMIT} до ${POINTS_LIMIT}`;
  }
  if (r.daily_cap.trim() !== '' && Number(r.daily_cap) < 1) return 'Дневной лимит — от 1 или пусто';
  return null;
};

/** «Действия»: weight table «действие → очки», daily caps, custom (future) actions. */
const ReputationActionsTab = ({ canEdit }: ReputationActionsTabProps) => {
  const [actions, setActions] = useState<ReputationAction[] | null>(null);
  const [rows, setRows] = useState<Record<string, RowForm>>({});
  const [loadError, setLoadError] = useState<string | null>(null);
  const [busyCode, setBusyCode] = useState<string | null>(null);
  const [toDelete, setToDelete] = useState<ReputationAction | null>(null);
  const [newForm, setNewForm] = useState<RowForm & { code: string }>({
    code: '',
    name: '',
    points: '0',
    daily_cap: '',
    sort_order: '',
  });
  const [creating, setCreating] = useState(false);

  const load = useCallback(() => {
    fetchReputationActions()
      .then((list) => {
        const sorted = [...list].sort((a, b) => a.sort_order - b.sort_order || a.code.localeCompare(b.code));
        setActions(sorted);
        setRows(Object.fromEntries(sorted.map((a) => [a.code, toRow(a)])));
        setLoadError(null);
      })
      .catch((e) => {
        const msg = apiErrorMessage(e, 'Не удалось загрузить действия репутации');
        setLoadError(msg);
        toast.error(msg);
      });
  }, []);

  useEffect(load, [load]);

  const setRow = (code: string, key: keyof RowForm, value: string) => {
    if (key === 'points' && !INT_RE.test(value)) return;
    if ((key === 'daily_cap' || key === 'sort_order') && !UINT_RE.test(value)) return;
    setRows((prev) => ({ ...prev, [code]: { ...prev[code], [key]: value } }));
  };

  const saveRow = async (a: ReputationAction) => {
    const r = rows[a.code];
    const err = rowError(r);
    if (err) {
      toast.error(err);
      return;
    }
    setBusyCode(a.code);
    try {
      await updateReputationAction(a.code, {
        name: r.name.trim(),
        points: Number(r.points),
        daily_cap: r.daily_cap.trim() === '' ? null : Number(r.daily_cap),
        sort_order: r.sort_order.trim() === '' ? null : Number(r.sort_order),
      });
      toast.success(`Действие «${r.name.trim()}» сохранено`);
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить действие'));
    } finally {
      setBusyCode(null);
    }
  };

  const removeAction = async (a: ReputationAction) => {
    setToDelete(null);
    setBusyCode(a.code);
    try {
      await deleteReputationAction(a.code);
      toast.success(`Действие «${a.name}» удалено`);
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось удалить действие'));
    } finally {
      setBusyCode(null);
    }
  };

  const create = async () => {
    const code = newForm.code.trim();
    if (!CODE_RE.test(code)) {
      toast.error('Код — латиница в нижнем регистре, цифры и «_», от 3 до 40 символов, начинается с буквы');
      return;
    }
    const err = rowError(newForm);
    if (err) {
      toast.error(err);
      return;
    }
    setCreating(true);
    try {
      await createReputationAction({
        code,
        name: newForm.name.trim(),
        points: Number(newForm.points),
        daily_cap: newForm.daily_cap.trim() === '' ? null : Number(newForm.daily_cap),
        sort_order: newForm.sort_order.trim() === '' ? null : Number(newForm.sort_order),
      });
      toast.success('Действие создано');
      setNewForm({ code: '', name: '', points: '0', daily_cap: '', sort_order: '' });
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось создать действие'));
    } finally {
      setCreating(false);
    }
  };

  if (loadError && !actions) return <p className="text-site-red text-sm">{loadError}</p>;
  if (!actions) return <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />;

  return (
    <div className="flex flex-col gap-5">
      {!canEdit && (
        <p className="text-white/50 text-sm">Только просмотр: менять действия может администратор (право reputation:settings).</p>
      )}
      <p className="text-white/50 text-sm">
        Сколько очков репутации даёт каждое действие в регионе, где оно произошло. Дневной лимит — сколько очков за
        действие можно получить в одном регионе за сутки (пусто — без лимита). Действия «без источника» пока ничем не
        вызываются в игре — их можно применять вручную в карточке персонажа.
      </p>

      <div className="flex flex-col gap-2">
        {actions.map((a) => {
          const r = rows[a.code];
          if (!r) return null;
          const busy = busyCode === a.code;
          const disabled = !canEdit || busy;
          return (
            <div key={a.code} className="p-3 sm:p-4 rounded-card border border-white/[0.07] bg-site-bg flex flex-col gap-3 min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-white/40 text-xs font-mono break-all">{a.code}</span>
                {a.is_builtin && (
                  <span className="px-2 py-0.5 rounded-full border border-gold/40 text-gold text-[11px]">встроенное</span>
                )}
                {!a.has_source && (
                  <span className="px-2 py-0.5 rounded-full border border-white/20 text-white/50 text-[11px]">без источника</span>
                )}
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-[minmax(0,3fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)] gap-3">
                <label className="flex flex-col gap-1 col-span-2 sm:col-span-1 min-w-0">
                  <span className={LABEL}>Название</span>
                  <input className="input-underline w-full" maxLength={100} value={r.name} disabled={disabled}
                    onChange={(e) => setRow(a.code, 'name', e.target.value)} />
                </label>
                <label className="flex flex-col gap-1 min-w-0">
                  <span className={LABEL}>Очки</span>
                  <input className="input-underline w-full" inputMode="numeric" value={r.points} disabled={disabled}
                    onChange={(e) => setRow(a.code, 'points', e.target.value)} />
                </label>
                <label className="flex flex-col gap-1 min-w-0">
                  <span className={LABEL}>Лимит в день</span>
                  <input className="input-underline w-full" inputMode="numeric" placeholder="без лимита" value={r.daily_cap}
                    disabled={disabled} onChange={(e) => setRow(a.code, 'daily_cap', e.target.value)} />
                </label>
                <label className="flex flex-col gap-1 min-w-0">
                  <span className={LABEL}>Порядок</span>
                  <input className="input-underline w-full" inputMode="numeric" value={r.sort_order} disabled={disabled}
                    onChange={(e) => setRow(a.code, 'sort_order', e.target.value)} />
                </label>
              </div>
              {ACTION_NOTES[a.code] && <p className="text-white/40 text-xs">{ACTION_NOTES[a.code]}</p>}
              {canEdit && (
                <div className="flex flex-col sm:flex-row gap-2">
                  <button type="button" className="btn-blue w-full sm:w-auto !text-sm !px-5 !py-1.5 disabled:opacity-50"
                    disabled={busy} onClick={() => void saveRow(a)}>
                    {busy ? 'Сохранение...' : 'Сохранить'}
                  </button>
                  {!a.is_builtin && (
                    <button type="button" className="btn-line w-full sm:w-auto !text-sm !px-5 !py-1.5 disabled:opacity-50"
                      disabled={busy} onClick={() => setToDelete(a)}>
                      Удалить
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {canEdit && (
        <section className="bg-site-bg rounded-card border border-white/[0.07] p-4 sm:p-6 flex flex-col gap-4 min-w-0">
          <h2 className="gold-text text-lg font-medium uppercase tracking-[0.06em]">Новое действие</h2>
          <div className="grid grid-cols-2 sm:grid-cols-[minmax(0,2fr)_minmax(0,3fr)_minmax(0,1fr)_minmax(0,1fr)_minmax(0,1fr)] gap-3">
            <label className="flex flex-col gap-1 col-span-2 sm:col-span-1 min-w-0">
              <span className={LABEL}>Код</span>
              <input className="input-underline w-full font-mono" maxLength={40} placeholder="robbery" value={newForm.code}
                onChange={(e) => setNewForm((f) => ({ ...f, code: e.target.value.toLowerCase() }))} />
            </label>
            <label className="flex flex-col gap-1 col-span-2 sm:col-span-1 min-w-0">
              <span className={LABEL}>Название</span>
              <input className="input-underline w-full" maxLength={100} placeholder="Грабёж" value={newForm.name}
                onChange={(e) => setNewForm((f) => ({ ...f, name: e.target.value }))} />
            </label>
            <label className="flex flex-col gap-1 min-w-0">
              <span className={LABEL}>Очки</span>
              <input className="input-underline w-full" inputMode="numeric" value={newForm.points}
                onChange={(e) => INT_RE.test(e.target.value) && setNewForm((f) => ({ ...f, points: e.target.value }))} />
            </label>
            <label className="flex flex-col gap-1 min-w-0">
              <span className={LABEL}>Лимит в день</span>
              <input className="input-underline w-full" inputMode="numeric" placeholder="без лимита" value={newForm.daily_cap}
                onChange={(e) => UINT_RE.test(e.target.value) && setNewForm((f) => ({ ...f, daily_cap: e.target.value }))} />
            </label>
            <label className="flex flex-col gap-1 min-w-0">
              <span className={LABEL}>Порядок</span>
              <input className="input-underline w-full" inputMode="numeric" placeholder="авто" value={newForm.sort_order}
                onChange={(e) => UINT_RE.test(e.target.value) && setNewForm((f) => ({ ...f, sort_order: e.target.value }))} />
            </label>
          </div>
          <div>
            <button type="button" className="btn-blue w-full sm:w-auto !px-6 disabled:opacity-50" disabled={creating}
              onClick={() => void create()}>
              {creating ? 'Создание...' : 'Создать действие'}
            </button>
          </div>
        </section>
      )}

      {toDelete && (
        <ConfirmDialog
          title="Удалить действие"
          message={`Действие «${toDelete.name}» исчезнет из таблицы весов. Записи журнала с ним сохранятся.`}
          confirmLabel="Удалить"
          danger
          onConfirm={() => void removeAction(toDelete)}
          onCancel={() => setToDelete(null)}
        />
      )}
    </div>
  );
};

export default ReputationActionsTab;
