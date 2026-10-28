import { useEffect, useState } from 'react';
import {
  Anvil,
  Archive,
  Bath,
  BedDouble,
  BedSingle,
  BookOpen,
  ChefHat,
  Clock,
  Coins,
  Flame,
  FlaskConical,
  Flower2,
  Gem,
  Hammer,
  Hexagon,
  LibraryBig,
  Orbit,
  Package,
  Sofa,
  Sparkles,
  Sprout,
  Trophy,
  type LucideIcon,
} from 'lucide-react';
import {
  BATH_COOLDOWN_HOURS,
  BATH_RESTORE_PERCENT_BY_LEVEL,
  BEDROOM_SLEEP_FACTOR_BY_LEVEL,
  CELLAR_STACKS_BY_LEVEL,
  CIRCLE_KEEP_PERCENT_BY_LEVEL,
  HOUSE_BUFF_HOURS,
  LIBRARY_CAP_PERCENT_BY_LEVEL,
  LIBRARY_PERCENT_PER_HOUR,
  SHRINE_BONUS_PERCENT_BY_LEVEL,
  SHRINE_COOLDOWN_HOURS,
  TROPHY_PERCENT_CAP,
  TROPHY_PERCENT_PER_PIECE,
  TROPHY_SLOTS_BY_LEVEL,
  GARDEN_BEDS_BY_LEVEL,
  isProfessionRoom,
  KITCHEN_SATIETY_HOURS_BY_LEVEL,
  ROOM_LEVELS,
  roomProfessionName,
  STORAGE_STACKS_BY_LEVEL,
  WORKSHOP_DOUBLE_PERCENT_PER_LEVEL,
  WORKSHOP_XP_PERCENT_PER_LEVEL,
  type BuildCost,
  type HouseRoom,
  type RoomType,
} from '../../../api/houses';
import { cellsWord } from '../../../utils/furniture';
import { parseServerDate } from '../../../utils/serverDate';

/*
  FEAT-180 stage 2 — shared bits of house building: durations, the live
  countdown of a room under construction and the price of a build step.
*/

const MS_PER_MINUTE = 60_000;
const MINUTES_PER_HOUR = 60;
const MINUTES_PER_DAY = 1440;
const HOURS_PER_DAY = 24;
/** How often a countdown re-renders (it shows minutes). */
const COUNTDOWN_TICK_MS = 30_000;
/** Grace after the end before the house is reloaded, so the server has settled it. */
const SETTLE_GRACE_MS = 1500;

/** Icon of each room type (plan cells, build choices). */
export const ROOM_TYPE_ICON: Record<RoomType, LucideIcon> = {
  hall: Sofa,
  bedroom: BedDouble,
  storage: Package,
  cellar: Archive,
  garden: Sprout,
  greenhouse: Flower2,
  apiary: Hexagon,
  bath: Bath,
  forge: Anvil,
  alchemy_lab: FlaskConical,
  kitchen: ChefHat,
  jewelry: Gem,
  enchanting: Sparkles,
  study: BookOpen,
  library: LibraryBig,
  shrine: Flame,
  trophy_hall: Trophy,
  guest_room: BedSingle,
  return_circle: Orbit,
};

/** «грядка / грядки / грядок» (or «улей / улья / ульев» for an apiary) for a count. */
export const bedsWord = (type: RoomType, n: number): string => {
  const mod10 = n % 10;
  const mod100 = n % 100;
  const form = mod10 === 1 && mod100 !== 11 ? 0 : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14) ? 1 : 2;
  return (type === 'apiary' ? ['улей', 'улья', 'ульев'] : ['грядка', 'грядки', 'грядок'])[form];
};

const pct = (n: number) => n.toLocaleString('ru-RU', { maximumFractionDigits: 1 });
const byLevels = (f: (level: number) => number | string) => ROOM_LEVELS.map(f).join(' / ');
const professionBonus = (level: number) =>
  `опыт +${level * WORKSHOP_XP_PERCENT_PER_LEVEL}%, удвоение +${level * WORKSHOP_DOUBLE_PERCENT_PER_LEVEL}%`;

