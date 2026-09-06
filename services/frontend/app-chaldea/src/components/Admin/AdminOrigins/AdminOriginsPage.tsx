import { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  fetchOriginsAdminThunk,
  createOriginThunk,
  updateOriginThunk,
  deleteOriginThunk,
  selectAdminOrigins,
  selectAdminOriginsLoading,
  selectAdminOriginsError,
} from '../../../redux/slices/originsSlice';
import type { OriginCountryAdmin, OriginCountryCreatePayload } from '../../../api/origins';
import { selectPermissions, selectRole } from '../../../redux/slices/userSlice';
import { hasPermission } from '../../../utils/permissions';
import OriginForm from './OriginForm';
import OriginStartingPoints from './OriginStartingPoints';

/**
 * FEAT-154 (rules 8-10, task #23) — admin registry of origin countries.
 *
 * Deletion here is a **soft delete**: the row is hidden from the player-facing
 * list but keeps existing, and the admin listing includes hidden rows by
 * default (note N5) precisely so a hidden origin can be found and restored.
 * The UI therefore says «скрыть» / «вернуть», never «удалить».
 *
 * FEAT-155: each origin also carries a curated set of recommended starting
 * points, edited here (rule 5) — the location tree cannot express that relation
 * at all, and walking five levels to flip one flag was the whole complaint.
 * The «Страна на карте» caption and the `is_playable` marker are gone with
 * their columns (rules 10-11), and with them the country list this page used to
 * load solely to resolve that caption.
 */

type VisibilityFilter = 'all' | 'visible' | 'hidden';

const FILTERS: { value: VisibilityFilter; label: string }[] = [
  { value: 'all', label: 'Все' },
  { value: 'visible', label: 'Видимые' },
  { value: 'hidden', label: 'Скрытые' },
];

