/**
 * FEAT-196 — per-level growth of resource maximums, by class (subclass ignored).
 *
 * MIRRORS the backend rate table in
 * `services/character-attributes-service/app/constants.py`
 * (`MAIN_RESOURCE_PER_LEVEL`, `OTHER_RESOURCE_PER_LEVEL`, `CLASS_MAIN_RESOURCE`)
 * and `crud.py::level_resource_bonus`. Change both together.
 *
 *   bonus(resource) = level × rate(class, resource)
 *   rate = 15 for the class's main resource, 10 for the other three.
 *
 * The bonus is NOT a stat: it is added to the resource maximum after the
 * soft/hard cap (FEAT-195), so the cap never cuts it.
 */

export type GrowthResource = 'health' | 'mana' | 'energy' | 'stamina';

export const GROWTH_RESOURCES: readonly GrowthResource[] = ['health', 'mana', 'energy', 'stamina'];

/** Main resource of the class grows this much per level. */
export const MAIN_RESOURCE_PER_LEVEL = 15;
/** Every other resource grows this much per level. */
export const OTHER_RESOURCE_PER_LEVEL = 10;

/** Class id → its main resource: 1 Воин, 2 Ловкач (плут), 3 Маг. */
export const CLASS_MAIN_RESOURCE: Readonly<Record<number, GrowthResource>> = {
  1: 'health',
  2: 'energy',
  3: 'mana',
};

const RESOURCE_LABELS: Record<GrowthResource, string> = {
  health: 'здоровье',
  mana: 'мана',
  energy: 'энергия',
  stamina: 'выносливость',
};

const isKnownClass = (classId: number | null | undefined): classId is number =>
  typeof classId === 'number' && classId in CLASS_MAIN_RESOURCE;

/** Per-level rate of `resource` for the class; unknown class → 0. */
export const levelResourceRate = (
  resource: GrowthResource,
  classId: number | null | undefined,
): number => {
  if (!isKnownClass(classId)) return 0;
  return CLASS_MAIN_RESOURCE[classId] === resource
    ? MAIN_RESOURCE_PER_LEVEL
    : OTHER_RESOURCE_PER_LEVEL;
};

/** level × rate; unknown class, missing level or level < 1 → 0. */
export const levelResourceBonus = (
  resource: GrowthResource,
  classId: number | null | undefined,
  level: number | null | undefined,
): number => {
  if (typeof level !== 'number' || !Number.isFinite(level) || level < 1) return 0;
  return Math.floor(level) * levelResourceRate(resource, classId);
};

/** «За уровень: здоровье +15, мана/энергия/выносливость +10». Unknown class → ''. */
export const classGrowthText = (classId: number | null | undefined): string => {
  if (!isKnownClass(classId)) return '';
  const main = CLASS_MAIN_RESOURCE[classId];
  const others = GROWTH_RESOURCES.filter((r) => r !== main)
    .map((r) => RESOURCE_LABELS[r])
    .join('/');
  return `За уровень: ${RESOURCE_LABELS[main]} +${MAIN_RESOURCE_PER_LEVEL}, ${others} +${OTHER_RESOURCE_PER_LEVEL}`;
};

/** Generic note for places where the class is not chosen yet. */
export const RESOURCE_GROWTH_NOTE =
  `Каждый уровень сам поднимает запасы: основной ресурс класса на +${MAIN_RESOURCE_PER_LEVEL}, ` +
  `остальные на +${OTHER_RESOURCE_PER_LEVEL} (воин — здоровье, плут — энергия, маг — мана). ` +
  'Это не зависит от вложенных очков и не режется убывающей отдачей.';
