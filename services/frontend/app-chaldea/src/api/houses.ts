import axios from 'axios';

/**
 * FEAT-180 — player houses: plots placed by admins in city locations, a house
 * bought on a plot, its rooms (role-play locations with posts), residents and
 * the shared storage (locations-service `/locations/houses`,
 * inventory-service `/inventory/houses`).
 */

export type RoomType =
  | 'hall'
  | 'bedroom'
  | 'storage'
  | 'cellar'
  | 'garden'
  | 'greenhouse'
  | 'apiary'
  | 'bath'
  | 'forge'
  | 'alchemy_lab'
  | 'kitchen'
  | 'jewelry'
  | 'enchanting'
  | 'study'
  | 'library'
  | 'shrine'
  | 'trophy_hall'
  | 'guest_room'
  | 'return_circle';

export const ROOM_TYPES: RoomType[] = [
  'hall', 'bedroom', 'storage', 'cellar', 'garden', 'greenhouse', 'apiary', 'bath',
  'forge', 'alchemy_lab', 'kitchen', 'jewelry', 'enchanting', 'study',
  'library', 'shrine', 'trophy_hall', 'guest_room', 'return_circle',
];

export const ROOM_TYPE_LABEL: Record<RoomType, string> = {
  hall: 'Гостиная',
  bedroom: 'Спальня',
  storage: 'Кладовая',
  cellar: 'Погреб',
  garden: 'Огород',
  greenhouse: 'Оранжерея',
  apiary: 'Пасека',
  bath: 'Баня',
  forge: 'Кузница',
  alchemy_lab: 'Алхимическая лаборатория',
  kitchen: 'Кухня',
  jewelry: 'Ювелирная мастерская',
  enchanting: 'Зал зачарования',
  study: 'Кабинет мистика',
  library: 'Библиотека',
  shrine: 'Святилище',
  trophy_hall: 'Трофейный зал',
  guest_room: 'Гостевая',
  return_circle: 'Круг возвращения',
};

/**
 * Stage 6a: furniture items keep `furniture_room_type` hall/bedroom/storage/workshop
 * and fit every room of that group (storage pieces fit a cellar, workshop
 * pieces any profession room). Rooms without a group take no furniture.
 */
export type FurnitureGroup = 'hall' | 'bedroom' | 'storage' | 'workshop';

export const FURNITURE_GROUPS: FurnitureGroup[] = ['hall', 'bedroom', 'storage', 'workshop'];

export const FURNITURE_GROUP_LABEL: Record<FurnitureGroup, string> = {
  hall: 'Гостиная',
  bedroom: 'Спальня',
  storage: 'Кладовая и погреб',
  workshop: 'Мастерская профессии',
};

/** Profession rooms and the profession (inventory `professions.slug`) each serves. */
export type ProfessionRoomType = 'forge' | 'alchemy_lab' | 'kitchen' | 'jewelry' | 'enchanting' | 'study';

export const PROFESSION_ROOMS: Record<ProfessionRoomType, string> = {
  forge: 'blacksmith',
  alchemy_lab: 'alchemist',
  kitchen: 'cook',
  jewelry: 'jeweler',
  enchanting: 'enchanter',
  study: 'scholar',
};

/** Russian names of the professions that profession rooms serve, by slug. */
export const PROFESSION_NAME_BY_SLUG: Record<string, string> = {
  blacksmith: 'Кузнец',
  alchemist: 'Алхимик',
  cook: 'Повар',
  jeweler: 'Ювелир',
  enchanter: 'Зачарователь',
  scholar: 'Мистик',
};

export const isProfessionRoom = (type: RoomType): type is ProfessionRoomType => type in PROFESSION_ROOMS;

/** Russian profession name of a profession room type, else null. */
export const roomProfessionName = (type: RoomType): string | null =>
  isProfessionRoom(type) ? PROFESSION_NAME_BY_SLUG[PROFESSION_ROOMS[type]] ?? null : null;

/** Rooms with beds where seeds are planted. */
export type GardenRoomType = 'garden' | 'greenhouse' | 'apiary';
export const GARDEN_ROOMS: GardenRoomType[] = ['garden', 'greenhouse', 'apiary'];
export const isGardenRoom = (type: string): type is GardenRoomType => (GARDEN_ROOMS as string[]).includes(type);
/** «в огороде», «на пасеке» — where a seed grows. */
export const GARDEN_ROOM_PLACE: Record<GardenRoomType, string> = {
  garden: 'в огороде',
  greenhouse: 'в оранжерее',
  apiary: 'на пасеке',
};

/** Rooms whose stacks make up the house storage. */
export const STORAGE_ROOMS: RoomType[] = ['storage', 'cellar'];

/** Layers of a house plan (stage 5): floors, the basement and the yard. */
export type HouseLayer = 'floor1' | 'floor2' | 'basement' | 'yard';

export const HOUSE_LAYERS: HouseLayer[] = ['floor1', 'floor2', 'basement', 'yard'];

