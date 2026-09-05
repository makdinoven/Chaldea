import type { Subclass } from '../AdminClassTreeEditor/types';
import {
  ALL_SKILLS,
  GENERAL_ACCENT,
  MOB_ACCENT,
  RACE_ACCENT,
  SKILL_CLASSES,
  sameCategory,
  type RaceWithSubraces,
  type SkillCategory,
} from './skillCategories';

/**
 * The category picker above the skill list.
 *
 * Rows rather than one flat list, because the categories nest: the top row
 * holds what a skill can be scoped by, and each row below narrows the one
 * above. A subclass is not a sibling of its class and a subrace is not a
 * sibling of its race — stacking the rows is what says so, and picking "Воин"
 * shows the warrior's own skills, not its subclasses'.
 */

interface SkillCategoryBarProps {
  category: SkillCategory;
  onChange: (category: SkillCategory) => void;
  subclasses: Subclass[];
  races: RaceWithSubraces[];
  /** Number of skills in the category currently shown. */
  count: number;
}

const topClass = (active: boolean) =>
  `px-3 py-1.5 rounded-card text-sm font-medium uppercase tracking-wide transition-colors duration-200 ${
    active ? 'text-white' : 'text-white/40 hover:text-white/70'
  }`;

const topStyle = (active: boolean, accent: string) => ({
  background: active ? `${accent}22` : 'rgba(255,255,255,0.04)',
  border: `1px solid ${active ? `${accent}66` : 'transparent'}`,
});

const nestedClass = (active: boolean) =>
  `px-2.5 py-1 rounded-card text-xs transition-colors duration-200 ${
    active ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/70'
  }`;

const SkillCategoryBar = ({
  category,
  onChange,
  subclasses,
  races,
  count,
}: SkillCategoryBarProps) => {
  // Which branch is open — by the category itself or by one of its children.
  const openClassId =
    category.kind === 'class' || category.kind === 'subclass' ? category.classId : null;
  const openRaceId =
    category.kind === 'race' || category.kind === 'subrace' ? category.raceId : null;

  const classSubclasses = subclasses.filter((s) => s.class_id === openClassId);
  const openRace = races.find((r) => r.id_race === openRaceId);

  return (
    <div className="flex flex-col gap-2">
      {/* What a skill can be scoped by */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => onChange(ALL_SKILLS)}
          className={topClass(category.kind === 'all')}
          style={topStyle(category.kind === 'all', '#f0d95c')}
        >
          Все
        </button>

        <button
          onClick={() => onChange({ kind: 'general' })}
          className={topClass(category.kind === 'general')}
          style={topStyle(category.kind === 'general', GENERAL_ACCENT)}
          title="Навыки без ограничений: доступны всем"
        >
          Общие
        </button>

        {SKILL_CLASSES.map((cls) => {
          const active = openClassId === cls.id;
          return (
            <button
              key={cls.id}
              onClick={() => onChange({ kind: 'class', classId: cls.id })}
              className={topClass(active)}
              style={topStyle(active, cls.accent)}
            >
              {cls.label}
            </button>
          );
        })}

        <button
          onClick={() =>
            onChange({ kind: 'race', raceId: races[0]?.id_race ?? 1 })
          }
          disabled={races.length === 0}
          className={topClass(openRaceId !== null)}
          style={topStyle(openRaceId !== null, RACE_ACCENT)}
          title="Навыки, доступные только определённой расе"
        >
          Расовые
        </button>

        <button
          onClick={() => onChange({ kind: 'mob' })}
          className={topClass(category.kind === 'mob')}
          style={topStyle(category.kind === 'mob', MOB_ACCENT)}
        >
          Мобы
        </button>

        <span className="self-center text-white/35 text-xs ml-auto">
          {count} навык(ов) в разделе
        </span>
      </div>

      {/* Subclasses of the open class */}
      {openClassId !== null && classSubclasses.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pl-1">
          <button
            onClick={() => onChange({ kind: 'class', classId: openClassId })}
            className={nestedClass(category.kind === 'class')}
          >
            Без подкласса
          </button>
          {classSubclasses.map((sub) => (
            <button
              key={sub.key}
              onClick={() =>
                onChange({ kind: 'subclass', classId: openClassId, subclassKey: sub.key })
              }
              title={sub.description}
              className={nestedClass(
                sameCategory(category, {
                  kind: 'subclass',
                  classId: openClassId,
                  subclassKey: sub.key,
                }),
              )}
            >
              {sub.name}
            </button>
          ))}
        </div>
      )}

      {/* Races, then the subraces of the open one */}
      {openRaceId !== null && (
        <>
          <div className="flex flex-wrap gap-1.5 pl-1">
            {races.map((race) => (
              <button
                key={race.id_race}
                onClick={() => onChange({ kind: 'race', raceId: race.id_race })}
                className={nestedClass(openRaceId === race.id_race)}
              >
                {race.name}
              </button>
            ))}
          </div>

          {openRace && openRace.subraces.length > 0 && (
            <div className="flex flex-wrap gap-1.5 pl-5">
              <button
                onClick={() => onChange({ kind: 'race', raceId: openRace.id_race })}
                className={nestedClass(category.kind === 'race')}
              >
                Без подрасы
              </button>
              {openRace.subraces.map((sub) => (
                <button
                  key={sub.id_subrace}
                  onClick={() =>
                    onChange({
                      kind: 'subrace',
                      raceId: openRace.id_race,
                      subraceId: sub.id_subrace,
                    })
                  }
                  className={nestedClass(
                    sameCategory(category, {
                      kind: 'subrace',
                      raceId: openRace.id_race,
                      subraceId: sub.id_subrace,
                    }),
                  )}
                >
                  {sub.name}
                </button>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default SkillCategoryBar;
