import { useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { uploadEpisodeImage } from '../../../api/episodes';
import { recropImage } from '../../../api/avatarCrop';
import { apiErrorMessage } from '../../../api/errors';
import AvatarEditor from '../../CommonComponents/AvatarEditor/AvatarEditor';

interface ImageFieldProps {
  label: string;
  value: string | null;
  onChange: (url: string | null) => void;
  /** A mini-role's avatar: round, and the player picks its frame. */
  round?: boolean;
}

/** Picks a picture, uploads it at once and hands back its URL. */
const ImageField = ({ label, value, onChange, round = false }: ImageFieldProps) => {
  const input = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [framing, setFraming] = useState(false);

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
        onClick={() => (round ? setFraming(true) : input.current?.click())}
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
      <div className="flex gap-3">
        {round && value && (
          <button type="button" onClick={() => setFraming(true)} className="text-xs text-white/40 hover:text-gold transition-colors">
            Изменить кадр
          </button>
        )}
        {value && (
          <button type="button" onClick={() => onChange(null)} className="text-xs text-white/40 hover:text-site-red transition-colors">
            Убрать картинку
          </button>
        )}
      </div>
      <input ref={input} type="file" accept="image/jpeg,image/png,image/webp,image/gif" className="hidden"
        onChange={(e) => void pick(e.target.files?.[0])} />
      {framing && (
        <AvatarEditor
          title={label}
          round
          currentUrl={value}
          onClose={() => setFraming(false)}
          onUpload={async (file, crop) => onChange(await uploadEpisodeImage(file, crop))}
          onReframe={async (crop) => onChange(await recropImage(value!, crop))}
        />
      )}
    </div>
  );
};

export default ImageField;