export const LAYER_LABEL: Record<HouseLayer, string> = {
  floor1: '1 этаж',
  floor2: '2 этаж',
  basement: 'Подвал',
  yard: 'Двор',
};

/** Layers each room type may stand on (mirrors the backend's ROOM_LAYERS). */
export const ROOM_LAYERS: Record<RoomType, HouseLayer[]> = {
  hall: ['floor1', 'floor2'],
  bedroom: ['floor1', 'floor2'],
  storage: ['floor1', 'floor2', 'basement'],
  cellar: ['basement'],
  garden: ['yard'],
  greenhouse: ['yard'],
  apiary: ['yard'],
  bath: ['yard', 'floor1'],
  forge: ['yard', 'floor1'],
  alchemy_lab: ['basement', 'floor1', 'floor2'],
  kitchen: ['floor1'],
  jewelry: ['floor1', 'floor2'],
  enchanting: ['floor1', 'floor2', 'basement'],
  study: ['floor1', 'floor2'],
  library: ['floor1', 'floor2'],
  shrine: ['floor1', 'floor2', 'yard'],
  trophy_hall: ['floor1', 'floor2'],
  guest_room: ['floor1', 'floor2'],
  return_circle: ['yard', 'basement', 'floor1'],
};

/** Room types allowed on a layer, in ROOM_TYPES order. */
export const layerRoomTypes = (layer: HouseLayer): RoomType[] =>
  ROOM_TYPES.filter((t) => ROOM_LAYERS[t].includes(layer));

/** Plan grid size limits (both sides). */
export const PLAN_GRID_MIN = 1;
export const PLAN_GRID_MAX = 6;

export type PlanCellKind = 'open' | 'extension';

export interface PlanLayer {
  layer: HouseLayer;
  label: string;
  /** Price the owner pays to open the layer, null = free. */
  unlock_price: number | null;
  unlocked: boolean;
}

export interface PlanCell {
  id: number;
  layer: HouseLayer;
  x: number;
  y: number;
  kind: PlanCellKind;
  /** Effective room types for this cell. */
  allowed_types: RoomType[];
  /** Usable now: its layer is open and (for an extension) it is bought. */
  unlocked: boolean;
  room_id: number | null;
}

/** The grid of a plot / house (stage 5). Positions without a cell are not buildable. */
export interface HousePlan {
  width: number;
  height: number;
  /** Price of one extension place, null when the plot has none. */
  extension_price: number | null;
  /** Ordered floor1, floor2, basement, yard; only the plot's layers. */
  layers: PlanLayer[];
  cells: PlanCell[];
}

/** Places of a plan: usable now, taken by rooms, all of them. */
export const planStats = (plan: HousePlan) => ({
  usable: plan.cells.filter((c) => c.unlocked).length,
  taken: plan.cells.filter((c) => c.room_id != null).length,
  total: plan.cells.length,
});

export type PlotKind = 'ready' | 'empty';

export const PLOT_KIND_LABEL: Record<PlotKind, string> = {
  ready: 'Готовый дом',
  empty: 'Пустой участок',
};

/** Highest room level (levels 1..3; 0 = being built for the first time). */
export const MAX_ROOM_LEVEL = 3;
export const ROOM_LEVELS = [1, 2, 3] as const;

/** Item stacks one storage room holds, by its level. */
export const STORAGE_STACKS_BY_LEVEL: Record<number, number> = { 1: 30, 2: 45, 3: 60 };
/** Item stacks a cellar adds to the house storage, by its level. */
export const CELLAR_STACKS_BY_LEVEL: Record<number, number> = { 1: 50, 2: 75, 3: 100 };
/** Beds of a garden, greenhouse or apiary, by its level. */
export const GARDEN_BEDS_BY_LEVEL: Record<number, number> = { 1: 4, 2: 8, 3: 12 };
/** Percent of max health, mana, energy and stamina a bath restores, by its level. */
export const BATH_RESTORE_PERCENT_BY_LEVEL: Record<number, number> = { 1: 20, 2: 35, 3: 50 };
/** How often one character may bathe. */
export const BATH_COOLDOWN_HOURS = 24;
/** Satiety of food eaten at the house, by the kitchen level (24 h elsewhere). */
export const KITCHEN_SATIETY_HOURS_BY_LEVEL: Record<number, number> = { 1: 30, 2: 36, 3: 48 };
/** Rest multiplier while sleeping in a bedroom, by its level. */
export const BEDROOM_SLEEP_FACTOR_BY_LEVEL: Record<number, number> = { 1: 2, 2: 2.5, 3: 3 };
/** Profession room bonus per level: profession XP % and doubling chance % when refining. */
export const WORKSHOP_XP_PERCENT_PER_LEVEL = 10;
export const WORKSHOP_DOUBLE_PERCENT_PER_LEVEL = 5;

/* ── Stage 6b: library, shrine, trophy hall, guest room, return circle ── */

