import { useState } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import ModalShell from '../../CommonComponents/ModalShell/ModalShell';
import ThemePicker from './ThemePicker';
import { EntityListPicker } from './editor/pickers';
import { generateDungeon, type DungeonGeneratePayload, type DungeonGenerateResult } from '../../../api/dungeons';
import { isTheme, type DungeonTheme } from '../../DungeonBoard3D/dungeonThemes';

/*
  FEAT-177: the dungeon generator. The admin sets a few numbers and gets a draft
  map — rooms, corridors, mobs, finds, keys and doors, stock texts — to finish
  in the editor. The dungeon is switched off until they turn it back on.
*/

const MAX_FLOORS = 5;
const ROOMS_MIN = 4;
const ROOMS_MAX = 20;
const PARTY_MAX = 4;
const LEVEL_MAX = 200;
const SEED_MAX = 2 ** 31;

const DIFFICULTIES: { value: DungeonGeneratePayload['difficulty']; label: string }[] = [
  { value: 'easy', label: 'Лёгкая' },
  { value: 'normal', label: 'Обычная' },
  { value: 'hard', label: 'Тяжёлая' },
];

interface DungeonGeneratorModalProps {
  open: boolean;
  onClose: () => void;
  dungeonId: number;
  /** Rooms the dungeon has now: replacing them needs a tick. */
  roomsCount: number;
  defaultLevel?: number | null;
  defaultPartySize?: number | null;
  defaultTheme?: string;
  /** The map was rebuilt: reload the dungeon. */
  onGenerated: () => void;
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
const toRange = (text: string, lo: number, hi: number) => clamp(Math.round(Number(text) || lo), lo, hi);

const errorText = (e: unknown): string => {
  if (axios.isAxiosError(e)) {
    const detail = e.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail) && detail.length) {
      return detail.map((d: { msg?: string }) => d.msg ?? '').filter(Boolean).join('; ');
    }
    if (!e.response) return 'Нет связи с сервером';
  }
  return 'Не удалось сгенерировать подземелье';
};

