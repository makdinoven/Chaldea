import { useState } from 'react';
import toast from 'react-hot-toast';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import {
  CATEGORY_LABEL,
  createEpisode,
  updateEpisode,
  type Episode,
  type EpisodeCategory,
  type EpisodeInput,
} from '../../../api/episodes';
import { apiErrorMessage } from '../../../api/errors';
import ImageField from './ImageField';

interface EpisodeFormModalProps {
  /** Absent → a new episode. */
  episode?: Episode;
  defaultCategory?: EpisodeCategory;
  onClose: () => void;
  onSaved: (episode: Episode) => void;
}

export const FIELD = 'w-full bg-black/40 border border-white/10 rounded-card text-white text-sm p-3 focus:outline-none focus:border-site-blue/50 placeholder:text-white/30';
export const LABEL = 'text-white/50 text-xs font-medium uppercase tracking-[0.06em]';

const EpisodeFormModal = ({ episode, defaultCategory = 'world', onClose, onSaved }: EpisodeFormModalProps) => {
  const [form, setForm] = useState<EpisodeInput>({
    category: episode?.category ?? defaultCategory,
    title: episode?.title ?? '',
    description: episode?.description ?? '',
    image_url: episode?.image_url ?? null,
    is_private: episode?.is_private ?? false,
  });
  const [saving, setSaving] = useState(false);
  const set = <K extends keyof EpisodeInput>(k: K, v: EpisodeInput[K]) => setForm((f) => ({ ...f, [k]: v }));

  const save = async () => {
    if (!form.title.trim() || !form.description.trim()) {
      toast.error('Заполните название и описание');
      return;
    }
    setSaving(true);
    try {
      const saved = episode ? await updateEpisode(episode.id, form) : await createEpisode(form);
      toast.success(episode ? 'Эпизод сохранён' : 'Эпизод создан');
      onSaved(saved);
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось сохранить эпизод'));
      setSaving(false);
    }
  };

  return (
    <ModalShell
      open
      onClose={onClose}
      title={episode ? 'Настройки эпизода' : 'Новый эпизод'}
      size="md"
      dismissible={!saving}
      closeOnBackdrop={false}
      footer={
        <>
          <button type="button" onClick={onClose} disabled={saving} className="btn-line w-full sm:w-auto !px-5">Отмена</button>
          <button type="button" onClick={() => void save()} disabled={saving}
            className="btn-blue w-full sm:w-auto !px-6 disabled:opacity-50">
            {saving ? 'Сохранение...' : episode ? 'Сохранить' : 'Создать'}
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <span className={LABEL}>Категория</span>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {(Object.keys(CATEGORY_LABEL) as EpisodeCategory[]).map((c) => (
              <button key={c} type="button" onClick={() => set('category', c)}
                className={`rounded-card border px-3 py-2 text-sm transition-colors ${
                  form.category === c ? 'border-gold/70 text-gold bg-gold/10' : 'border-white/10 text-white/60 hover:text-white'
                }`}>
                {CATEGORY_LABEL[c]}
              </button>
            ))}
          </div>
        </div>
        <label className="flex flex-col gap-1.5">
          <span className={LABEL}>Название</span>
          <input value={form.title} maxLength={120} onChange={(e) => set('title', e.target.value)} className={FIELD} />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className={LABEL}>Описание</span>
          <textarea value={form.description} maxLength={5000} onChange={(e) => set('description', e.target.value)}
            className={`${FIELD} resize-y min-h-[120px]`} />
        </label>
        <ImageField label="Картинка" value={form.image_url} onChange={(url) => set('image_url', url)} />
        <label className="flex items-start gap-3 cursor-pointer">
          <input type="checkbox" checked={form.is_private} onChange={(e) => set('is_private', e.target.checked)}
            className="mt-1 accent-gold" />
          <span className="flex flex-col">
            <span className="text-white text-sm">Закрытый эпизод</span>
            <span className="text-white/45 text-xs">
              Открывать и читать его смогут только участники. Остальным он не виден даже в списке.
            </span>
          </span>
        </label>
      </div>
    </ModalShell>
  );
};

export default EpisodeFormModal;