/** Rooms one sleeps in (a guest room sleeps like a bedroom of its level). */
export const SLEEP_ROOMS: RoomType[] = ['bedroom', 'guest_room'];
export const isSleepRoom = (type: RoomType): boolean => SLEEP_ROOMS.includes(type);
/** Each full hour read: +1 % to all character XP for 24 h, up to the library cap (percent) by level. */
export const LIBRARY_CAP_PERCENT_BY_LEVEL: Record<number, number> = { 1: 5, 2: 7, 3: 10 };
export const LIBRARY_PERCENT_PER_HOUR = 1;
/** A shrine blessing (percent) by level, for 24 h, once per 24 h. */
export const SHRINE_BONUS_PERCENT_BY_LEVEL: Record<number, number> = { 1: 5, 2: 10, 3: 15 };
export const HOUSE_BUFF_HOURS = 24;
export const SHRINE_COOLDOWN_HOURS = 24;
/** Elite trophies a trophy hall holds by level; each +1 % battle XP, at most 15 % in all. */
export const TROPHY_SLOTS_BY_LEVEL: Record<number, number> = { 1: 5, 2: 10, 3: 15 };
export const TROPHY_PERCENT_PER_PIECE = 1;
export const TROPHY_PERCENT_CAP = 15;
/** Chance (percent) a return circle keeps the home teleport scroll, by level. */
export const CIRCLE_KEEP_PERCENT_BY_LEVEL: Record<number, number> = { 1: 0, 2: 15, 3: 30 };

export type ShrineBlessing = 'gathering_xp' | 'regen' | 'post_xp';
export const SHRINE_BLESSINGS: ShrineBlessing[] = ['gathering_xp', 'regen', 'post_xp'];
export const SHRINE_BLESSING_LABEL: Record<ShrineBlessing, string> = {
  gathering_xp: 'Опыт сбора',
  regen: 'Восстановление',
  post_xp: 'Опыт за посты',
};

export type HouseBuffSource = 'library' | 'shrine';
export type HouseBuffKind = 'character_xp' | ShrineBlessing;
export const HOUSE_BUFF_KIND_LABEL: Record<HouseBuffKind, string> = {
  character_xp: 'весь опыт',
  gathering_xp: 'опыт сбора',
  regen: 'восстановление',
  post_xp: 'опыт за посты',
};

/** A running house blessing; `value` is a fraction (0.03 = 3 %). */
export interface HouseBuff {
  source: HouseBuffSource;
  kind: HouseBuffKind;
  value: number;
  expires_at: string;
}

export interface HouseBuffs {
  buffs: HouseBuff[];
  /** Battle XP bonus from the trophy halls of the character's home (fraction). */
  trophy_bonus: number;
}

/** A fraction from the API as a percent: 0.05 → 5, 0.075 → 7.5. */
export const fractionToPercent = (f: number | null | undefined): number => Math.round((f ?? 0) * 1000) / 10;
/** «5», «7,5» — a fraction from the API written as a Russian percent number. */
export const percentText = (f: number | null | undefined): string =>
  fractionToPercent(f).toLocaleString('ru-RU', { maximumFractionDigits: 1 });

/** Shortest post (plain text) the server accepts in a room. */
export const MIN_ROOM_POST_LENGTH = 300;

export interface HouseChar {
  id: number;
  name: string;
  avatar: string | null;
  user_id?: number | null;
}

export interface Plot {
  id: number;
  location_id: number;
  location_name: string | null;
  region_id: number | null;
  name: string;
  description: string;
  image_url: string | null;
  price: number;
  kind: PlotKind;
  room_count: number;
  /** Places usable right after purchase. */
  cells_open: number;
  /** All places incl. extensions and paid layers. */
  cells_total: number;
  map_x: number | null;
  map_y: number | null;
  house: null | {
    id: number;
    name: string;
    image_url: string | null;
    owner: HouseChar | null;
    /** Stage 4: frozen for an unpaid tax (seized houses are not listed). */
    status?: HouseStatus;
    /** Asking price while the owner sells it on the board, else null. */
    sale_price?: number | null;
  };
}

export interface TemplateRoom {
  room_type: RoomType;
  name: string;
  description: string;
  image_url: string | null;
  /** The plan cell the template room stands on. */
  cell_id?: number | null;
}

export interface PlotDetail extends Plot {
  rooms: TemplateRoom[];
  /** Plan without house state (unlocked = free layer && open cell, room_id null). */
  plan: HousePlan;
  grid_w: number;
  grid_h: number;
  extension_price: number | null;
}

export interface MyHouse {
  id: number;
  name: string;
  image_url: string | null;
  /** Stage 6b: 'guest' — the character is invited into the guest rooms. */
  status: 'owner' | 'resident' | 'guest';
  character: HouseChar | null;
  location_id: number | null;
  location_name: string | null;
}