/** What one level of a room type gives — a short line for the build form and the room panel. */
export const levelPerk = (type: RoomType, level: number): string | null => {
  switch (type) {
    case 'storage': {
      const n = STORAGE_STACKS_BY_LEVEL[level] ?? 0;
      return `${n} ${cellsWord(n)}`;
    }
    case 'cellar': {
      const n = CELLAR_STACKS_BY_LEVEL[level] ?? 0;
      return `+${n} ${cellsWord(n)} к кладовой`;
    }
    case 'bedroom':
    case 'guest_room':
      return `сон ×${pct(BEDROOM_SLEEP_FACTOR_BY_LEVEL[level] ?? 1)}`;
    case 'library':
      return `до +${LIBRARY_CAP_PERCENT_BY_LEVEL[level] ?? 0}% опыта`;
    case 'shrine':
      return `благословение +${SHRINE_BONUS_PERCENT_BY_LEVEL[level] ?? 0}%`;
    case 'trophy_hall':
      return `${TROPHY_SLOTS_BY_LEVEL[level] ?? 0} мест для трофеев`;
    case 'return_circle':
      return `свиток сохраняется с шансом ${CIRCLE_KEEP_PERCENT_BY_LEVEL[level] ?? 0}%`;
    case 'garden':
    case 'greenhouse':
    case 'apiary': {
      const n = GARDEN_BEDS_BY_LEVEL[level] ?? 0;
      return `${n} ${bedsWord(type, n)}`;
    }
    case 'bath':
      return `восстановление ${BATH_RESTORE_PERCENT_BY_LEVEL[level] ?? 0}%`;
    case 'kitchen':
      return `сытость ${KITCHEN_SATIETY_HOURS_BY_LEVEL[level] ?? 24} ч, ${professionBonus(level)}`;
    default:
      return isProfessionRoom(type) ? professionBonus(level) : null;
  }
};

/** What a room type does across its levels — the explanation in the room panel. */
export const roomTypeHint = (type: RoomType): string => {
  const profession = roomProfessionName(type);
  const bonus = `опыт профессии +${byLevels((l) => l * WORKSHOP_XP_PERCENT_PER_LEVEL)}% и шанс удвоения при переработке +${
    byLevels((l) => l * WORKSHOP_DOUBLE_PERCENT_PER_LEVEL)} п.п. по уровню`;
  switch (type) {
    case 'hall':
      return 'Место для встреч и постов. Мебель здесь только украшает.';
    case 'bedroom':
      return `Во сне здесь восстановление быстрее: ×${byLevels((l) => pct(BEDROOM_SLEEP_FACTOR_BY_LEVEL[l] ?? 1))} по уровню.`;
    case 'guest_room':
      return `Комната для гостей хозяина: они спят здесь, как в спальне — восстановление ×${
        byLevels((l) => pct(BEDROOM_SLEEP_FACTOR_BY_LEVEL[l] ?? 1))} по уровню. Мебель спальни подходит и сюда.`;
    case 'library':
      return `Сядьте читать: каждый полный час чтения даёт +${LIBRARY_PERCENT_PER_HOUR}% ко всему опыту персонажа на `
        + `${HOUSE_BUFF_HOURS} ч после окончания, но не больше ${byLevels((l) => LIBRARY_CAP_PERCENT_BY_LEVEL[l] ?? 0)}% `
        + 'по уровню. Складывается с книгами опыта. Пока персонаж читает, он ничем другим не занят.';
    case 'shrine':
      return `Раз в ${SHRINE_COOLDOWN_HOURS} ч дарует на ${HOUSE_BUFF_HOURS} ч одно благословение на выбор — опыт сбора, `
        + `восстановление или опыт за посты: +${byLevels((l) => SHRINE_BONUS_PERCENT_BY_LEVEL[l] ?? 0)}% по уровню.`;
    case 'trophy_hall':
      return `Здесь вешают элитные трофеи: ${byLevels((l) => TROPHY_SLOTS_BY_LEVEL[l] ?? 0)} мест по уровню. `
        + `Каждый трофей даёт хозяину и жильцам +${TROPHY_PERCENT_PER_PIECE}% опыта за бои (всего не больше ${TROPHY_PERCENT_CAP}%).`;
    case 'return_circle':
      return 'Свиток возвращения переносит в дом с построенным кругом. С шансом '
        + `${byLevels((l) => CIRCLE_KEEP_PERCENT_BY_LEVEL[l] ?? 0)}% по уровню свиток не тратится.`;
    case 'storage':
      return `Общая кладовая дома: ${byLevels((l) => STORAGE_STACKS_BY_LEVEL[l] ?? 0)} ячеек по уровню.`;
    case 'cellar':
      return `Добавляет к кладовой дома ${byLevels((l) => CELLAR_STACKS_BY_LEVEL[l] ?? 0)} ячеек по уровню.`;
    case 'garden':
    case 'greenhouse':
    case 'apiary':
      return `${type === 'apiary' ? 'Ульи' : 'Грядки'} для семян: ${byLevels((l) => GARDEN_BEDS_BY_LEVEL[l] ?? 0)} по уровню. `
        + 'Посаженное растёт само; собрать урожай может тот, кто сажал, или хозяин.';
    case 'bath':
      return `Раз в ${BATH_COOLDOWN_HOURS} ч восстанавливает ${byLevels((l) => BATH_RESTORE_PERCENT_BY_LEVEL[l] ?? 0)}% `
        + 'здоровья, маны, энергии и выносливости по уровню.';
    case 'kitchen':
      return `Мастерская повара: ${bonus}. Еда, съеденная в доме, держит сытость `
        + `${byLevels((l) => KITCHEN_SATIETY_HOURS_BY_LEVEL[l] ?? 24)} ч вместо 24.`;
    default:
      return profession
        ? `Мастерская профессии «${profession}»: ${bonus}, когда персонаж этой профессии работает в локации дома.`
        : '';
  }
};