const AdminOriginsPage = () => {
  const dispatch = useAppDispatch();
  const origins = useAppSelector(selectAdminOrigins);
  const loading = useAppSelector(selectAdminOriginsLoading);
  const error = useAppSelector(selectAdminOriginsError);
  const role = useAppSelector(selectRole);
  const permissions = useAppSelector(selectPermissions);

  const [filter, setFilter] = useState<VisibilityFilter>('all');
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<OriginCountryAdmin | null>(null);
  const [saving, setSaving] = useState(false);
  const [confirmHide, setConfirmHide] = useState<OriginCountryAdmin | null>(null);
  const [pointsFor, setPointsFor] = useState<OriginCountryAdmin | null>(null);

  // Admin always holds every permission, so the role short-circuit matches
  // the rest of the admin surface (see AdminPage).
  const isAdmin = role === 'admin';
  const canCreate = isAdmin || hasPermission(permissions, 'origins:create');
  const canUpdate = isAdmin || hasPermission(permissions, 'origins:update');
  const canDelete = isAdmin || hasPermission(permissions, 'origins:delete');
  // Reading the set needs `origins:read`; changing it needs `origins:update`.
  const canReadPoints = isAdmin || hasPermission(permissions, 'origins:read');

  useEffect(() => {
    // N5 — include_inactive defaults to true; hidden rows must stay findable.
    dispatch(fetchOriginsAdminThunk(true));
  }, [dispatch]);

  const visibleOrigins = useMemo(() => {
    const filtered = origins.filter((origin) => {
      if (filter === 'visible') return origin.is_active;
      if (filter === 'hidden') return !origin.is_active;
      return true;
    });
    return [...filtered].sort(
      (a, b) => a.sort_order - b.sort_order || a.name.localeCompare(b.name, 'ru')
    );
  }, [origins, filter]);

  const hiddenCount = useMemo(() => origins.filter((o) => !o.is_active).length, [origins]);

  const handleCreate = () => {
    setEditing(null);
    setShowForm(true);
  };

  const handleEdit = (origin: OriginCountryAdmin) => {
    setEditing(origin);
    setShowForm(true);
  };

  const handleSave = async (data: OriginCountryCreatePayload) => {
    setSaving(true);
    try {
      if (editing) {
        await dispatch(updateOriginThunk({ originId: editing.id, data })).unwrap();
        toast.success('Происхождение обновлено');
      } else {
        await dispatch(createOriginThunk(data)).unwrap();
        toast.success('Происхождение создано');
      }
      setShowForm(false);
      setEditing(null);
      dispatch(fetchOriginsAdminThunk(true));
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось сохранить происхождение.');
    } finally {
      setSaving(false);
    }
  };

  const handleConfirmHide = async () => {
    if (!confirmHide) return;
    try {
      await dispatch(deleteOriginThunk(confirmHide.id)).unwrap();
      toast.success(`Происхождение «${confirmHide.name}» скрыто. Его можно вернуть в любой момент.`);
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось скрыть происхождение.');
    }
    setConfirmHide(null);
  };

  const handleRestore = async (origin: OriginCountryAdmin) => {
    try {
      // There is no dedicated restore endpoint (N5) — restore is a PUT.
      await dispatch(
        updateOriginThunk({ originId: origin.id, data: { is_active: true } })
      ).unwrap();
      toast.success(`Происхождение «${origin.name}» снова доступно игрокам`);
    } catch (err) {
      toast.error(typeof err === 'string' ? err : 'Не удалось вернуть происхождение.');
    }
  };

  return (
    <div className="p-4 sm:p-5 text-white min-h-screen">
      <h1 className="gold-text text-xl sm:text-2xl font-medium uppercase text-center mb-3 tracking-wider">
        Происхождения
      </h1>
      <p className="text-white/50 text-sm text-center max-w-[720px] mx-auto mb-8">
        Справочник родных стран для создания персонажа. Он шире карты мира: сюда входят и страны,
        которых на карте нет. Скрытое происхождение не удаляется — оно просто перестаёт
        показываться игрокам и может быть возвращено. Кнопка «Стартовые точки» задаёт, какие
        места игра предложит игроку с этой родиной в первую очередь.
      </p>

      <div className="max-w-[1200px] mx-auto">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
          <div className="flex flex-wrap gap-2">
            {FILTERS.map((item) => (
              <button
                key={item.value}
                type="button"
                onClick={() => setFilter(item.value)}
                aria-pressed={filter === item.value}
                className={`chip-outline rounded-full px-4 py-2 text-xs font-medium ${
                  filter === item.value ? 'chip-outline-active' : ''
                }`}
              >
                {item.label}
                {item.value === 'hidden' && hiddenCount > 0 ? ` (${hiddenCount})` : ''}
              </button>
            ))}
          </div>

          {canCreate && (
            <button
              type="button"
              onClick={handleCreate}
              className="px-4 py-2 bg-green-600/20 text-white border-none rounded cursor-pointer
                transition-colors hover:bg-green-600/30 text-sm"
            >
              Добавить происхождение
            </button>
          )}
        </div>

        {/* Every failure is shown, and the user can retry. */}
        {error && (
          <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-6 p-3 rounded border border-site-red/40 bg-site-red/10">
            <p className="text-site-red text-sm flex-1">{error}</p>
            <button
              type="button"
              onClick={() => dispatch(fetchOriginsAdminThunk(true))}
              className="px-4 py-1.5 bg-white/10 text-white rounded text-sm transition-colors hover:bg-white/20"
            >
              Повторить
            </button>
          </div>
        )}

        {loading && origins.length === 0 && (
          <p className="text-white/60 text-center">Загрузка...</p>
        )}

        {!loading && !error && origins.length === 0 && (
          <p className="text-white/60 text-center">
            Справочник пуст. Добавьте первую страну происхождения — без неё шаг «Родина»
            при создании персонажа останется пустым.
          </p>
        )}

        {!loading && origins.length > 0 && visibleOrigins.length === 0 && (
          <p className="text-white/60 text-center">В этом фильтре ничего нет.</p>
        )}

        <div className="flex flex-col gap-3">
          {visibleOrigins.map((origin) => (
            <div
              key={origin.id}
              className={`bg-[rgba(22,37,49,0.85)] rounded-card p-4 sm:p-5 ${
                origin.is_active ? '' : 'opacity-60'
              }`}
            >
              <div className="flex flex-col lg:flex-row lg:items-start gap-4">
                <div className="flex items-start gap-3 flex-1 min-w-0">
                  {origin.emblem_url && (
                    <img
                      src={origin.emblem_url}
                      alt={origin.name}
                      className="w-12 h-12 object-contain flex-shrink-0"
                    />
                  )}
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-base sm:text-lg font-medium text-gold break-words">
                        {origin.name}
                      </span>
                      {!origin.is_active && (
                        <span className="text-xs px-2 py-0.5 rounded-full border border-site-red/50 text-site-red">
                          Скрыто от игроков
                        </span>
                      )}
                      <span className="text-xs text-white/40">#{origin.sort_order}</span>
                    </div>

                    {origin.summary && (
                      <p className="mt-2 text-white/70 text-sm whitespace-pre-wrap break-words">
                        {origin.summary}
                      </p>
                    )}
                    {origin.skitaltsy_attitude && (
                      <p className="mt-2 text-white/50 text-sm whitespace-pre-wrap break-words">
                        <span className="text-white/40">Отношение к Скитальцам: </span>
                        {origin.skitaltsy_attitude}
                      </p>
                    )}
                    {origin.archive_slug && (
                      <p className="mt-2 text-white/35 text-xs break-words">
                        Архив: /{origin.archive_slug}
                      </p>
                    )}
                  </div>
                </div>

                <div className="flex flex-wrap gap-2 lg:justify-end lg:flex-shrink-0">
                  {canReadPoints && (
                    <button
                      type="button"
                      onClick={() => setPointsFor(origin)}
                      className="px-3 py-1.5 bg-site-blue/20 text-site-blue rounded text-sm transition-colors hover:bg-site-blue/30"
                    >
                      Стартовые точки
                    </button>
                  )}
                  {canUpdate && (
                    <button
                      type="button"
                      onClick={() => handleEdit(origin)}
                      className="px-3 py-1.5 bg-white/10 text-white rounded text-sm transition-colors hover:bg-white/20"
                    >
                      Редактировать
                    </button>
                  )}
                  {origin.is_active
                    ? canDelete && (
                        <button
                          type="button"
                          onClick={() => setConfirmHide(origin)}
                          className="px-3 py-1.5 bg-site-red/20 text-site-red rounded text-sm transition-colors hover:bg-site-red/30"
                        >
                          Скрыть
                        </button>
                      )
                    : canUpdate && (
                        <button
                          type="button"
                          onClick={() => handleRestore(origin)}
                          className="px-3 py-1.5 bg-site-blue/20 text-site-blue rounded text-sm transition-colors hover:bg-site-blue/30"
                        >
                          Вернуть
                        </button>
                      )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {showForm && (
        <OriginForm
          origin={editing}
          onSave={handleSave}
          onCancel={() => {
            setShowForm(false);
            setEditing(null);
          }}
          loading={saving}
        />
      )}

      {pointsFor && (
        <OriginStartingPoints
          originId={pointsFor.id}
          originName={pointsFor.name}
          canUpdate={canUpdate}
          onClose={() => setPointsFor(null)}
        />
      )}

      {/*
        Portalled for the same reason as `OriginForm`: this page renders inside
        an animated (transformed) wrapper, which becomes the containing block
        for `position: fixed` and traps `.modal-overlay`'s z-index under the
        site header. Both overlays on this page use the one approach.
      */}
      {confirmHide && createPortal(
        <div className="modal-overlay" onClick={() => setConfirmHide(null)}>
          <div
            className="modal-content gold-outline gold-outline-thick w-full max-w-md"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="gold-text text-xl uppercase mb-4">Скрыть происхождение</h2>
            <p className="text-white mb-2">
              «{confirmHide.name}» перестанет показываться игрокам при создании персонажа.
            </p>
            <p className="text-white/60 text-sm mb-6">
              Запись не удаляется: она останется в этом списке с пометкой «Скрыто от игроков»,
              и её можно вернуть кнопкой «Вернуть». Уже созданные персонажи не пострадают.
            </p>
            <div className="flex flex-col sm:flex-row gap-3">
              <button
                type="button"
                onClick={handleConfirmHide}
                className="px-6 py-2 bg-site-red/20 text-site-red rounded font-medium transition-colors hover:bg-site-red/30"
              >
                Скрыть
              </button>
              <button
                type="button"
                onClick={() => setConfirmHide(null)}
                className="px-6 py-2 bg-white/10 text-white rounded font-medium transition-colors hover:bg-white/20"
              >
                Отмена
              </button>
            </div>
          </div>
        </div>,
        document.body,
      )}
    </div>
  );
};

export default AdminOriginsPage;