export interface ActingCharacter {
  character: HouseChar | null;
  is_owner: boolean;
  room_ids: number[];
  can_take: boolean;
  can_put: boolean;
  /** Where this character stands now. */
  location_id?: number | null;
  /** The bedroom this character sleeps in, or null. */
  asleep_room_id?: number | null;
  /** When this character may bathe again (server time); null = now. */
  bath_next_at?: string | null;
  /** Stage 6b: a guest acts only in the guest rooms (can_take/can_put false). */
  is_guest?: boolean;
  /** The library this character reads in, or null. */
  reading_room_id?: number | null;
  /** Since when it reads (server time). */
  reading_since?: string | null;
  /** When it may pray again (server time); null = now. */
  pray_next_at?: string | null;
  /** Its running house blessings. */
  buffs?: HouseBuff[];
  /** Battle XP bonus of its home's trophy halls (fraction; 0 for guests). */
  trophy_bonus?: number;
  /** Stage 7: the room of this house the character stands in now, or null (outside). */
  room_id?: number | null;
}

/** An item reference in garden data. */
export interface GardenItem {
  id: number;
  name: string;
  image: string | null;
}

/** A planted bed of a garden, greenhouse or apiary (empty beds are absent). */
export interface GardenBed {
  /** 1-based. */
  bed_no: number;
  planted_by: HouseChar | null;
  seed: GardenItem | null;
  result: GardenItem | null;
  quantity: number;
  planted_at: string;
  ready_at: string;
  ready: boolean;
}

/** A seed stack in the bag that grows in a given room. */
export interface SeedOption {
  inventory_item_id: number;
  item_id: number;
  name: string;
  image: string | null;
  quantity: number;
  grow_hours: number;
  result: GardenItem | null;
  result_quantity: number;
  herbalism_xp: number;
}

export interface HarvestResult {
  added: number;
  quantity: number;
  item: GardenItem | null;
  xp_awarded: number;
  rank_up: boolean;
}

export interface BatheResult {
  restored: { health: number; mana: number; energy: number; stamina: number };
  next_at: string;
}

export interface HouseRoom {
  id: number;
  room_type: RoomType;
  name: string;
  description: string;
  image_url: string | null;
  is_open: boolean;
  posts_count: number;
  /** The plan cell the room stands on (null only for odd legacy data). */
  cell_id: number | null;
  can_enter: boolean;
  can_read: boolean;
  /** 0 = being built for the first time, then 1..3. */
  level: number;
  /** Target level while a build/upgrade is in progress, else null. */
  upgrade_to_level: number | null;
  /** End of the build (server time), null unless in progress. */
  upgrade_complete_at: string | null;
  workshop_profession_id: number | null;
  /** The furniture this room takes; null = none. */
  furniture_group: FurnitureGroup | null;
  /** Profession rooms: the profession slug that gets the bonus, else null. */
  profession_slug: string | null;
  /** Garden rooms: beds of the current level, else null. */
  beds_total: number | null;
  /** Garden rooms: the planted beds, else null. */
  beds: GardenBed[] | null;
  /** Bedrooms and guest rooms: rest multiplier of the current level incl. furniture, null otherwise. */
  sleep_factor: number | null;
  /** Stage 6b: pieces the room holds (its level, or a trophy hall's trophy slots). */
  furniture_slots?: number;
  /** Library: the blessing cap of the current level (fraction), else null. */
  library_cap?: number | null;
  /** Shrine: the blessing value of the current level (fraction), else null. */
  shrine_bonus?: number | null;
  /** Trophy hall: elite trophy slots of the current level, else null. */
  trophy_slots?: number | null;
  /** Return circle: chance to keep the scroll (fraction), else null. */
  circle_keep_chance?: number | null;
  /** Furniture placed here; slots = `level` (0 while first built). */
  furniture: RoomFurniture[];
  /** Storage rooms and cellars: total stacks incl. furniture, null otherwise. */
  storage_stacks: number | null;
  /** Stage 7: who stands in this room now. */
  present?: HouseChar[];
}

/** A piece of furniture placed in a room (FEAT-180 stage 3). */
export interface RoomFurniture {
  id: number;
  item_id: number;
  name: string;
  image: string | null;
  rarity: string | null;
  description: string | null;
  sleep_bonus: number;
  storage_stacks: number;
  xp_bonus_pct: number;
  refine_bonus_pct: number;
}

export interface HouseResident {
  id: number;
  character: HouseChar | null;
  room_ids: number[];
  can_take: boolean;
  can_put: boolean;
}

/** Stage 4: a seized house is gone for players (the API answers 404). */
export type HouseStatus = 'active' | 'frozen';

/** What happens when the current tax period ends unpaid. */
export type TaxNextStep = 'freeze' | 'seize';

export interface HouseTax {
  /** Tax for one period (a game season with its transition). */
  per_season: number;
  /** Unpaid periods: 0 — paid, 1 — this season owed, 2 — frozen. */
  owed_periods: number;
  /** Gold to pay now (all owed periods). */
  due: number;
  /** End of the current tax period (server time, UTC). */
  period_ends_at: string;
  next_step: TaxNextStep | null;
}