/** «3 ч 12 мин», «2 д 4 ч», «меньше минуты». */
export const formatLeft = (ms: number): string => {
  const total = Math.ceil(Math.max(0, ms) / MS_PER_MINUTE);
  if (total < 1) return 'меньше минуты';
  const d = Math.floor(total / MINUTES_PER_DAY);
  const h = Math.floor((total % MINUTES_PER_DAY) / MINUTES_PER_HOUR);
  const m = total % MINUTES_PER_HOUR;
  if (d > 0) return h > 0 ? `${d} д ${h} ч` : `${d} д`;
  if (h > 0) return m > 0 ? `${h} ч ${m} мин` : `${h} ч`;
  return `${m} мин`;
};

/** The largest unit only, for a compact button line: «7 ч», «2 д 4 ч», «12 мин». */
export const formatLeftShort = (ms: number): string => {
  const total = Math.ceil(Math.max(0, ms) / MS_PER_MINUTE);
  if (total < 1) return 'меньше минуты';
  if (total >= MINUTES_PER_DAY) return formatLeft(ms);
  if (total >= MINUTES_PER_HOUR) return `${Math.floor(total / MINUTES_PER_HOUR)} ч`;
  return `${total} мин`;
};

/** Build time of a cost step: «6 ч», «1 д 12 ч», «мгновенно». */
export const formatBuildHours = (hours: number): string => {
  if (hours <= 0) return 'мгновенно';
  const d = Math.floor(hours / HOURS_PER_DAY);
  const h = hours % HOURS_PER_DAY;
  if (d === 0) return `${h} ч`;
  return h > 0 ? `${d} д ${h} ч` : `${d} д`;
};

/** Milliseconds left until `iso`, ticking; calls `onDone` once it has passed. */
export const useTimeLeft = (iso: string | null, onDone?: () => void): number | null => {
  const end = parseServerDate(iso)?.getTime() ?? null;
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (end == null) return undefined;
    const tick = setInterval(() => setNow(Date.now()), COUNTDOWN_TICK_MS);
    const left = end - Date.now();
    const done = setTimeout(() => {
      setNow(Date.now());
      onDone?.();
    }, Math.max(0, left) + SETTLE_GRACE_MS);
    return () => {
      clearInterval(tick);
      clearTimeout(done);
    };
    // onDone is a reload callback; re-arming on its identity is unnecessary.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [end]);

  return end == null ? null : end - now;
};

interface BuildStatusProps {
  room: HouseRoom;
  /** Called when the build has finished (reload the house). */
  onDone?: () => void;
  className?: string;
}

/** «Строится до ур. 2 — осталось 3 ч 12 мин»; nothing when the room is not being built. */
export const BuildStatus = ({ room, onDone, className = '' }: BuildStatusProps) => {
  const left = useTimeLeft(room.upgrade_to_level != null ? room.upgrade_complete_at : null, onDone);
  if (room.upgrade_to_level == null) return null;
  const what = room.level === 0 ? 'Строится' : `Строится до ур. ${room.upgrade_to_level}`;
  return (
    <span className={`flex items-center gap-1 text-gold-light ${className}`}>
      <Hammer size={12} className="shrink-0" />
      {what}
      {left != null && (left > 0 ? ` — осталось ${formatLeft(left)}` : ' — почти готово')}
    </span>
  );
};

interface CostViewProps {
  cost: BuildCost | null;
  className?: string;
}

/** Gold, materials (with pictures) and build time of one step. */
export const CostView = ({ cost, className = '' }: CostViewProps) => {
  if (!cost) {
    return <p className={`text-white/40 text-xs ${className}`}>Стоимость не задана — обратитесь к администрации.</p>;
  }
  return (
    <div className={`flex flex-wrap items-center gap-x-3 gap-y-1.5 text-xs ${className}`}>
      <span className="flex items-center gap-1 text-gold">
        <Coins size={13} className="shrink-0" />{cost.gold.toLocaleString('ru-RU')} золота
      </span>
      {cost.items.map((item) => (
        <span key={item.item_id} className="flex items-center gap-1.5 text-white/75 min-w-0">
          <span className="w-6 h-6 rounded-[6px] overflow-hidden bg-black/40 border border-white/10 shrink-0 block">
            {item.image && <img src={item.image} alt="" className="w-full h-full object-cover" />}
          </span>
          <span className="truncate max-w-[160px]">{item.name ?? `Предмет #${item.item_id}`}</span>
          <span className="text-white/50">×{item.quantity}</span>
        </span>
      ))}
      <span className="flex items-center gap-1 text-white/55">
        <Clock size={13} className="shrink-0" />{formatBuildHours(cost.build_hours)}
      </span>
    </div>
  );
};
