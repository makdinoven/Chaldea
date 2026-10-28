import { useEffect, useRef, useState, type MouseEvent } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import {
  adminCreatePlot,
  adminUpdatePlot,
  getPlot,
  PLOT_KIND_LABEL,
  type Plot,
  type PlotInput,
  type PlotKind,
} from '../../../api/houses';
import { lookupLocations } from '../../../api/adminCharacters';
import { apiErrorMessage } from '../../../api/errors';
import { FIELD, LABEL } from '../../pages/EpisodesPage/EpisodeFormModal';
import ImageField from '../../pages/EpisodesPage/ImageField';
import PlotPlanEditor, { defaultPlan, planFromPlot, planToBody, validatePlan, type EditorPlan } from './PlotPlanEditor';

interface PlotFormModalProps {
  /** Absent → a new plot. */
  plot?: Plot;
  onClose: () => void;
  onSaved: () => void;
}

const LOOKUP_DEBOUNCE_MS = 300;

/** The plot's own fields; the plan is edited separately. */
type PlotFields = Omit<PlotInput, 'grid_w' | 'grid_h' | 'extension_price' | 'layers' | 'cells' | 'rooms'>;

/** Map picture of the region a location belongs to (for placing the marker). */
const regionMapOf = async (locationId: number, knownRegionId: number | null): Promise<string | null> => {
  let regionId = knownRegionId;
  if (regionId == null) {
    const { data } = await axios.get<{ region_id?: number | null }>(`/locations/${locationId}/client/details`);
    regionId = data.region_id ?? null;
  }
  if (regionId == null) return null;
  const { data } = await axios.get<{ map_image_url?: string | null }>(`/locations/regions/${regionId}/details`);
  return data.map_image_url ?? null;
};

