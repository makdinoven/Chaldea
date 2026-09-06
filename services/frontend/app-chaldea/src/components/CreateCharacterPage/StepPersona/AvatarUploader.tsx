import { useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { uploadCharacterRequestAvatar } from '../../../api/characterRequests';

/**
 * FEAT-154 (task #18) — avatar upload for a character that does not exist yet
 * (rule 21, D4).
 *
 * The old form sent the literal `avatar: 'string'`; here the file really goes
 * to `POST /photo/upload_character_request_avatar`, which writes no DB row and
 * answers with a permanent S3 URL that the application then carries.
 *
 * **The field is optional on purpose.** If the upload fails the player sees a
 * Russian message and can still submit — on approval the subrace artwork is
 * used instead. Nothing here ever blocks the wizard.
 */

/** Mirrors the backend cap (`photo-service/utils.py`) — 413 above it. */
const MAX_AVATAR_BYTES = 15 * 1024 * 1024;
const MAX_AVATAR_LABEL = '15 МБ';

interface AvatarUploaderProps {
  /** The uploaded S3 URL, or `null` while nothing has been uploaded. */
  value: string | null;
  onChange: (avatarUrl: string | null) => void;
  /** Subrace artwork — what the character will get if no avatar is uploaded. */
  fallbackImage?: string | null;
  characterName?: string;
}

const AvatarUploader = ({
  value,
  onChange,
  fallbackImage,
  characterName,
}: AvatarUploaderProps) => {
  const inputRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // A blob preview is a browser resource, not application state — release it.
  useEffect(() => {
    return () => {
      if (preview) URL.revokeObjectURL(preview);
    };
  }, [preview]);

  const shown = value ?? preview ?? fallbackImage ?? null;

  const handleFile = async (file: File) => {
    // Both checks mirror the server so the player is told immediately instead
    // of after a 15 MB round trip. The server still has the final word.
    if (!file.type.startsWith('image/')) {
      const message = 'Это не изображение. Подойдут JPG, PNG или WebP.';
      setError(message);
      toast.error(message);
      return;
    }
    if (file.size > MAX_AVATAR_BYTES) {
      const message = `Файл слишком большой. Максимальный размер — ${MAX_AVATAR_LABEL}.`;
      setError(message);
      toast.error(message);
      return;
    }

    setError(null);
    setUploading(true);

    // Show the picked file straight away; it is replaced by the S3 URL on success.
    if (preview) URL.revokeObjectURL(preview);
    const objectUrl = URL.createObjectURL(file);
    setPreview(objectUrl);

    try {
      const { avatar_url } = await uploadCharacterRequestAvatar(file);
      onChange(avatar_url);
      toast.success('Портрет загружен.');
    } catch (err) {
      // 413 (over 15 MB) and 400 (not an image) both arrive here already
      // translated by `apiErrorMessage`. The application stays submittable.
      const message =
        err instanceof Error && err.message
          ? err.message
          : 'Не удалось загрузить портрет. Заявку можно отправить и без него.';
      setError(message);
      toast.error(message);
      onChange(null);
    } finally {
      setUploading(false);
    }
  };

  const handleChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    // Reset the input so re-picking the same file fires `change` again.
    event.target.value = '';
    if (file) void handleFile(file);
  };

  const handleClear = () => {
    if (preview) URL.revokeObjectURL(preview);
    setPreview(null);
    setError(null);
    onChange(null);
  };

  return (
    <div className="flex flex-col items-center gap-3 w-full">
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        disabled={uploading}
        aria-label="Загрузить портрет персонажа"
        className="hover-gold-overlay w-[160px] h-[160px] sm:w-[200px] sm:h-[200px] rounded-card
                   gold-outline bg-white/5 disabled:cursor-wait"
      >
        {shown ? (
          <img src={shown} alt="" className="w-full h-full object-cover" />
        ) : (
          <span className="w-full h-full flex items-center justify-center px-3 text-center text-white/40 text-xs">
            Нажмите, чтобы выбрать портрет
          </span>
        )}

        {characterName && (
          <span className="absolute bottom-0 left-0 w-full h-[60px] flex items-end justify-center pb-2 rounded-b-card bg-gradient-to-t from-black/90 to-transparent">
            <span className="gold-text text-xs sm:text-sm font-medium uppercase text-center px-2 truncate max-w-full">
              {characterName}
            </span>
          </span>
        )}

        {uploading && (
          <span className="absolute inset-0 bg-black/60 flex items-center justify-center">
            <span className="w-8 h-8 border-4 border-white/30 border-t-white rounded-full animate-spin" />
          </span>
        )}
      </button>

      <input
        ref={inputRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handleChange}
      />

      <div className="flex flex-wrap items-center justify-center gap-3">
        <button
          type="button"
          className="btn-line text-sm w-auto px-5"
          onClick={() => inputRef.current?.click()}
          disabled={uploading}
        >
          {uploading ? 'Загрузка…' : value ? 'Заменить портрет' : 'Загрузить портрет'}
        </button>
        {value && !uploading && (
          <button type="button" className="site-link text-sm" onClick={handleClear}>
            Убрать
          </button>
        )}
      </div>

      {error ? (
        <p className="text-site-red text-[13px] sm:text-sm text-center max-w-[260px] leading-snug">{error}</p>
      ) : (
        <p className="field-hint text-left max-w-[260px]">
          Портрет необязателен. Без него в паспорт попадёт изображение вашей подрасы.
          Не больше {MAX_AVATAR_LABEL}.
        </p>
      )}
    </div>
  );
};

export default AvatarUploader;
