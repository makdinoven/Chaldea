import { useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { Play, Upload, RotateCcw } from 'react-feather';
import { playSound, type SoundKind } from '../../utils/notifySound';
import {
  ACCEPTED_SOUND_TYPES,
  MAX_SOUND_SECONDS,
  loadCustomSounds,
  removeCustomSound,
  saveCustomSound,
  useCustomSounds,
} from '../../utils/customSounds';

const SLOTS: { kind: SoundKind; label: string }[] = [
  { kind: 'message', label: 'Сообщение' },
  { kind: 'notification', label: 'Уведомление' },
  { kind: 'battle', label: 'Начало боя' },
];

const iconButton =
  'w-9 h-9 shrink-0 flex items-center justify-center rounded-card border border-white/10 bg-white/[0.04] text-white/70 hover:bg-white/[0.07] hover:text-white transition-colors duration-200 ease-site disabled:opacity-40';

/**
 * The three sounds, each standard or the player's own file kept in this
 * browser: listen, upload, back to standard.
 */
const SoundSlots = () => {
  const custom = useCustomSounds();
  const [busy, setBusy] = useState<SoundKind | null>(null);
  const inputs = useRef<Partial<Record<SoundKind, HTMLInputElement | null>>>({});

  useEffect(() => {
    void loadCustomSounds();
  }, []);

  const handleFile = async (kind: SoundKind, file: File | undefined) => {
    if (!file) return;
    setBusy(kind);
    try {
      await saveCustomSound(kind, file);
      toast.success('Звук сохранён в этом браузере');
      playSound(kind, { force: true });
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Не удалось загрузить звук');
    } finally {
      setBusy(null);
    }
  };

  const handleReset = async (kind: SoundKind) => {
    setBusy(kind);
    try {
      await removeCustomSound(kind);
      toast.success('Вернули стандартный звук');
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Не удалось вернуть стандартный звук');
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="flex flex-col gap-2">
      <ul className="flex flex-col divide-y divide-white/5">
        {SLOTS.map(({ kind, label }) => {
          const own = custom[kind];
          return (
            <li key={kind} className="flex items-center gap-2 py-2">
              <div className="flex-1 min-w-0">
                <p className="text-white text-sm">{label}</p>
                <p className="text-white/40 text-xs truncate" title={own?.name}>
                  {own ? `${own.name} · ${own.duration.toFixed(1)} с` : 'Стандартный'}
                </p>
              </div>
              <button
                type="button"
                onClick={() => playSound(kind, { force: true })}
                className={iconButton}
                title="Послушать"
                aria-label={`Послушать: ${label}`}
              >
                <Play size={14} />
              </button>
              <button
                type="button"
                onClick={() => inputs.current[kind]?.click()}
                disabled={busy === kind}
                className={iconButton}
                title="Загрузить свой звук"
                aria-label={`Загрузить свой звук: ${label}`}
              >
                <Upload size={14} />
              </button>
              {own && (
                <button
                  type="button"
                  onClick={() => handleReset(kind)}
                  disabled={busy === kind}
                  className={iconButton}
                  title="Вернуть стандартный"
                  aria-label={`Вернуть стандартный: ${label}`}
                >
                  <RotateCcw size={14} />
                </button>
              )}
              <input
                ref={(el) => {
                  inputs.current[kind] = el;
                }}
                type="file"
                accept={ACCEPTED_SOUND_TYPES}
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  e.target.value = '';
                  void handleFile(kind, file);
                }}
              />
            </li>
          );
        })}
      </ul>
      <p className="text-white/40 text-xs">
        Свои звуки: mp3, ogg или wav до 500 КБ. Длиннее {MAX_SOUND_SECONDS} секунд — обрежется с
        затуханием. Хранятся только в этом браузере.
      </p>
    </div>
  );
};

export default SoundSlots;
