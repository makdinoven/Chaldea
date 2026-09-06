import { useMemo, useState } from 'react';
import { createPortal } from 'react-dom';
import type {
  OriginCountryAdmin,
  OriginCountryCreatePayload,
} from '../../../api/origins';

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
interface OriginFormProps {
  origin: OriginCountryAdmin | null;
  onSave: (data: OriginCountryCreatePayload) => void;
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

const OriginForm = ({ origin, onSave, onCancel, loading }: OriginFormProps) => {
  const [name, setName] = useState(origin?.name || '');
  const [summary, setSummary] = useState(origin?.summary || '');
  const [attitude, setAttitude] = useState(origin?.skitaltsy_attitude || '');
  const [archiveSlug, setArchiveSlug] = useState(origin?.archive_slug || '');
  const [emblemUrl, setEmblemUrl] = useState(origin?.emblem_url || '');
  const [mapImageUrl, setMapImageUrl] = useState(origin?.map_image_url || '');
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
    onSave({
      name: name.trim(),
      summary: trimmedOrNull(summary),
      skitaltsy_attitude: trimmedOrNull(attitude),
      archive_slug: trimmedOrNull(archiveSlug),
      emblem_url: trimmedOrNull(emblemUrl),
      map_image_url: trimmedOrNull(mapImageUrl),
      sort_order: sortOrder.trim() ? Number(sortOrder) : 0,
    });
  };

  const handleOverlayClick = (e: React.MouseEvent) => {
    if (e.target === e.currentTarget) onCancel();
  };

  /*
    Portalled to `document.body`, like `ItemDetailModal` / `ConfirmationModal`
    and every overlay on `CharactersListPage`. Not cosmetic: the admin page is
    rendered inside an animated (transformed) wrapper, and a transformed
    ancestor becomes the containing block for `position: fixed` descendants —
    so this overlay's `inset-0` resolved against the scrolling page instead of
    the viewport, its `z-[1000]` stayed trapped in that ancestor's stacking
    context, and the site header (`relative z-50`) drew over the heading.
  */
  return createPortal(
    <div
      className="fixed inset-0 bg-black/85 z-[1000] overflow-y-auto py-6 px-3 sm:py-10 sm:px-5 flex items-start justify-center"
      onClick={handleOverlayClick}
    >
      <div className="modal-content gold-outline gold-outline-thick w-full max-w-2xl">
        <h2 className="gold-text text-xl sm:text-2xl uppercase mb-6">
          {origin ? 'Редактировать происхождение' : 'Создать происхождение'}
        </h2>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
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
            <div>
              <label className={LABEL_CLASS}>Ссылка на герб</label>
              <input
                type="text"
                value={emblemUrl}
                onChange={(e) => setEmblemUrl(e.target.value)}
                placeholder="https://…"
                className={FIELD_CLASS}
              />
            </div>
            <div>
              <label className={LABEL_CLASS}>Ссылка на карту</label>
              <input
                type="text"
                value={mapImageUrl}
                onChange={(e) => setMapImageUrl(e.target.value)}
                placeholder="https://…"
                className={FIELD_CLASS}
              />
            </div>
          </div>

          {emblemUrl.trim() && (
            <img
              src={emblemUrl.trim()}
              alt="Герб"
              className="max-h-[90px] w-auto object-contain rounded border border-white/10 self-start"
            />
          )}

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

          <div className="flex flex-col sm:flex-row gap-3 sm:gap-4 mt-2">
            <button
              type="submit"
              disabled={!canSubmit}
              className="px-6 py-2 bg-site-blue text-white border-none rounded cursor-pointer font-medium
                transition-colors hover:bg-[#5d8fa8] disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loading ? 'Сохранение...' : 'Сохранить'}
            </button>
            <button
              type="button"
              onClick={onCancel}
              className="px-6 py-2 bg-white/10 text-white border-none rounded cursor-pointer font-medium
                transition-colors hover:bg-white/20"
            >
              Отмена
            </button>
          </div>
        </form>
      </div>
    </div>,
    document.body,
  );
};

export default OriginForm;