const DungeonGeneratorModal = ({
  open,
  onClose,
  dungeonId,
  roomsCount,
  defaultLevel,
  defaultPartySize,
  defaultTheme,
  onGenerated,
}: DungeonGeneratorModalProps) => {
  // Numbers are kept as typed and brought into range on the way out.
  const [floors, setFloors] = useState('1');
  const [rooms, setRooms] = useState('8');
  const [level, setLevel] = useState(String(defaultLevel ?? 1));
  const [party, setParty] = useState(String(clamp(defaultPartySize ?? 2, 1, PARTY_MAX)));
  const [difficulty, setDifficulty] = useState<DungeonGeneratePayload['difficulty']>('normal');
  const [theme, setTheme] = useState<DungeonTheme>(isTheme(defaultTheme) ? defaultTheme : 'stone');
  const [locks, setLocks] = useState(true);
  const [secrets, setSecrets] = useState(true);
  const [seed, setSeed] = useState('');
  const [mobPool, setMobPool] = useState<number[]>([]);
  const [bossPool, setBossPool] = useState<number[]>([]);
  const [lootPool, setLootPool] = useState<number[]>([]);
  const [replace, setReplace] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DungeonGenerateResult | null>(null);

  const mustConfirm = roomsCount > 0 && !result;

  const run = async (fresh: boolean) => {
    let seedValue: number | undefined;
    if (!fresh && seed.trim()) {
      seedValue = Number(seed);
      if (!Number.isInteger(seedValue) || seedValue < 0 || seedValue >= SEED_MAX) {
        setError('Seed — целое число от 0 до 2147483647');
        return;
      }
    }
    setBusy(true);
    setError(null);
    try {
      const res = await generateDungeon(dungeonId, {
        floors: toRange(floors, 1, MAX_FLOORS),
        rooms_per_floor: toRange(rooms, ROOMS_MIN, ROOMS_MAX),
        level: toRange(level, 1, LEVEL_MAX),
        party_size: toRange(party, 1, PARTY_MAX),
        difficulty,
        theme,
        locks,
        secrets,
        seed: seedValue,
        mob_pool: mobPool.length ? mobPool : undefined,
        boss_pool: bossPool.length ? bossPool : undefined,
        loot_pool: lootPool.length ? lootPool : undefined,
        // A second go replaces what the first one built.
        replace: replace || !!result || roomsCount === 0,
      });
      setResult(res);
      setSeed(String(res.seed));
      onGenerated();
      toast.success(`Подземелье сгенерировано: ${res.rooms} комнат`);
    } catch (e) {
      const text = errorText(e);
      setError(text);
      toast.error(text);
    } finally {
      setBusy(false);
    }
  };

  const close = () => {
    setResult(null);
    setReplace(false);
    setError(null);
    onClose();
  };

  const numberField = (
    label: string,
    value: string,
    set: (v: string) => void,
    lo: number,
    hi: number,
  ) => (
    <label className="flex flex-col gap-1">
      <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">{label}</span>
      <input
        type="number"
        inputMode="numeric"
        min={lo}
        max={hi}
        value={value}
        onChange={(e) => set(e.target.value)}
        onBlur={() => set(String(toRange(value, lo, hi)))}
        className="input-underline"
      />
    </label>
  );

  const toggle = (label: string, hint: string, value: boolean, set: (v: boolean) => void) => (
    <label className="flex items-start gap-3 cursor-pointer">
      <input type="checkbox" checked={value} onChange={(e) => set(e.target.checked)} className="mt-1 accent-gold" />
      <span className="flex flex-col">
        <span className="text-sm text-white">{label}</span>
        <span className="text-xs text-white/45">{hint}</span>
      </span>
    </label>
  );

  const poolFields: { label: string; kind: 'mob' | 'item'; ids: number[]; set: (ids: number[]) => void }[] = [
    { label: 'Мобы для боёв', kind: 'mob', ids: mobPool, set: setMobPool },
    { label: 'Боссы', kind: 'mob', ids: bossPool, set: setBossPool },
    { label: 'Предметы добычи', kind: 'item', ids: lootPool, set: setLootPool },
  ];

  const footer = result ? (
    <div className="flex flex-col-reverse sm:flex-row gap-2 sm:justify-end w-full">
      <button type="button" onClick={() => void run(true)} disabled={busy} className="btn-line !w-full sm:!w-auto !px-5">
        {busy ? 'Генерация...' : 'Другой вариант'}
      </button>
      <button type="button" onClick={close} className="btn-blue !w-full sm:!w-auto !px-6">
        Открыть в редакторе
      </button>
    </div>
  ) : (
    <div className="flex flex-col-reverse sm:flex-row gap-2 sm:justify-end w-full">
      <button type="button" onClick={close} className="btn-line !w-full sm:!w-auto !px-5">
        Отмена
      </button>
      <button
        type="button"
        onClick={() => void run(false)}
        disabled={busy || (mustConfirm && !replace)}
        className="btn-blue !w-full sm:!w-auto !px-6 disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {busy ? 'Генерация...' : 'Сгенерировать'}
      </button>
    </div>
  );

  return (
    <ModalShell
      open={open}
      onClose={close}
      title="Генератор подземелья"
      size="lg"
      closeOnBackdrop={false}
      dismissible={!busy}
      footer={footer}
    >
      {result ? (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-white">
            Готово: {result.rooms} комнат, {result.corridors} коридоров.{' '}
            <span className="text-white/50">Seed {result.seed} — с ним карта соберётся такой же.</span>
          </p>
          <p className="text-xs text-white/50">
            Подземелье выключено и не видно на локации. Поправьте карту и тексты, затем включите его кнопкой «Неактивно — включить» рядом с названием.
          </p>
          {result.validation.errors.length > 0 && (
            <div className="flex flex-col gap-1">
              <span className="text-xs uppercase tracking-[0.06em] text-site-red">Ошибки проверки</span>
              {result.validation.errors.map((e) => (
                <span key={e} className="text-sm text-site-red">{e}</span>
              ))}
            </div>
          )}
          {[...result.warnings, ...result.validation.warnings].length > 0 && (
            <div className="flex flex-col gap-1">
              <span className="text-xs uppercase tracking-[0.06em] text-yellow-400/80">Обратите внимание</span>
              {[...result.warnings, ...result.validation.warnings].map((w) => (
                <span key={w} className="text-sm text-yellow-200/80">{w}</span>
              ))}
            </div>
          )}
          {result.validation.valid && result.warnings.length === 0 && (
            <p className="text-sm text-green-400">Проверка пройдена: подземелье проходимо.</p>
          )}
          {error && <p className="text-sm text-site-red">{error}</p>}
        </div>
      ) : (
        <div className="flex flex-col gap-5">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {numberField('Этажей', floors, setFloors, 1, MAX_FLOORS)}
            {numberField('Комнат на этаже', rooms, setRooms, ROOMS_MIN, ROOMS_MAX)}
            {numberField('Уровень', level, setLevel, 1, LEVEL_MAX)}
            {numberField('Размер группы', party, setParty, 1, PARTY_MAX)}
          </div>

          <div className="flex flex-col gap-2">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Сложность</span>
            <div className="grid grid-cols-3 gap-2">
              {DIFFICULTIES.map((d) => (
                <button
                  key={d.value}
                  type="button"
                  aria-pressed={difficulty === d.value}
                  onClick={() => setDifficulty(d.value)}
                  className={`rounded-card border px-2 py-2 text-sm transition-colors ${
                    difficulty === d.value ? 'border-gold/70 bg-gold/10 text-white' : 'border-white/10 text-white/60 hover:border-white/30'
                  }`}
                >
                  {d.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex flex-col gap-2">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Оформление</span>
            <ThemePicker value={theme} onChange={setTheme} />
          </div>

          <div className="flex flex-col gap-3">
            {toggle('Ключи и запертые двери', 'Ключ всегда лежит там, куда можно дойти до его двери', locks, setLocks)}
            {toggle(
              'Тайники и испытания классов',
              'Тайные ходы, решётки, печати, скрытые провалы и тёмные комнаты — только в стороне от главного пути',
              secrets,
              setSecrets,
            )}
          </div>

          <details className="group">
            <summary className="cursor-pointer text-sm text-site-blue hover:text-white transition-colors">
              Свои мобы и добыча, seed
            </summary>
            <div className="flex flex-col gap-4 pt-3">
              <p className="text-xs text-white/45">
                Пусто — мобы и предметы подбираются по уровню. Искать можно по названию или id.
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                {poolFields.map(({ label, kind, ids, set }) => (
                  <div key={label} className="flex flex-col gap-1 min-w-0">
                    <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">{label}</span>
                    <EntityListPicker kind={kind} ids={ids} onChange={set} />
                  </div>
                ))}
              </div>
              <label className="flex flex-col gap-1 sm:max-w-[200px]">
                <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Seed</span>
                <input
                  value={seed}
                  onChange={(e) => setSeed(e.target.value)}
                  inputMode="numeric"
                  placeholder="случайный"
                  className="input-underline"
                />
              </label>
            </div>
          </details>

          {roomsCount > 0 && (
            <label className="flex items-start gap-3 cursor-pointer rounded-card border border-site-red/40 bg-site-red/10 p-3">
              <input
                type="checkbox"
                checked={replace}
                onChange={(e) => setReplace(e.target.checked)}
                className="mt-1 accent-gold"
              />
              <span className="text-sm text-white">
                Заменить текущую карту: {roomsCount} комнат и все коридоры будут удалены, несохранённые правки в
                редакторе тоже пропадут.
              </span>
            </label>
          )}

          <p className="text-xs text-white/45">
            Тексты комнат — заготовки под оформление. После генерации подземелье выключится, пока вы его не проверите.
          </p>
          {error && <p className="text-sm text-site-red">{error}</p>}
        </div>
      )}
    </ModalShell>
  );
};

export default DungeonGeneratorModal;
