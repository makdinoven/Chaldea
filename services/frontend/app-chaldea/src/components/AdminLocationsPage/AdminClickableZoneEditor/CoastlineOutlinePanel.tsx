import {
  MAX_TOLERANCE,
  MAX_WATER_SAMPLES,
  MIN_TOLERANCE,
  type MapSamplePoint,
} from '../../../api/mapOutlines';

interface CoastlineOutlinePanelProps {
  open: boolean;
  onToggleOpen: () => void;
  settingsLoading: boolean;
  pipetteMode: boolean;
  onTogglePipette: () => void;
  samples: MapSamplePoint[];
  onRemoveSample: (index: number) => void;
  onClearSamples: () => void;
  tolerance: number;
  onToleranceChange: (value: number) => void;
  hasMask: boolean;
  showMask: boolean;
  onToggleShowMask: () => void;
  landRatio: number | null;
  previewLoading: boolean;
  applyLoading: boolean;
  onPreview: () => void;
  onApply: () => void;
  preciseCount: number;
  zoneCount: number;
  /** Zone mode: name of the selected zone; null = map mode */
  zoneLabel: string | null;
  zoneHasOwnSettings: boolean;
  resetLoading: boolean;
  onResetZoneSettings: () => void;
}

const buttonBase =
  'px-3 py-1.5 rounded text-sm font-medium border-none cursor-pointer transition-colors disabled:opacity-50 disabled:cursor-not-allowed';

