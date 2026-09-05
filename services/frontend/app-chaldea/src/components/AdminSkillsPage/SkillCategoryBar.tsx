import type { Subclass } from '../AdminClassTreeEditor/types';
import {
  ALL_SKILLS,
  MOB_ACCENT,
  SKILL_CLASSES,
  sameCategory,
  type SkillCategory,
} from './skillCategories';

/**
 * The category picker above the skill list.
 *
 * Two rows rather than one flat list: the classes and mobs on top, and the
 * subclasses of whichever class is open below. A subclass is a narrower
 * category than its class, not a sibling of it, and stacking the rows is what
 * says so — picking "Воин" shows the warrior's own skills, and its subclasses
 * are one step further in.
 */

interface SkillCategoryBarProps {
  category: SkillCategory;
  onChange: (category: SkillCategory) => void;
  subclasses: Subclass[];
  /** Number of skills in the category currently shown. */
  count: number;
}

const tabClass = (active: boolean) =>
  `px-3 py-1.5 rounded-card text-sm font-medium uppercase tracking-wide transition-colors duration-200 ${
    active ? 'text-white' : 'text-white/40 hover:text-white/70'
  }`;

const tabStyle = (active: boolean, accent: string) => ({
  background: active ? `${accent}22` : 'rgba(255,255,255,0.04)',
  border: `1px solid ${active ? `${accent}66` : 'transparent'}`,
});

const SkillCategoryBar = ({ category, onChange, subclasses, count }: SkillCategoryBarProps) => {
  // Which class's subclasses to offer: the one being viewed, either directly or
  // through one of its subclasses.
  const openClassId =
    category.kind === 'class' || category.kind === 'subclass' ? category.classId : null;
  const classSubclasses = subclasses.filter((s) => s.class_id === openClassId);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => onChange(ALL_SKILLS)}
          className={tabClass(category.kind === 'all')}
          style={tabStyle(category.kind === 'all', '#f0d95c')}
        >
          Все
        </button>

        {SKILL_CLASSES.map((cls) => {
          const active = openClassId === cls.id;
          return (
            <button
              key={cls.id}
              onClick={() => onChange({ kind: 'class', classId: cls.id })}
              className={tabClass(active)}
              style={tabStyle(active, cls.accent)}
            >
              {cls.label}
            </button>
          );
        })}

        <button
          onClick={() => onChange({ kind: 'mob' })}
          className={tabClass(category.kind === 'mob')}
          style={tabStyle(category.kind === 'mob', MOB_ACCENT)}
        >
          Мобы
        </button>

        <span className="self-center text-white/35 text-xs ml-auto">
          {count} навык(ов) в разделе
        </span>
      </div>

      {openClassId !== null && classSubclasses.length > 0 && (
        <div className="flex flex-wrap gap-1.5 pl-1">
          <button
            onClick={() => onChange({ kind: 'class', classId: openClassId })}
            className={`px-2.5 py-1 rounded-card text-xs transition-colors duration-200 ${
              category.kind === 'class'
                ? 'bg-white/10 text-white'
                : 'text-white/40 hover:text-white/70'
            }`}
          >
            Без подкласса
          </button>
          {classSubclasses.map((sub) => {
            const active = sameCategory(category, {
              kind: 'subclass',
              classId: openClassId,
              subclassKey: sub.key,
            });
            return (
              <button
                key={sub.key}
                onClick={() =>
                  onChange({ kind: 'subclass', classId: openClassId, subclassKey: sub.key })
                }
                title={sub.description}
                className={`px-2.5 py-1 rounded-card text-xs transition-colors duration-200 ${
                  active ? 'bg-white/10 text-white' : 'text-white/40 hover:text-white/70'
                }`}
              >
                {sub.name}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default SkillCategoryBar;
