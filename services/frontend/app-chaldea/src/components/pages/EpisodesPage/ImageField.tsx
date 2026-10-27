import { useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { uploadEpisodeImage } from '../../../api/episodes';
import { apiErrorMessage } from '../../../api/errors';

interface ImageFieldProps {
  label: string;
  value: string | null;
  onChange: (url: string | null) => void;
  /** Round preview, for a mini-role's avatar. */
  round?: boolean;
}

/** Picks a picture, uploads it at once and hands back its URL. */
const ImageField = ({ label, value, onChange, round = false }: ImageFieldProps) => {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  const pick = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    try {
      onChange(await uploadEpisodeImage(file));
    } catch (e) {
      toast.error(apiErrorMessage(e, 'Не удалось загрузить картинку'));
    } finally {
      setBusy(false);
      if (input.current) input.current.value = '';
    }
  };

  const frame = round ? 'w-24 h-24 rounded-full' : 'w-full aspect-[16/7] rounded-card';
  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">{label}</span>
      <button
        type="button"
        onClick={() => input.current?.click()}
        disabled={busy}
        className={`${frame} relative overflow-hidden border border-dashed border-white/20 hover:border-gold/60 bg-black/30 transition-colors flex items-center justify-center`}
      >
        {value ? (
          <img src={value} alt="" className="absolute inset-0 w-full h-full object-cover" />
        ) : (
          <span className="text-white/40 text-xs px-2 text-center">{busy ? 'Загрузка...' : 'Выбрать картинку'}</span>
        )}
        {busy && value && <span className="absolute inset-0 bg-black/60 flex items-center justify-center text-xs text-white">Загрузка...</span>}
      </button>
      {value && (
        <button type="button" onClick={() => onChange(null)} className="self-start text-xs text-white/40 hover:text-site-red transition-colors">
          Убрать картинку
        </button>
      )}
      <input ref={input} type="file" accept="image/jpeg,image/png,image/webp,image/gif" className="hidden"
        onChange={(e) => void pick(e.target.files?.[0])} />
    </div>
  );
};

export default ImageField;