export interface House {
  id: number;
  status: HouseStatus;
  tax: HouseTax;
  /** The resident who inherits the house when the owner character is deleted. */
  heir: HouseChar | null;
  /** Asking price while listed on the sale board, else null. */
  sale_price: number | null;
  name: string;
  description: string;
  image_url: string | null;
  plot_id: number;
  plot_kind: PlotKind;
  plan: HousePlan;
  location_id: number;
  location_name: string | null;
  owner: HouseChar | null;
  is_owner: boolean;
  acting: ActingCharacter[];
  rooms: HouseRoom[];
  residents: HouseResident[];
  /** Stage 6b: battle XP bonus the trophy halls give owner and residents (fraction). */
  trophy_bonus?: number;
  /** Invited guests (shown to the owner, residents and admins). */
  guests?: HouseGuest[];
  /** Stage 7: the viewer sees inside (owner, resident, guest or staff). */
  can_view_inside: true;
}

/**
 * Stage 7: what an outsider (or an anonymous visitor) sees of a house — the
 * facade only; inside fields come back empty.
 */
export interface HouseFacade {
  id: number;
  name: string;
  description: string;
  image_url: string | null;
  plot_id: number;
  plot_kind: PlotKind;
  status: HouseStatus;
  sale_price: number | null;
  location_id: number;
  location_name: string | null;
  owner: HouseChar | null;
  is_owner: false;
  can_view_inside: false;
}

export type HouseView = House | HouseFacade;

/** Stage 7: where the character stands after entering / moving (room_id null after leaving). */
export interface HousePresence {
  house_id: number;
  room_id: number | null;
  room_type?: RoomType;
  room_name?: string;
}

export interface HouseGuest {
  character: HouseChar | null;
  invited_at: string;
}

/** A house the character's home teleport scroll may carry it to. */
export interface HomeTeleportTarget {
  house_id: number;
  name: string;
  location_id: number;
  location_name: string | null;
  circle_level: number;
  /** Chance the circle keeps the scroll (fraction). */
  keep_chance: number;
}

export interface HomeTeleportResult {
  location_id: number;
  location_name: string | null;
  scroll_kept: boolean;
  /** Stage 7: the character lands in the house's return circle. */
  house_id?: number | null;
  house_room_id?: number | null;
}

export interface StopReadingResult {
  reading: false;
  hours: number;
  /** Earned now (fraction). */
  bonus: number;
  /** The resulting library blessing (fraction), 0 when under 1 %. */
  value: number;
  expires_at: string | null;
}

export interface RoomPost {
  id: number;
  content: string;
  created_at: string;
  edited_at: string | null;
  character: HouseChar | null;
  can_edit: boolean;
  can_delete: boolean;
}

export interface RoomView {
  room: {
    id: number;
    house_id: number;
    house_name: string;
    room_type: RoomType;
    name: string;
    description: string;
    image_url: string | null;
    is_open: boolean;
    level?: number;
    beds_total?: number | null;
    beds?: GardenBed[] | null;
  };
  /** Stage 7: `in_room` — the writer stands in this room (posting needs it). */
  writers: (HouseChar & { in_room?: boolean })[];
  /** Stage 7: who stands in this room now. */
  present?: HouseChar[];
  posts: RoomPost[];
  has_more: boolean;
}

export interface PlotLayerInput {
  layer: HouseLayer;
  unlock_price?: number | null;
}

export interface PlotCellInput {
  layer: HouseLayer;
  x: number;
  y: number;
  kind?: PlanCellKind;
  /** Empty = every type the layer allows. */
  allowed_types?: RoomType[];
}

export interface PlotRoomInput {
  room_type: RoomType;
  name: string;
  description: string;
  image_url: string | null;
  layer: HouseLayer;
  x: number;
  y: number;
}

export interface PlotInput {
  location_id: number;
  name: string;
  description: string;
  image_url: string | null;
  price: number;
  map_x: number | null;
  map_y: number | null;
  kind: PlotKind;
  grid_w: number;
  grid_h: number;
  extension_price: number | null;
  layers: PlotLayerInput[];
  cells: PlotCellInput[];
  rooms: PlotRoomInput[];
}

export interface BuildCostItem {
  item_id: number;
  quantity: number;
  name: string | null;
  image: string | null;
}

/** Price of building a room type up to `level` (level 1 = the first build). */
export interface BuildCost {
  room_type: RoomType;
  level: number;
  gold: number;
  build_hours: number;
  items: BuildCostItem[];
}

export interface BuildCostInput {
  gold: number;
  build_hours: number;
  items: { item_id: number; quantity: number }[];
}

export interface StorageItem {
  id: number;
  item_id: number;
  quantity: number;
  name: string;
  description: string | null;
  image_url: string | null;
  item_type: string | null;
  rarity: string | null;
  max_stack_size: number;
  is_identified: boolean;
  enhancement_points_spent: number;
  current_durability: number | null;
  max_durability: number;
}

export interface StorageState {
  can_take: boolean;
  can_put: boolean;
  capacity: number;
  at_house: boolean;
  /** Stage 7: the character stands in a storage or cellar of this house (put/take need it). */
  in_storage?: boolean;
  used: number;
  items: StorageItem[];
}

