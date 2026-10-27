import { useCallback, useEffect, useRef, useState } from 'react';
import axios from 'axios';
import Cropper, { type Area } from 'react-easy-crop';
import toast from 'react-hot-toast';
import ModalShell from '../ModalShell/ModalShell';
import { apiErrorMessage } from '../../../api/errors';
import { originalOf, type CropArea } from '../../../api/avatarCrop';

/*
  Choosing an avatar's frame: the player drags and zooms the picture under a
  square; the square becomes the avatar, the whole picture stays on the server.
  Opens on the current avatar's whole picture (re-framing needs no upload) or,
  after «Выбрать картинку», on a new file.
*/

const MIN_ZOOM = 1;
const MAX_ZOOM = 5;
const MAX_FILE_SIZE = 15 * 1024 * 1024;

interface AvatarEditorProps {
  title?: string;
  /** The avatar as it is now; absent → the editor starts by picking a file. */
  currentUrl?: string | null;
  /** Round preview and frame (users, mini-roles); square otherwise. */
  round?: boolean;
  onClose: () => void;
  /** A new picture with its frame. */
  onUpload: (file: File, crop: CropArea) => Promise<unknown>;
  /** A new frame for the current picture. */
  onReframe: (crop: CropArea) => Promise<unknown>;
}

const Preview = ({ src, area, className }: { src: string; area: Area; className: string }) => (
  <div className={`relative overflow-hidden bg-white/5 shrink-0 ${className}`}>
    <img
      src={src}
      alt=""
      className="absolute max-w-none"
      style={{
        width: `${10000 / area.width}%`,
        left: `${(-area.x * 100) / area.width}%`,
        top: `${(-area.y * 100) / area.height}%`,
      }}
    />
  </div>
);

const AvatarEditor = ({ title = 'Аватар', currentUrl, round = false, onClose, onUpload, onReframe }: AvatarEditorProps) => {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [fileUrl, setFileUrl] = useState<string | null>(null);
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(MIN_ZOOM);
  const [area, setArea] = useState<Area | null>(null);
  const [pixels, setPixels] = useState<Area | null>(null);
  const [saving, setSaving] = useState(false);

  const src = fileUrl ?? (currentUrl ? originalOf(currentUrl) : null);

  useEffect(() => () => {
    if (fileUrl) URL.revokeObjectURL(fileUrl);
  }, [fileUrl]);

  // Nothing to frame yet: go straight to choosing a file.
  useEffect(() => {
    if (!currentUrl) input.current?.click();
  }, [currentUrl]);

  const pick = (picked: File | undefined) => {
    if (!picked) return;
    if (picked.size > MAX_FILE_SIZE) {
      toast.error('Файл слишком большой. Максимальный размер: 15 МБ');
      return;
    }
    setFile(picked);
    setFileUrl(URL.createObjectURL(picked));
    setCrop({ x: 0, y: 0 });
    setZoom(MIN_ZOOM);
  };

  const onCropComplete = useCallback((a: Area, p: Area) => {
    setArea(a);
    setPixels(p);
  }, []);

  const save = async () => {
    if (!pixels) return;
    const square: CropArea = {
      x: Math.round(pixels.x), y: Math.round(pixels.y),
      width: Math.round(pixels.width), height: Math.round(pixels.height),
    };
    setSaving(true);
    try {
      await (file ? onUpload(file, square) : onReframe(square));
      toast.success(file ? 'Аватар обновлён' : 'Кадр сохранён');
      onClose();
    } catch (e) {
      // Redux thunks and some API helpers fail with a ready Russian message.
      const ready = typeof e === 'string' ? e : !axios.isAxiosError(e) && e instanceof Error ? e.message : null;
      toast.error(ready || apiErrorMessage(e, 'Не удалось сохранить аватар'));
      setSaving(false);
    }
  };

  return (
    <ModalShell
      open
      onClose={onClose}
      title={title}
      size="md"
      dismissible={!saving}
      closeOnBackdrop={false}
      footer={
        <>
          <button type="button" onClick={() => input.current?.click()} disabled={saving}
            className="btn-line w-full sm:w-auto !px-5 sm:mr-auto">
            {src ? 'Другая картинка' : 'Выбрать картинку'}
          </button>
          <button type="button" onClick={onClose} disabled={saving} className="btn-line w-full sm:w-auto !px-5">Отмена</button>
          <button type="button" onClick={() => void save()} disabled={saving || !src || !pixels}
            className="btn-blue w-full sm:w-auto !px-6 disabled:opacity-50">
            {saving ? 'Сохранение...' : 'Сохранить'}
          </button>
        </>
      }
    >
      <input ref={input} type="file" accept="image/jpeg,image/png,image/webp,image/gif" className="hidden"
        onChange={(e) => {
          pick(e.target.files?.[0]);
          e.target.value = '';
        }} />
      {src ? (
        <div className="flex flex-col sm:flex-row gap-4">
          <div className="flex-1 min-w-0 flex flex-col gap-3">
            <div className="relative w-full h-64 sm:h-80 rounded-card overflow-hidden bg-black/40 touch-none">
              <Cropper
                key={src}
                image={src}
                crop={crop}
                zoom={zoom}
                minZoom={MIN_ZOOM}
                maxZoom={MAX_ZOOM}
                aspect={1}
                cropShape={round ? 'round' : 'rect'}
                showGrid={!round}
                onCropChange={setCrop}
                onZoomChange={setZoom}
                onCropComplete={onCropComplete}
              />
            </div>
            <label className="flex items-center gap-3">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em] shrink-0">Масштаб</span>
              <input type="range" min={MIN_ZOOM} max={MAX_ZOOM} step={0.05} value={zoom}
                onChange={(e) => setZoom(Number(e.target.value))} className="w-full accent-site-blue" />
            </label>
            <p className="text-white/40 text-xs">
              Перетащите картинку и приблизьте, чтобы в кадр попало нужное. Картинка хранится целиком — кадр можно
              поменять потом.
            </p>
          </div>
          {area && (
            <div className="flex sm:flex-col items-center gap-3 sm:w-24">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Вид</span>
              <Preview src={src} area={area} className={`w-20 h-20 ${round ? 'rounded-full' : 'rounded-card'}`} />
              <Preview src={src} area={area} className="w-10 h-10 rounded-full" />
            </div>
          )}
        </div>
      ) : (
        <p className="text-white/50 text-sm">Выберите картинку — потом можно будет выбрать кадр.</p>
      )}
    </ModalShell>
  );
};

export default AvatarEditor;