const PlotFormModal = ({ plot, onClose, onSaved }: PlotFormModalProps) => {
  const [form, setForm] = useState<PlotFields>({
    location_id: plot?.location_id ?? 0,
    name: plot?.name ?? '',
    description: plot?.description ?? '',
    image_url: plot?.image_url ?? null,
    price: plot?.price ?? 1000,
    map_x: plot?.map_x ?? null,
    map_y: plot?.map_y ?? null,
    kind: plot?.kind ?? 'ready',
  });
  const [plan, setPlan] = useState<EditorPlan | null>(plot ? null : defaultPlan());
  const [locationName, setLocationName] = useState(plot?.location_name ?? '');
  const [query, setQuery] = useState('');
  const [options, setOptions] = useState<{ id: number; name: string }[]>([]);
  const [loadingRooms, setLoadingRooms] = useState(!!plot);
  const [saving, setSaving] = useState(false);
  const [mapUrl, setMapUrl] = useState<string | null>(null);
  const mapRef = useRef<HTMLDivElement>(null);
  const set = <K extends keyof PlotFields>(k: K, v: PlotFields[K]) => setForm((f) => ({ ...f, [k]: v }));

  // Existing plot: its plan and template rooms come from the plot card endpoint.
  useEffect(() => {
    if (!plot) return;
    getPlot(plot.id)
      .then((d) => setPlan(planFromPlot(d)))
      .catch((e) => toast.error(apiErrorMessage(e, 'Не удалось загрузить план участка')))
      .finally(() => setLoadingRooms(false));
  }, [plot]);

  useEffect(() => {
    if (query.trim().length < 1) {
      setOptions([]);
      return undefined;
    }
    const t = setTimeout(() => {
      lookupLocations(query.trim())
        .then(setOptions)
        .catch((e) => toast.error(apiErrorMessage(e, 'Не удалось найти локации')));
    }, LOOKUP_DEBOUNCE_MS);
    return () => clearTimeout(t);
  }, [query]);

  useEffect(() => {
    setMapUrl(null);
    if (!form.location_id) return undefined;
    let cancelled = false;
    const known = plot && plot.location_id === form.location_id ? plot.region_id : null;
    regionMapOf(form.location_id, known)
      .then((url) => {
        if (!cancelled) setMapUrl(url);
      })
      .catch((e) => {
        if (!cancelled) toast.error(apiErrorMessage(e, 'Не удалось загрузить карту региона'));
      });
    return () => {
      cancelled = true;
    };
  }, [form.location_id, plot]);

  const pickPoint = (e: MouseEvent<HTMLDivElement>) => {
    const box = mapRef.current?.getBoundingClientRect();
    if (!box) return;
    const round = (v: number) => Math.round(Math.min(100, Math.max(0, v)) * 10) / 10;
    setForm((f) => ({
      ...f,
      map_x: round(((e.clientX - box.left) / box.width) * 100),
      map_y: round(((e.clientY - box.top) / box.height) * 100),
    }));
  };

  const numberOrNull = (v: string) => (v.trim() === '' ? null : Number(v));

  const save = async () => {
    if (!form.location_id) {
      toast.error('Выберите локацию');
      return;
    }
    if (!form.name.trim()) {
      toast.error('Введите название участка');
      return;
    }
    if (!plan) {
      toast.error('План участка ещё не загружен');
      return;
    }
    const planError = validatePlan(plan, form.kind);
    if (planError) {
      toast.error(planError);
      return;
    }
    setSaving(true);
    try {
      const body: PlotInput = {
        ...form,
        name: form.name.trim(),
        // An empty plot is land only (no rooms): the owner builds them.
        ...planToBody(plan, form.kind),
      };
      if (plot) await adminUpdatePlot(plot.id, body);
      else await adminCreatePlot(body);
      toast.success(plot ? 'Участок сохранён' : 'Участок создан');
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить участок'));
      setSaving(false);
    }
  };

  return (
    <ModalShell
      open
      onClose={onClose}
      title={plot ? 'Участок' : 'Новый участок'}
      size="lg"
      dismissible={!saving}
      closeOnBackdrop={false}
      closeOnEscape={false}
      footer={
        <>
          <button type="button" onClick={onClose} disabled={saving} className="btn-line w-full sm:w-auto !px-5">Отмена</button>
          <button type="button" onClick={() => void save()} disabled={saving || loadingRooms}
            className="btn-blue w-full sm:w-auto !px-6 disabled:opacity-50">
            {saving ? 'Сохранение...' : plot ? 'Сохранить' : 'Создать'}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {plot?.house && (
          <p className="text-gold-light text-xs bg-gold/10 border border-gold-dark/30 rounded-card p-3">
            На участке уже куплен дом «{plot.house.name}». Шаблон комнат влияет только на будущие покупки, а план
            применяется и к этому дому: место, где уже стоит его комната, убрать нельзя.
          </p>
        )}

        <div className="flex flex-col gap-1.5">
          <span className={LABEL}>Вид участка</span>
          <div className="grid grid-cols-2 gap-2 sm:max-w-md">
            {(['ready', 'empty'] as PlotKind[]).map((k) => (
              <button key={k} type="button" onClick={() => set('kind', k)}
                className={`px-3 py-2 rounded-card border text-sm transition-colors ${
                  form.kind === k ? 'border-gold/70 text-gold bg-gold/10' : 'border-white/10 text-white/60 hover:text-white'
                }`}>
                {PLOT_KIND_LABEL[k]}
              </button>
            ))}
          </div>
          <span className="text-white/40 text-xs">
            {form.kind === 'ready'
              ? 'Покупатель получает дом с шаблонными комнатами, расставленными на плане ниже.'
              : 'Покупатель получает только землю и сам строит комнаты на местах плана за золото и материалы.'}
          </span>
        </div>

        <div className="flex flex-col gap-1.5 relative">
          <span className={LABEL}>Локация</span>
          {form.location_id > 0 && (
            <span className="text-white text-sm">
              {locationName || `#${form.location_id}`} <span className="text-white/40">(ID {form.location_id})</span>
            </span>
          )}
          <input value={query} onChange={(e) => setQuery(e.target.value)}
            placeholder={form.location_id ? 'Сменить: название или ID' : 'Название или ID локации'} className={FIELD} />
          {options.length > 0 && (
            <div className="bg-black/80 border border-white/10 rounded-card divide-y divide-white/5 max-h-56 overflow-y-auto gold-scrollbar">
              {options.map((o) => (
                <button key={o.id} type="button"
                  onClick={() => {
                    set('location_id', o.id);
                    setLocationName(o.name);
                    setQuery('');
                    setOptions([]);
                  }}
                  className="w-full text-left px-3 py-2 text-sm text-white hover:bg-white/[0.06] transition-colors">
                  {o.name} <span className="text-white/40 text-xs">#{o.id}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        <label className="flex flex-col gap-1.5">
          <span className={LABEL}>Название</span>
          <input value={form.name} maxLength={120} onChange={(e) => set('name', e.target.value)} className={FIELD} />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className={LABEL}>Описание</span>
          <textarea value={form.description} maxLength={5000} onChange={(e) => set('description', e.target.value)}
            className={`${FIELD} resize-y min-h-[90px]`} />
        </label>
        <ImageField label="Картинка" value={form.image_url} onChange={(url) => set('image_url', url)} />

        <label className="flex flex-col gap-1.5 sm:max-w-xs">
          <span className={LABEL}>Цена (золото)</span>
          <input type="number" min={0} value={form.price} onChange={(e) => set('price', Math.max(0, Number(e.target.value) || 0))} className={FIELD} />
        </label>

        <div className="flex flex-col gap-2">
          <span className={LABEL}>Точка на карте региона, % (необязательно)</span>
          <div className="grid grid-cols-2 gap-3 sm:max-w-sm">
            <input type="number" min={0} max={100} step={0.1} placeholder="X" value={form.map_x ?? ''}
              onChange={(e) => set('map_x', numberOrNull(e.target.value))} className={FIELD} />
            <input type="number" min={0} max={100} step={0.1} placeholder="Y" value={form.map_y ?? ''}
              onChange={(e) => set('map_y', numberOrNull(e.target.value))} className={FIELD} />
          </div>
          {mapUrl && (
            <>
              <span className="text-white/40 text-xs">Или кликните по карте региона:</span>
              <div ref={mapRef} onClick={pickPoint} className="relative w-full rounded-card overflow-hidden cursor-crosshair border border-white/10">
                <img src={mapUrl} alt="Карта региона" className="w-full h-auto block select-none" draggable={false} />
                {form.map_x != null && form.map_y != null && (
                  <span className="absolute w-4 h-4 rounded-full bg-gold border-2 border-black/70 pointer-events-none"
                    style={{ left: `${form.map_x}%`, top: `${form.map_y}%`, transform: 'translate(-50%, -50%)' }} />
                )}
              </div>
            </>
          )}
          {(form.map_x != null || form.map_y != null) && (
            <button type="button" onClick={() => setForm((f) => ({ ...f, map_x: null, map_y: null }))}
              className="self-start text-xs text-white/40 hover:text-site-red transition-colors">
              Убрать с карты
            </button>
          )}
        </div>

        <div className="flex flex-col gap-3">
          <span className={LABEL}>План участка</span>
          {loadingRooms && <div className="w-6 h-6 border-4 border-white/30 border-t-gold rounded-full animate-spin" />}
          {plan && (
            <PlotPlanEditor plan={plan} kind={form.kind}
              onChange={(updater) => setPlan((p) => (p ? updater(p) : p))} />
          )}
        </div>
      </div>
    </ModalShell>
  );
};

export default PlotFormModal;