/** A house on the sale board (stage 4). */
export interface MarketHouse {
  id: number;
  name: string;
  image_url: string | null;
  price: number;
  listed_at: string | null;
  location_id: number;
  location_name: string | null;
  owner: HouseChar | null;
  cells: { usable: number; taken: number; total: number };
  rooms: { room_type: RoomType; name: string; level: number }[];
  furniture_count: number;
  stored_stacks: number;
  tax_per_season: number;
}

export interface HouseSettings {
  tax_price_pct: number;
  tax_per_room_level: number;
  tax_period_days: number;
}

export type SeizeReason = 'tax' | 'no_heir';

export const SEIZE_REASON_LABEL: Record<SeizeReason, string> = {
  tax: 'за неуплату налога',
  no_heir: 'хозяин удалён без наследника',
};

/** A house the city took away (admin archive). */
export interface SeizedHouse {
  id: number;
  name: string;
  owner: HouseChar | null;
  seized_at: string | null;
  reason: SeizeReason | null;
  location_name: string | null;
  rooms: { room_type: RoomType; name: string; level: number }[];
  furniture: string[];
  stored_stacks: number;
}

/** Server detail of a seized house's 404. */
export const SEIZED_HOUSE_DETAIL = 'Дом изъят городом';

const BASE = '/locations/houses';
const STORAGE = '/inventory/houses';
const INVENTORY = '/inventory';

// --- Plots & buying ---

export const plotsAtLocation = async (locationId: number) =>
  (await axios.get<Plot[]>(`${BASE}/by-location/${locationId}`)).data;
export const plotsInRegion = async (regionId: number) =>
  (await axios.get<Plot[]>(`${BASE}/by-region/${regionId}`)).data;
export const getPlot = async (plotId: number) => (await axios.get<PlotDetail>(`${BASE}/plots/${plotId}`)).data;
export const buyPlot = async (plotId: number, characterId: number) =>
  (await axios.post<{ house_id: number; gold: number }>(`${BASE}/plots/${plotId}/buy`, { character_id: characterId })).data;

// --- Houses ---

export const myHouses = async () => (await axios.get<MyHouse[]>(`${BASE}/my`)).data;
export const searchCharacters = async (q: string) =>
  (await axios.get<HouseChar[]>(`${BASE}/character-search`, { params: { q } })).data;
export const getHouse = async (houseId: number) => (await axios.get<HouseView>(`${BASE}/${houseId}`)).data;

// --- Presence inside the house (stage 7) ---

/** Steps into the house: into `roomId` or the first built room the character is let into. */
export const enterHouse = async (houseId: number, characterId: number, roomId?: number) =>
  (await axios.post<HousePresence>(`${BASE}/${houseId}/enter`, {
    character_id: characterId,
    ...(roomId != null ? { room_id: roomId } : {}),
  })).data;
/** Moves to another room of the same house — instant and free; also enters straight into it. */
export const goToRoom = async (roomId: number, characterId: number) =>
  (await axios.post<HousePresence>(`${BASE}/rooms/${roomId}/go`, { character_id: characterId })).data;
export const leaveHouse = async (houseId: number, characterId: number) =>
  (await axios.post<HousePresence>(`${BASE}/${houseId}/leave`, { character_id: characterId })).data;
export const updateHouse = async (
  houseId: number,
  body: { character_id: number; name: string; description: string; image_url: string | null },
) => axios.put(`${BASE}/${houseId}`, body);
export const updateRoom = async (
  houseId: number,
  roomId: number,
  body: {
    character_id: number;
    name: string;
    description: string;
    image_url: string | null;
    is_open: boolean;
  },
) => axios.put(`${BASE}/${houseId}/rooms/${roomId}`, body);

// --- Building & sleep ---

export const getBuildCosts = async () => (await axios.get<BuildCost[]>(`${BASE}/build-costs`)).data;
export const buildRoom = async (houseId: number, characterId: number, roomType: RoomType, name: string, cellId: number) =>
  (await axios.post<{ room_id: number }>(`${BASE}/${houseId}/rooms`, {
    character_id: characterId,
    room_type: roomType,
    name,
    cell_id: cellId,
  })).data;
/** The owner, standing at the house, pays the layer's unlock price (e.g. a second floor). */
export const unlockLayer = async (houseId: number, layer: HouseLayer, characterId: number) =>
  axios.post(`${BASE}/${houseId}/layers/${layer}/unlock`, { character_id: characterId });
/** The owner buys one extension place at the plot's extension price. */
export const unlockCell = async (houseId: number, cellId: number, characterId: number) =>
  axios.post(`${BASE}/${houseId}/cells/${cellId}/unlock`, { character_id: characterId });
export const upgradeRoom = async (houseId: number, roomId: number, characterId: number) =>
  axios.post(`${BASE}/${houseId}/rooms/${roomId}/upgrade`, { character_id: characterId });
