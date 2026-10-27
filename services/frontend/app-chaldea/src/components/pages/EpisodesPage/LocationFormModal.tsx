import { useState } from 'react';
import toast from 'react-hot-toast';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import { createLocation, updateLocation, type EpisodeLocationCard, type LocationInput } from '../../../api/episodes';
import { apiErrorMessage } from '../../../api/errors';
import ImageField from './ImageField';
import { FIELD, LABEL } from './EpisodeFormModal';

interface LocationFormModalProps {
  episodeId: number;
  /** Absent → a new location. */
  location?: Pick<EpisodeLocationCard, 'id' | 'name' | 'description' | 'image_url' | 'sort_order'>;
  nextOrder?: number;
  onClose: () => void;
  onSaved: () => void;
}

const LocationFormModal = ({ episodeId, location, nextOrder = 0, onClose, onSaved }: LocationFormModalProps) => {
  const [form, setForm] = useState<LocationInput>({
    name: location?.name ?? '',
    description: location?.description ?? '',
    image_url: location?.image_url ?? null,
    sort_order: location?.sort_order ?? nextOrder,
  });
  const [saving, setSaving] = useState(false);

  const save = async () => {
    if (!form.name.trim()) {
      toast.error('Укажите название локации');
      return;
    }
    setSaving(true);
    try {
      if (location) await updateLocation(episodeId, location.id, form);
      else await createLocation(episodeId, form);
      toast.success(location ? 'Локация сохранена' : 'Локация создана');
      onSaved();
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить локацию'));
      setSaving(false);
    }
  };

  return (
    <ModalShell
      open
      onClose={onClose}
      title={location ? 'Локация' : 'Новая локация'}
      size="md"
      dismissible={!saving}
      closeOnBackdrop={false}
      footer={
        <>
          <button type="button" onClick={onClose} disabled={saving} className="btn-line w-full sm:w-auto !px-5">Отмена</button>
          <button type="button" onClick={() => void save()} disabled={saving} className="btn-blue w-full sm:w-auto !px-6 disabled:opacity-50">
            {saving ? 'Сохранение...' : 'Сохранить'}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <label className="flex flex-col gap-1.5">
          <span className={LABEL}>Название</span>
          <input value={form.name} maxLength={120} onChange={(e) => setForm({ ...form, name: e.target.value })} className={FIELD} />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className={LABEL}>Описание</span>
          <textarea value={form.description} maxLength={5000} onChange={(e) => setForm({ ...form, description: e.target.value })}
            className={`${FIELD} resize-y min-h-[100px]`} />
        </label>
        <ImageField label="Картинка (фон локации)" value={form.image_url} onChange={(url) => setForm({ ...form, image_url: url })} />
        <label className="flex flex-col gap-1.5 max-w-[160px]">
          <span className={LABEL}>Порядок в списке</span>
          <input type="number" value={form.sort_order} onChange={(e) => setForm({ ...form, sort_order: Math.round(Number(e.target.value) || 0) })}
            className={FIELD} />
        </label>
      </div>
    </ModalShell>
  );
};

export default LocationFormModal;