/** Controls for computing exact coastline outlines from the map image */
const CoastlineOutlinePanel = ({
  open,
  onToggleOpen,
  settingsLoading,
  pipetteMode,
  onTogglePipette,
  samples,
  onRemoveSample,
  onClearSamples,
  tolerance,
  onToleranceChange,
  hasMask,
  showMask,
  onToggleShowMask,
  landRatio,
  previewLoading,
  applyLoading,
  onPreview,
  onApply,
  preciseCount,
  zoneCount,
  zoneLabel,
  zoneHasOwnSettings,
  resetLoading,
  onResetZoneSettings,
}: CoastlineOutlinePanelProps) => {
  const busy = previewLoading || applyLoading || resetLoading;
  const zoneMode = zoneLabel !== null;
  const noSamples = samples.length === 0;

  return (
    <div className="mt-4 rounded-lg border border-white/10 bg-[rgba(22,37,49,0.85)]">
      <button
        type="button"
        onClick={onToggleOpen}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 bg-transparent border-none cursor-pointer text-left"
        aria-expanded={open}
      >
        <span className="min-w-0 text-[#a8c6df] font-medium truncate">
          {zoneMode ? `Контур для зоны: ${zoneLabel}` : 'Контуры по берегу'}
        </span>
        <span className="flex items-center gap-3 text-xs text-[#8ab3d5]">
          <span>
            Точные: {preciseCount}/{zoneCount}
          </span>
          <span className={`transition-transform ${open ? 'rotate-180' : ''}`}>▾</span>
        </span>
      </button>

      {open && (
        <div className="px-4 pb-4 flex flex-col gap-4">
          <p className="text-xs text-[#8ab3d5] leading-relaxed">
            Сервер находит сушу по цвету карты и обрезает каждую зону по берегу, включая острова.
            Зоны можно рисовать грубо, с запасом по воде. Граница между соседними зонами на одной
            суше пройдёт по линии, которую вы нарисовали.
          </p>

          {zoneMode ? (
            <p className="text-xs text-gold/90 leading-relaxed">
              {zoneHasOwnSettings
                ? 'У этой зоны свои настройки воды. Маска и пересчёт касаются только её.'
                : 'Зона использует общие настройки карты. Применение сохранит для неё собственные.'}
            </p>
          ) : (
            <p className="text-xs text-[#8ab3d5]/80 leading-relaxed">
              Выберите зону в списке или на карте, чтобы настроить контур только для неё. Зоны со своими
              настройками при общем применении пересчитываются по своим.
            </p>
          )}

          {settingsLoading && <p className="text-xs text-[#8ab3d5]">Загрузка настроек…</p>}

          {/* Water samples */}
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <button
                type="button"
                onClick={onTogglePipette}
                className={`${buttonBase} ${
                  pipetteMode ? 'bg-site-blue text-white' : 'bg-white/10 text-[#8ab3d5] hover:bg-white/20'
                }`}
                aria-pressed={pipetteMode}
              >
                {pipetteMode ? 'Пипетка включена' : 'Пипетка'}
              </button>
              <span className="text-xs text-[#8ab3d5]">
                Образцы: {samples.length}/{MAX_WATER_SAMPLES}
              </span>
              {!noSamples && (
                <button
                  type="button"
                  onClick={onClearSamples}
                  className="text-xs text-[#ff9999] hover:text-white bg-transparent border-none underline cursor-pointer"
                >
                  Очистить
                </button>
              )}
            </div>
            {pipetteMode && (
              <p className="text-xs text-gold/90">Кликните по воде, облакам и всему, что не является сушей</p>
            )}
            {!noSamples && (
              <div className="flex flex-wrap gap-1.5">
                {samples.map((sample, index) => (
                  <span
                    key={`${sample.x}-${sample.y}-${index}`}
                    className="inline-flex items-center gap-1 rounded-full bg-black/30 border border-white/10 pl-2 pr-1 py-0.5 text-[11px] text-[#d4e6f3]"
                  >
                    #{index + 1} · {sample.x.toFixed(1)}%, {sample.y.toFixed(1)}%
                    <button
                      type="button"
                      onClick={() => onRemoveSample(index)}
                      className="w-5 h-5 flex items-center justify-center rounded-full bg-transparent border-none text-[#ff9999] hover:bg-white/10 cursor-pointer"
                      aria-label={`Удалить образец ${index + 1}`}
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Tolerance */}
          <label className="flex flex-col gap-1">
            <span className="flex justify-between text-xs text-[#8ab3d5]">
              <span>Чувствительность</span>
              <span className="text-white">{tolerance}</span>
            </span>
            <input
              type="range"
              min={MIN_TOLERANCE}
              max={MAX_TOLERANCE}
              value={tolerance}
              onChange={(e) => onToleranceChange(Number(e.target.value))}
              className="w-full accent-site-blue"
            />
            <span className="text-[11px] text-[#8ab3d5]/80">
              Больше — к воде относятся цвета, сильнее отличающиеся от образцов.
            </span>
          </label>

          {/* Actions */}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={onPreview}
              disabled={busy || noSamples}
              className={`${buttonBase} bg-white/10 text-white hover:bg-white/20`}
            >
              {previewLoading ? 'Считаю…' : 'Показать маску'}
            </button>
            {hasMask && (
              <button
                type="button"
                onClick={onToggleShowMask}
                className={`${buttonBase} bg-transparent text-[#8ab3d5] hover:text-white underline`}
              >
                {showMask ? 'Скрыть маску' : 'Показать маску на карте'}
              </button>
            )}
            {landRatio !== null && (
              <span className="text-xs text-[#8ab3d5]">Суша: {Math.round(landRatio * 100)}%</span>
            )}
          </div>

          <div className="flex flex-col sm:flex-row sm:flex-wrap gap-2">
            <button
              type="button"
              onClick={onApply}
              disabled={busy || noSamples || zoneCount === 0}
              className={`${buttonBase} bg-site-blue text-white hover:bg-[#5d8fa8] w-full sm:w-auto`}
            >
              {applyLoading ? 'Применяю…' : zoneMode ? 'Применить к зоне' : 'Применить ко всем зонам'}
            </button>
            {zoneMode && zoneHasOwnSettings && (
              <button
                type="button"
                onClick={onResetZoneSettings}
                disabled={busy}
                className={`${buttonBase} bg-white/10 text-white hover:bg-white/20 w-full sm:w-auto`}
              >
                {resetLoading ? 'Возвращаю…' : 'Вернуть общие настройки карты'}
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

export default CoastlineOutlinePanel;