export const demolishRoom = async (houseId: number, roomId: number, characterId: number) =>
  axios.delete(`${BASE}/${houseId}/rooms/${roomId}`, { params: { character_id: characterId } });
export const sleepInRoom = async (roomId: number, characterId: number) =>
  (await axios.post<{ asleep: boolean; sleep_factor: number }>(`${BASE}/rooms/${roomId}/sleep`, {
    character_id: characterId,
  })).data;
/** Wakes the character wherever it sleeps. */
export const wakeUp = async (characterId: number) =>
  (await axios.post<{ asleep: boolean }>(`${BASE}/wake`, { character_id: characterId })).data;

// --- Gardens & bath (stage 6a) ---

/** The character's seeds that grow in this garden room. */
export const getRoomSeeds = async (roomId: number, characterId: number) =>
  (await axios.get<SeedOption[]>(`${BASE}/rooms/${roomId}/seeds`, { params: { character_id: characterId } })).data;
export const plantSeed = async (roomId: number, characterId: number, inventoryItemId: number, bedNo?: number) =>
  (await axios.post<{ bed_no: number; ready_at: string }>(`${BASE}/rooms/${roomId}/plant`, {
    character_id: characterId,
    inventory_item_id: inventoryItemId,
    ...(bedNo != null ? { bed_no: bedNo } : {}),
  })).data;
/** The planter or the owner gathers a grown bed into the bag. */
export const harvestBed = async (roomId: number, characterId: number, bedNo: number) =>
  (await axios.post<HarvestResult>(`${BASE}/rooms/${roomId}/harvest`, { character_id: characterId, bed_no: bedNo })).data;
export const batheInRoom = async (roomId: number, characterId: number) =>
  (await axios.post<BatheResult>(`${BASE}/rooms/${roomId}/bathe`, { character_id: characterId })).data;

// --- Library, shrine, buffs, guests (stage 6b) ---

export const startReading = async (roomId: number, characterId: number) =>
  (await axios.post<{ reading: true; reading_since: string; cap: number }>(`${BASE}/rooms/${roomId}/read`, {
    character_id: characterId,
  })).data;
/** Ends reading wherever the character reads; the earned library blessing is granted. */
export const stopReading = async (characterId: number) =>
  (await axios.post<StopReadingResult>(`${BASE}/stop-reading`, { character_id: characterId })).data;
export const prayAtShrine = async (roomId: number, characterId: number, blessing: ShrineBlessing) =>
  (await axios.post<{ blessing: ShrineBlessing; value: number; expires_at: string; next_at: string }>(
    `${BASE}/rooms/${roomId}/pray`, { character_id: characterId, blessing },
  )).data;
export const getHouseBuffs = async (characterId: number) =>
  (await axios.get<HouseBuffs>(`${BASE}/buffs`, { params: { character_id: characterId } })).data;
export const inviteGuest = async (houseId: number, ownerCharacterId: number, guestCharacterId: number) =>
  (await axios.post<{ id: number }>(`${BASE}/${houseId}/guests`, {
    character_id: ownerCharacterId,
    guest_character_id: guestCharacterId,
  })).data;
/** The owner sends a guest away, or the guest's own character leaves. */
export const removeGuest = async (houseId: number, guestCharacterId: number, characterId: number) =>
  axios.delete(`${BASE}/${houseId}/guests/${guestCharacterId}`, { params: { character_id: characterId } });

/** The stop-reading result as a toast line. */
export const stopReadingText = (r: StopReadingResult): string => {
  if (r.bonus <= 0 || r.value <= 0) return 'Чтение: меньше часа — бонуса нет';
  const held = fractionToPercent(r.value) > fractionToPercent(r.bonus)
    ? ` (действует прежнее +${percentText(r.value)} %, срок обновлён)`
    : '';
  return `Чтение: ${r.hours} ч — +${percentText(r.bonus)} % ко всему опыту на ${HOUSE_BUFF_HOURS} ч${held}`;
};

// --- Furniture ---

/** Puts a furniture item from the owner's bag into a room. */
export const placeFurniture = async (houseId: number, roomId: number, characterId: number, inventoryItemId: number) =>
  axios.post(`${BASE}/${houseId}/rooms/${roomId}/furniture`, {
    character_id: characterId,
    inventory_item_id: inventoryItemId,
  });
/** Takes a piece back into the owner's bag. */
export const removeFurniture = async (houseId: number, roomId: number, furnitureId: number, characterId: number) =>
  axios.delete(`${BASE}/${houseId}/rooms/${roomId}/furniture/${furnitureId}`, { params: { character_id: characterId } });

/** Cost of building `roomType` up to `level`, if configured. */
export const findCost = (costs: BuildCost[], roomType: RoomType, level: number) =>
  costs.find((c) => c.room_type === roomType && c.level === level) ?? null;

export const addResident = async (houseId: number, ownerCharacterId: number, residentCharacterId: number) =>
  (await axios.post<{ id: number }>(`${BASE}/${houseId}/residents`, {
    character_id: ownerCharacterId,
    resident_character_id: residentCharacterId,
  })).data;
