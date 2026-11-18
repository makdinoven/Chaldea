import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import {
  createSeaShip,
  fetchSeaCandidates,
  seaAdminError,
  seaRangeText,
  SEA_LIMITS,
  updateSeaShip,
  type SeaLimitKey,
} from '../../../api/seaAdmin';
import type {
  SeaCandidates,
  SeaLeg,
  SeaPort,
  SeaShipAdmin,
  SeaShipCreate,
  SeaShipUpdate,
  SeaStopInput,
  SeaZone,
} from '../../../types/seaAdmin';
import { FIELD, LABEL } from '../../pages/EpisodesPage/EpisodeFormModal';
import ShipStopsEditor from './ShipStopsEditor';

interface ShipFormProps {
  /** Absent → a new ship. */
  ship?: SeaShipAdmin;
  ports: SeaPort[];
  zones: SeaZone[];
  canSave: boolean;
  onSaved: (ship: SeaShipAdmin) => void;
  onCancel?: () => void;
}

type NumKey =
  | 'capacity'
  | 'crew_slots'
  | 'cargo_capacity'
  | 'boarding_minutes'
  | 'zone_minutes'
  | 'fare_base'
  | 'fare_per_zone';

const NUM_FIELDS: { key: NumKey; label: string; hint: string }[] = [
  { key: 'capacity', label: 'Мест для пассажиров', hint: 'Билетов на один рейс (0 — билеты не продаются)' },
  { key: 'crew_slots', label: 'Мест для матросов', hint: 'Наём на один рейс (0 — матросов не берут)' },
  { key: 'cargo_capacity', label: 'Трюм (караванов за рейс)', hint: 'Сколько караванов берёт за рейс (0 — грузы не возит)' },
  { key: 'boarding_minutes', label: 'Сборы в порту, мин', hint: 'Сколько корабль стоит у причала в каждом порту' },
  { key: 'zone_minutes', label: 'Время на морскую зону, мин', hint: 'Скорость: сколько идёт одна морская зона' },
  { key: 'fare_base', label: 'Базовая цена билета', hint: 'Билет = база + цена за зону × число зон пути' },
  { key: 'fare_per_zone', label: 'Цена за морскую зону', hint: 'Добавляется за каждую зону пути пассажира' },
];

const DEFAULTS: Record<NumKey, number> = {
  capacity: 10,
  crew_slots: 2,
  cargo_capacity: 2,
  boarding_minutes: 30,
  zone_minutes: 10,
  fare_base: 10,
  fare_per_zone: 5,
};

const stopsOf = (ship?: SeaShipAdmin): SeaStopInput[] =>
  ship ? ship.stops.map((s) => ({ port_location_id: s.port_id, path_override: s.path_override?.length ? s.path_override : null })) : [];

/** Comparable route signature (the last stop's manual path only matters on a loop). */
const routeSig = (stops: SeaStopInput[], isLoop: boolean): string =>
  JSON.stringify([
    stops.map((s, i) => [s.port_location_id, i < stops.length - 1 || isLoop ? s.path_override ?? [] : []]),
    isLoop,
  ]);

