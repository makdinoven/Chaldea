import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import toast from 'react-hot-toast';
import { ArrowLeft, Home, MapPin, Pencil, Trash2 } from 'lucide-react';
import { adminDeletePlot, adminListPlots, type Plot } from '../../../api/houses';
import { apiErrorMessage } from '../../../api/errors';
import { useAppSelector } from '../../../redux/store';
import { hasPermission } from '../../../utils/permissions';
import ConfirmDialog from '../../pages/LocationPage/ConfirmDialog';
import PlotFormModal from './PlotFormModal';
import BuildCostsAdmin from './BuildCostsAdmin';
import HouseTaxAdmin from './HouseTaxAdmin';
import SeizedHousesAdmin from './SeizedHousesAdmin';

type AdminTab = 'plots' | 'costs' | 'tax' | 'seized';

const ADMIN_TAB_LABEL: Record<AdminTab, string> = {
  plots: 'Участки',
  costs: 'Стоимость стройки',
  tax: 'Налоги',
  seized: 'Изъятые дома',
};

/** Admin: house plots — where houses stand, their price and template rooms (FEAT-180). */
const HousesAdminPage = () => {
  const permissions = useAppSelector((state) => state.user.permissions) as string[];
  const canCreate = hasPermission(permissions, 'locations:create');
  const canUpdate = hasPermission(permissions, 'locations:update');
  const canDelete = hasPermission(permissions, 'locations:delete');
  const [plots, setPlots] = useState<Plot[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [editing, setEditing] = useState<Plot | 'new' | null>(null);
  const [deleting, setDeleting] = useState<Plot | null>(null);
  const [tab, setTab] = useState<AdminTab>('plots');

  const load = useCallback(() => {
    adminListPlots()
      .then((p) => {
        setPlots(p);
        setError(null);
      })
      .catch((e) => setError(apiErrorMessage(e, 'Не удалось загрузить участки')));
  }, []);

  useEffect(load, [load]);

  const remove = async (plot: Plot) => {
    setDeleting(null);
    try {
      await adminDeletePlot(plot.id);
      toast.success('Участок удалён');
      load();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось удалить участок'));
    }
  };

  return (
    <div className="w-full max-w-container mx-auto flex flex-col gap-5 pb-10">
      <Link to="/admin" className="self-start text-white/60 hover:text-white text-sm flex items-center gap-1">
        <ArrowLeft size={15} />Админ-панель
      </Link>
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div className="flex flex-col gap-1.5">
          <h1 className="gold-text text-2xl sm:text-3xl font-semibold uppercase tracking-[0.06em]">Дома и участки</h1>
          <p className="text-white/60 text-sm max-w-2xl">
            Участки в городских локациях: персонаж, стоящий в локации, покупает готовый дом из шаблонных комнат
            или пустой участок, где комнаты строит сам.
          </p>
        </div>
        {canCreate && tab === 'plots' && (
          <button type="button" onClick={() => setEditing('new')} className="btn-blue !w-full sm:!w-auto !px-6 shrink-0">
            Новый участок
          </button>
        )}
      </div>

      <div className="flex gap-1 sm:gap-2 border-b border-white/10 overflow-x-auto gold-scrollbar">
        {(['plots', 'costs', 'tax', 'seized'] as AdminTab[]).map((t) => (
          <button key={t} type="button" onClick={() => setTab(t)}
            className={`px-3 sm:px-4 py-2 -mb-px border-b-2 text-sm uppercase tracking-[0.06em] whitespace-nowrap transition-colors ${
              t === tab ? 'border-gold text-gold' : 'border-transparent text-white/50 hover:text-white'
            }`}>
            {ADMIN_TAB_LABEL[t]}
          </button>
        ))}
      </div>

      {tab === 'costs' && <BuildCostsAdmin canUpdate={canUpdate} />}
      {tab === 'tax' && <HouseTaxAdmin canUpdate={canUpdate} />}
      {tab === 'seized' && <SeizedHousesAdmin />}

      {tab === 'plots' && error && <p className="text-site-red text-sm">{error}</p>}
      {tab === 'plots' && !plots && !error && <div className="w-8 h-8 border-4 border-white/30 border-t-gold rounded-full animate-spin" />}
      {tab === 'plots' && plots?.length === 0 && <p className="text-white/40 text-sm italic">Участков пока нет.</p>}

      {tab === 'plots' && <div className="flex flex-col gap-3">
        {plots?.map((plot) => (
          <article key={plot.id}
            className="bg-site-bg backdrop-blur-sm rounded-card border border-white/[0.07] p-3 sm:p-4 flex flex-col sm:flex-row sm:items-center gap-3">
            <div className="flex items-center gap-3 min-w-0 flex-1">
              <div className="w-16 h-12 sm:w-20 sm:h-14 rounded-[10px] overflow-hidden bg-black/40 shrink-0 flex items-center justify-center">
                {plot.image_url ? <img src={plot.image_url} alt="" className="w-full h-full object-cover" /> : <Home size={20} className="text-white/20" />}
              </div>
              <div className="min-w-0 flex flex-col gap-0.5">
                <p className="text-white text-sm font-medium truncate">
                  {plot.name}
                  {plot.kind === 'empty' && <span className="ml-2 text-gold-light text-[11px] font-normal">пустой участок</span>}
                </p>
                <p className="text-white/50 text-xs flex items-center gap-1 min-w-0">
                  <MapPin size={12} className="shrink-0" />
                  <Link to={`/location/${plot.location_id}`} className="site-link truncate">{plot.location_name ?? `#${plot.location_id}`}</Link>
                  {plot.map_x != null && plot.map_y != null && <span className="text-white/30 shrink-0">· на карте</span>}
                </p>
                <p className="text-xs text-white/50">
                  {plot.price.toLocaleString('ru-RU')} золота · комнат {plot.room_count} · мест {plot.cells_open}{plot.cells_total > plot.cells_open ? `/${plot.cells_total}` : ''} ·{' '}
                  {plot.house ? (
                    <Link to={`/houses/${plot.house.id}`} className="text-gold hover:text-gold-light">
                      {plot.house.owner?.name ?? 'куплен'}
                    </Link>
                  ) : (
                    <span className="text-stat-energy">свободен</span>
                  )}
                  {plot.house?.status === 'frozen' && <span className="text-site-red"> · заморожен</span>}
                  {plot.house?.sale_price != null && (
                    <span className="text-gold"> · продаётся за {plot.house.sale_price.toLocaleString('ru-RU')}</span>
                  )}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-1 self-end sm:self-auto">
              {canUpdate && (
                <button type="button" title="Изменить" onClick={() => setEditing(plot)}
                  className="w-9 h-9 flex items-center justify-center rounded-[8px] text-white/50 hover:text-gold transition-colors">
                  <Pencil size={16} />
                </button>
              )}
              {canDelete && (
                <button type="button" title="Удалить" onClick={() => setDeleting(plot)}
                  className="w-9 h-9 flex items-center justify-center rounded-[8px] text-white/50 hover:text-site-red transition-colors">
                  <Trash2 size={16} />
                </button>
              )}
            </div>
          </article>
        ))}
      </div>}

      {editing && (
        <PlotFormModal
          plot={editing === 'new' ? undefined : editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            load();
          }}
        />
      )}
      {deleting && (
        <ConfirmDialog
          title="Удалить участок"
          message={`«${deleting.name}» будет удалён. Участок с купленным домом удалить нельзя.`}
          confirmLabel="Удалить"
          danger
          onCancel={() => setDeleting(null)}
          onConfirm={() => void remove(deleting)}
        />
      )}
    </div>
  );
};

export default HousesAdminPage;