export const updateResident = async (
  houseId: number,
  residentId: number,
  body: { character_id: number; room_ids: number[]; can_take: boolean; can_put: boolean },
) => axios.put(`${BASE}/${houseId}/residents/${residentId}`, body);
/** The owner evicts a resident, or the resident's own character moves out. */
export const removeResident = async (houseId: number, residentId: number, characterId: number) =>
  axios.delete(`${BASE}/${houseId}/residents/${residentId}`, { params: { character_id: characterId } });

// --- Rooms & posts ---

export const getRoom = async (roomId: number, beforeId?: number) =>
  (await axios.get<RoomView>(`${BASE}/rooms/${roomId}`, { params: beforeId ? { before_id: beforeId } : undefined })).data;
export const createRoomPost = async (roomId: number, characterId: number, content: string) =>
  (await axios.post<RoomPost>(`${BASE}/rooms/${roomId}/posts`, { character_id: characterId, content })).data;
export const editRoomPost = async (postId: number, content: string) =>
  (await axios.put<RoomPost>(`${BASE}/posts/${postId}`, { content })).data;
export const deleteRoomPost = async (postId: number) => axios.delete(`${BASE}/posts/${postId}`);

// --- Tax, heir, sale board (stage 4) ---

/** The owner or a resident pays every owed tax period. */
export const payTax = async (houseId: number, characterId: number) =>
  (await axios.post<{ paid: number }>(`${BASE}/${houseId}/tax`, { character_id: characterId })).data;
export const setHeir = async (houseId: number, ownerCharacterId: number, heirCharacterId: number | null) =>
  axios.put(`${BASE}/${houseId}/heir`, { character_id: ownerCharacterId, heir_character_id: heirCharacterId });
export const putUpForSale = async (houseId: number, ownerCharacterId: number, price: number) =>
  axios.put(`${BASE}/${houseId}/sale`, { character_id: ownerCharacterId, price });
export const takeOffSale = async (houseId: number, ownerCharacterId: number) =>
  axios.delete(`${BASE}/${houseId}/sale`, { params: { character_id: ownerCharacterId } });
export const getMarket = async () => (await axios.get<MarketHouse[]>(`${BASE}/market`)).data;
/** Buys a listed house; the character must stand in the house's location. */
export const buyListedHouse = async (houseId: number, characterId: number) =>
  (await axios.post<{ house_id: number; gold: number }>(`${BASE}/${houseId}/buy`, { character_id: characterId })).data;

// --- Admin ---

export const adminListPlots = async () => (await axios.get<Plot[]>(`${BASE}/admin/plots`)).data;
export const adminCreatePlot = async (body: PlotInput) =>
  (await axios.post<{ id: number }>(`${BASE}/admin/plots`, body)).data;
export const adminUpdatePlot = async (plotId: number, body: PlotInput) =>
  (await axios.put<{ id: number }>(`${BASE}/admin/plots/${plotId}`, body)).data;
export const adminDeletePlot = async (plotId: number) => axios.delete(`${BASE}/admin/plots/${plotId}`);
export const adminGetHouseSettings = async () => (await axios.get<HouseSettings>(`${BASE}/admin/settings`)).data;
export const adminSetHouseSettings = async (body: { tax_price_pct: number; tax_per_room_level: number }) =>
  axios.put(`${BASE}/admin/settings`, body);
export const adminGetSeizedHouses = async () => (await axios.get<SeizedHouse[]>(`${BASE}/admin/seized`)).data;
export const adminSetBuildCost = async (roomType: RoomType, level: number, body: BuildCostInput) =>
  axios.put(`${BASE}/admin/build-costs/${roomType}/${level}`, body);

// --- Storage (inventory-service) ---

export const getStorage = async (houseId: number, characterId: number) =>
  (await axios.get<StorageState>(`${STORAGE}/${houseId}/storage`, { params: { character_id: characterId } })).data;
export const putIntoStorage = async (houseId: number, characterId: number, inventoryItemId: number, quantity: number) =>
  (await axios.post<StorageState>(`${STORAGE}/${houseId}/storage/put`, {
    character_id: characterId,
    inventory_item_id: inventoryItemId,
    quantity,
  })).data;
export const takeFromStorage = async (houseId: number, characterId: number, storageItemId: number, quantity: number) =>
  (await axios.post<StorageState>(`${STORAGE}/${houseId}/storage/take`, {
    character_id: characterId,
    storage_item_id: storageItemId,
    quantity,
  })).data;

// --- Home teleport scroll (inventory-service, stage 6b) ---

export const getHomeTeleportTargets = async (characterId: number) =>
  (await axios.get<HomeTeleportTarget[]>(`${INVENTORY}/${characterId}/home-teleport/targets`)).data;
export const homeTeleport = async (characterId: number, inventoryItemId: number, houseId: number) =>
  (await axios.post<HomeTeleportResult>(`${INVENTORY}/${characterId}/home-teleport`, {
    inventory_item_id: inventoryItemId,
    house_id: houseId,
  })).data;