const ShipForm = ({ ship, ports, zones, canSave, onSaved, onCancel }: ShipFormProps) => {
  const isNew = !ship;
  const [name, setName] = useState(ship?.name ?? '');
  const [deckId, setDeckId] = useState<string>(ship ? String(ship.deck.id) : '');
  const [captainId, setCaptainId] = useState<string>(ship?.captain_npc_id ? String(ship.captain_npc_id) : '');
  const [nums, setNums] = useState<Record<NumKey, string>>(() =>
    // `?? DEFAULTS` — an older backend does not send `cargo_capacity` yet.
    Object.fromEntries(NUM_FIELDS.map(({ key }) => [key, String(ship?.[key] ?? DEFAULTS[key])])) as Record<NumKey, string>,
  );
  const [isLoop, setIsLoop] = useState(ship?.is_loop ?? false);
  const [isActive, setIsActive] = useState(ship?.is_active ?? true);
  const [stops, setStops] = useState<SeaStopInput[]>(() => stopsOf(ship));
  const [legs, setLegs] = useState<SeaLeg[] | null>(null);
  const [candidates, setCandidates] = useState<SeaCandidates | null>(null);
  const [candidatesError, setCandidatesError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchSeaCandidates(ship?.id)
      .then((c) => {
        if (!cancelled) setCandidates(c);
      })
      .catch((e) => {
        if (!cancelled) setCandidatesError(seaAdminError(e, 'Не удалось загрузить палубы и капитанов'));
      });
    return () => {
      cancelled = true;
    };
  }, [ship?.id]);

  const routeLocked = !!ship && ship.status !== 'docked';
  const zoneMinutes = Number(nums.zone_minutes) || 0;
  const badLegs = legs?.filter((l) => !l.ok) ?? [];

  const validate = (): string | null => {
    const trimmed = name.trim();
    if (trimmed.length < SEA_LIMITS.name[0] || trimmed.length > SEA_LIMITS.name[1]) return 'Название корабля: от 1 до 100 символов';
    if (isNew && !deckId) return 'Выберите локацию палубы';
    for (const { key } of NUM_FIELDS) {
      const raw = nums[key].trim();
      const value = Number(raw);
      const [min, max] = SEA_LIMITS[key as SeaLimitKey];
      if (raw === '' || !Number.isInteger(value) || value < min || value > max) return `Неверное значение: ${seaRangeText(key)}`;
    }
    if (stops.length < SEA_LIMITS.stops[0] || stops.length > SEA_LIMITS.stops[1]) return 'В маршруте должно быть от 2 до 30 портов';
    for (let i = 1; i < stops.length; i += 1) {
      if (stops[i].port_location_id === stops[i - 1].port_location_id) {
        return `Соседние остановки маршрута не могут быть одним портом (остановка ${i + 1})`;
      }
    }
    if (isLoop && stops.length > 1 && stops[0].port_location_id === stops[stops.length - 1].port_location_id) {
      return 'По кругу: первый и последний порт не могут совпадать';
    }
    return null;
  };

  const numbers = (): Record<NumKey, number> =>
    Object.fromEntries(NUM_FIELDS.map(({ key }) => [key, Number(nums[key])])) as Record<NumKey, number>;

  const submit = async () => {
    const problem = validate();
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    setSaving(true);
    try {
      let saved: SeaShipAdmin;
      if (!ship) {
        const body: SeaShipCreate = {
          name: name.trim(),
          captain_npc_id: captainId ? Number(captainId) : null,
          deck_location_id: Number(deckId),
          ...numbers(),
          is_loop: isLoop,
          is_active: isActive,
          stops,
        };
        saved = await createSeaShip(body);
        toast.success(`Корабль «${saved.name}» создан`);
      } else {
        const patch: SeaShipUpdate = {};
        if (name.trim() !== ship.name) patch.name = name.trim();
        const newCaptain = captainId ? Number(captainId) : null;
        if (newCaptain !== (ship.captain_npc_id ?? null)) patch.captain_npc_id = newCaptain;
        const n = numbers();
        NUM_FIELDS.forEach(({ key }) => {
          if (n[key] !== (ship[key] ?? DEFAULTS[key])) patch[key] = n[key];
        });
        if (isActive !== ship.is_active) patch.is_active = isActive;
        if (routeSig(stops, isLoop) !== routeSig(stopsOf(ship), ship.is_loop)) {
          patch.stops = stops;
          patch.is_loop = isLoop;
        }
        if (Object.keys(patch).length === 0) {
          toast('Изменений нет');
          setSaving(false);
          return;
        }
        saved = await updateSeaShip(ship.id, patch);
        toast.success('Корабль сохранён');
      }
      onSaved(saved);
    } catch (e) {
      const message = seaAdminError(e, 'Не удалось сохранить корабль');
      setError(message);
      toast.error(message);
    } finally {
      setSaving(false);
    }
  };

  const deckOptions = candidates?.decks ?? [];
  const captainOptions = candidates?.captains ?? [];

  return (
    <div className="flex flex-col gap-5">
      {candidatesError && <p className="text-site-red text-sm">{candidatesError}</p>}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <label className="flex flex-col gap-1.5 md:col-span-2">
          <span className={LABEL}>Название</span>
          <input
            value={name}
            maxLength={SEA_LIMITS.name[1]}
            onChange={(e) => setName(e.target.value)}
            disabled={!canSave}
            placeholder="Например, «Морская дева»"
            className={FIELD}
          />
        </label>

        <label className="flex flex-col gap-1.5">
          <span className={LABEL}>Палуба (локация)</span>
          {isNew ? (
            <select value={deckId} onChange={(e) => setDeckId(e.target.value)} disabled={!canSave} className={FIELD}>
              <option value="">— выберите локацию палубы —</option>
              {deckOptions.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name ?? `#${d.id}`}
                  {d.region_name ? ` (${d.region_name}${d.country_name ? `, ${d.country_name}` : ''})` : ''}
                </option>
              ))}
            </select>
          ) : (
            <span className={`${FIELD} !bg-transparent text-white/70`}>{ship.deck.name ?? `#${ship.deck.id}`}</span>
          )}
          <span className="text-white/40 text-xs">
            {isNew
              ? 'Локация скрытой страны без переходов (не порт и не морская зона). Потом палубу не сменить.'
              : 'Палубу корабля менять нельзя.'}
          </span>
          {isNew && candidates && deckOptions.length === 0 && (
            <span className="text-site-red text-xs">
              Свободных палуб нет — создайте локацию в скрытой стране (например, «Моря») без соседей.
            </span>
          )}
        </label>

        <label className="flex flex-col gap-1.5">
          <span className={LABEL}>Капитан (НПС)</span>
          <select value={captainId} onChange={(e) => setCaptainId(e.target.value)} disabled={!canSave} className={FIELD}>
            <option value="">— без капитана (билеты не продаются) —</option>
            {captainOptions.map((c) => (
              <option key={c.id} value={c.id}>
                {c.name ?? `#${c.id}`}
                {c.location_name ? ` — сейчас: ${c.location_name}` : ''}
              </option>
            ))}
          </select>
          <span className="text-white/40 text-xs">
            Свободные живые НПС с ролью «Капитан». Капитан сам переходит в порт стоянки или на палубу.
          </span>
        </label>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {NUM_FIELDS.map(({ key, label, hint }) => (
          <label key={key} className="flex flex-col gap-1.5">
            <span className={LABEL}>{label}</span>
            <input
              type="number"
              inputMode="numeric"
              min={SEA_LIMITS[key][0]}
              max={SEA_LIMITS[key][1]}
              step={1}
              value={nums[key]}
              disabled={!canSave}
              onChange={(e) => setNums((prev) => ({ ...prev, [key]: e.target.value }))}
              className={FIELD}
            />
            <span className="text-white/40 text-xs">
              {hint} ({SEA_LIMITS[key][0]}–{SEA_LIMITS[key][1].toLocaleString('ru-RU')})
            </span>
          </label>
        ))}
      </div>

      <div className="flex flex-col sm:flex-row gap-3 sm:gap-6">
        <label className="flex items-start gap-2 text-white/85 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={isLoop}
            disabled={!canSave || routeLocked}
            onChange={(e) => setIsLoop(e.target.checked)}
            className="w-4 h-4 mt-0.5 shrink-0"
          />
          <span>
            По кругу
            <span className="block text-white/40 text-xs">Иначе — туда-обратно по линии портов</span>
          </span>
        </label>
        <label className="flex items-start gap-2 text-white/85 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={isActive}
            disabled={!canSave}
            onChange={(e) => setIsActive(e.target.checked)}
            className="w-4 h-4 mt-0.5 shrink-0"
          />
          <span>
            Корабль ходит
            <span className="block text-white/40 text-xs">
              Выключенный корабль не отплывает; неначатые билеты возвращаются
            </span>
          </span>
        </label>
      </div>

      <div className="flex flex-col gap-2">
        <span className={LABEL}>Маршрут — порты по порядку</span>
        <ShipStopsEditor
          stops={stops}
          onChange={setStops}
          isLoop={isLoop}
          zoneMinutes={zoneMinutes}
          ports={ports}
          zones={zones}
          disabled={!canSave || routeLocked}
          disabledReason={routeLocked ? 'Корабль в море — маршрут меняется только у причала.' : undefined}
          onLegsChange={setLegs}
        />
      </div>

      {badLegs.length > 0 && (
        <p className="text-site-red text-xs">
          Есть участки с проблемами ({badLegs.map((l) => l.index + 1).join(', ')}) — сохранение может быть отклонено.
        </p>
      )}
      {error && <p className="text-site-red text-sm">{error}</p>}

      {canSave && (
        <div className="flex flex-col sm:flex-row gap-2 sm:justify-end">
          {onCancel && (
            <button type="button" onClick={onCancel} disabled={saving} className="btn-line w-full sm:w-auto">
              Отмена
            </button>
          )}
          <button type="button" onClick={() => void submit()} disabled={saving} className="btn-blue w-full sm:w-auto">
            {saving ? 'Сохранение…' : isNew ? 'Создать корабль' : 'Сохранить'}
          </button>
        </div>
      )}
    </div>
  );
};

export default ShipForm;
