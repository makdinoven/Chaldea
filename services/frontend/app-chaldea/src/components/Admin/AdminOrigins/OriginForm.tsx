import { useEffect, useMemo, useState } from 'react';
import type {
  OriginCountryAdmin,
  OriginCountryCreatePayload,
} from '../../../api/origins';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';

/**
 * FEAT-154 (rules 8-10) — create/edit one origin country.
 *
 * FEAT-155 (rules 10-12): the «страна на карте мира» select and the
 * «играбельная страна» checkbox are gone. They described the same thing twice
 * and could contradict each other, and the registry is deliberately wider than
 * the playable `Countries` anyway. An origin's link to the world is now
 * expressed only through its recommended starting points, curated on the
 * listing page.
 */
/** Images picked on the admin's device; uploaded by the page after the origin is saved. */
export interface OriginImageFiles {
  emblem: File | null;
  map: File | null;
}

interface OriginFormProps {
  origin: OriginCountryAdmin | null;
  onSave: (data: OriginCountryCreatePayload, files: OriginImageFiles) => void;
  onCancel: () => void;
  loading: boolean;
}

const FIELD_CLASS =
  'w-full p-2.5 bg-black/30 border border-white/10 rounded text-white ' +
  'transition-colors focus:border-site-blue/50 focus:outline-none';
const LABEL_CLASS = 'block mb-1 text-white/60 font-medium text-sm uppercase tracking-wide';

/** Mirrors the server-side rule for `archive_slug`. */
const SLUG_PATTERN = /^[a-z0-9-]+$/;

const trimmedOrNull = (value: string): string | null => {
  const trimmed = value.trim();
  return trimmed ? trimmed : null;
};

interface ImageFieldProps {
  label: string;
  currentUrl: string | null;
  file: File | null;
  removed: boolean;
  onFile: (file: File | null) => void;
  onRemove: () => void;
}

/** File picker with a preview of the current or newly chosen image (same flow as other admin images). */
const ImageField = ({ label, currentUrl, file, removed, onFile, onRemove }: ImageFieldProps) => {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null);
      return undefined;
    }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  const shown = previewUrl ?? (removed ? null : currentUrl);

  return (
    <div className="flex flex-col gap-2 min-w-0">
      <label className={LABEL_CLASS}>{label}</label>
      <input
        type="file"
        accept="image/*"
        onChange={(e) => onFile(e.target.files?.[0] ?? null)}
        className="text-white/60 text-sm max-w-full"
      />
      {shown && (
        <img
          src={shown}
          alt={label}
          className="max-h-[120px] max-w-full w-auto object-contain rounded border border-white/10 self-start"
        />
      )}
      {file && <p className="text-white/40 text-xs break-all">Выбрано: {file.name} — загрузится при сохранении</p>}
      {!file && currentUrl && !removed && (
        <button
          type="button"
          onClick={onRemove}
          className="self-start text-xs text-white/50 hover:text-site-red transition-colors"
        >
          Убрать изображение
        </button>
      )}
      {!file && removed && <p className="text-white/40 text-xs">Изображение будет убрано при сохранении</p>}
    </div>
  );
};

const OriginForm = ({ origin, onSave, onCancel, loading }: OriginFormProps) => {
  const [name, setName] = useState(origin?.name || '');
  const [summary, setSummary] = useState(origin?.summary || '');
  const [attitude, setAttitude] = useState(origin?.skitaltsy_attitude || '');
  const [archiveSlug, setArchiveSlug] = useState(origin?.archive_slug || '');
  const [emblemFile, setEmblemFile] = useState<File | null>(null);
  const [mapFile, setMapFile] = useState<File | null>(null);
  const [emblemRemoved, setEmblemRemoved] = useState(false);
  const [mapRemoved, setMapRemoved] = useState(false);
  const [sortOrder, setSortOrder] = useState(String(origin?.sort_order ?? 0));

  const slugError = useMemo(() => {
    const value = archiveSlug.trim();
    if (!value) return null;
    return SLUG_PATTERN.test(value)
      ? null
      : 'Слаг статьи Архива может содержать только строчные латинские буквы, цифры и дефис.';
  }, [archiveSlug]);

  const sortOrderError = useMemo(() => {
    const value = sortOrder.trim();
    if (!value) return null;
    return Number.isInteger(Number(value)) ? null : 'Порядок сортировки должен быть целым числом.';
  }, [sortOrder]);

  const canSubmit = Boolean(name.trim()) && !slugError && !sortOrderError && !loading;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!canSubmit) return;
    const data: OriginCountryCreatePayload = {
      name: name.trim(),
      summary: trimmedOrNull(summary),
      skitaltsy_attitude: trimmedOrNull(attitude),
      archive_slug: trimmedOrNull(archiveSlug),
      sort_order: sortOrder.trim() ? Number(sortOrder) : 0,
    };
    // Image URLs are written by the upload itself; only an explicit «убрать» clears them here.
    if (emblemRemoved && !emblemFile) data.emblem_url = null;
    if (mapRemoved && !mapFile) data.map_image_url = null;
    onSave(data, { emblem: emblemFile, map: mapFile });
  };

  return (
    <ModalShell
      open
      onClose={onCancel}
      title={origin ? 'Редактировать происхождение' : 'Создать происхождение'}
      size="lg"
      footer={
        <>
          <button
            type="submit"
            form="origin-form"
            disabled={!canSubmit}
            className="w-full sm:w-auto px-6 py-2 bg-site-blue text-white border-none rounded cursor-pointer font-medium
              transition-colors hover:bg-[#5d8fa8] disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'Сохранение...' : 'Сохранить'}
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="w-full sm:w-auto px-6 py-2 bg-white/10 text-white border-none rounded cursor-pointer font-medium
              transition-colors hover:bg-white/20"
          >
            Отмена
          </button>
        </>
      }
    >
      <form id="origin-form" onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div>
          <label className={LABEL_CLASS}>Название</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={120}
            placeholder="Например, Империя Мидденгерд"
            className={FIELD_CLASS}
          />
        </div>

        <div>
          <label className={LABEL_CLASS}>Краткое описание</label>
          <textarea
            value={summary}
            onChange={(e) => setSummary(e.target.value)}
            rows={3}
            placeholder="Что игрок должен знать о родине при выборе"
            className={`${FIELD_CLASS} resize-y`}
          />
          <p className="mt-1 text-white/40 text-xs">
            Это текст для игрока. Админские описания стран из карты мира здесь не используются.
          </p>
        </div>

        <div>
          <label className={LABEL_CLASS}>Отношение к Скитальцам</label>
          <textarea
            value={attitude}
            onChange={(e) => setAttitude(e.target.value)}
            rows={3}
            placeholder="Например: почитают как героев / считают еретиками"
            className={`${FIELD_CLASS} resize-y`}
          />
        </div>

        <div>
          <label className={LABEL_CLASS}>Слаг статьи Архива</label>
          <input
            type="text"
            value={archiveSlug}
            onChange={(e) => setArchiveSlug(e.target.value)}
            placeholder="middengerd"
            className={FIELD_CLASS}
          />
          {slugError ? (
            <p className="mt-1 text-site-red text-xs">{slugError}</p>
          ) : (
            <p className="mt-1 text-white/40 text-xs">
              Необязательно. Ведёт на статью Архива, если она есть.
            </p>
          )}
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <ImageField
            label="Герб"
            currentUrl={origin?.emblem_url ?? null}
            file={emblemFile}
            removed={emblemRemoved}
            onFile={(f) => {
              setEmblemFile(f);
              if (f) setEmblemRemoved(false);
            }}
            onRemove={() => setEmblemRemoved(true)}
          />
          <ImageField
            label="Карта"
            currentUrl={origin?.map_image_url ?? null}
            file={mapFile}
            removed={mapRemoved}
            onFile={(f) => {
              setMapFile(f);
              if (f) setMapRemoved(false);
            }}
            onRemove={() => setMapRemoved(true)}
          />
        </div>

        <div className="sm:max-w-[50%]">
          <label className={LABEL_CLASS}>Порядок сортировки</label>
          <input
            type="number"
            value={sortOrder}
            onChange={(e) => setSortOrder(e.target.value)}
            className={FIELD_CLASS}
          />
          {sortOrderError ? (
            <p className="mt-1 text-site-red text-xs">{sortOrderError}</p>
          ) : (
            <p className="mt-1 text-white/40 text-xs">
              Порядок в списке при создании персонажа. Меньше — выше.
            </p>
          )}
        </div>
      </form>
    </ModalShell>
  );
};

export default OriginForm;
