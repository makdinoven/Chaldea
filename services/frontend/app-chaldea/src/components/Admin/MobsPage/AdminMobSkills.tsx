// AdminMobSkills — pick the skills a mob template fights with
import { useState, useEffect, useMemo } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import { updateMobSkills, selectMobsSaving } from '../../../redux/slices/mobsSlice';
import { fetchMobTemplates, fetchMobTemplate, type MobSkillEntry } from '../../../api/mobs';

/**
 * Every mob skill is listed up front, grouped by type.
 *
 * It used to be a search box and nothing else: until you typed a name you saw
 * an empty panel, which is no way to answer "what can I give this mob". Now
 * that mob skills are their own category the whole set can simply be shown,
 * and the search is a filter over it rather than the only way in.
 */

interface AdminMobSkillsProps {
  templateId: number;
  skills: MobSkillEntry[];
  onUpdate: () => void;
}

interface SkillInfo {
  id: number;
  name: string;
  skill_type: string;
  description: string | null;
}

/** Grouping headings, in the order a mob is usually built up. */
const SKILL_TYPE_GROUPS: Array<{ match: string[]; label: string }> = [
  { match: ['attack', 'атака'], label: 'Атака' },
  { match: ['defense', 'защита'], label: 'Защита' },
  { match: ['support', 'поддержка'], label: 'Поддержка' },
];

const groupLabelOf = (skillType: string): string => {
  const normalised = (skillType ?? '').trim().toLowerCase();
  const group = SKILL_TYPE_GROUPS.find((g) => g.match.includes(normalised));
  return group?.label ?? 'Прочее';
};

const AdminMobSkills = ({ templateId, skills, onUpdate }: AdminMobSkillsProps) => {
  const dispatch = useAppDispatch();
  const saving = useAppSelector(selectMobsSaving);

  const [currentSkillIds, setCurrentSkillIds] = useState<number[]>(
    skills.map((s) => s.skill_id),
  );

  const [allSkills, setAllSkills] = useState<SkillInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('');

  // "Take the same set as" — building a variant of an existing mob.
  const [otherTemplates, setOtherTemplates] = useState<Array<{ id: number; name: string }>>([]);
  const [copying, setCopying] = useState(false);

  useEffect(() => {
    setCurrentSkillIds(skills.map((s) => s.skill_id));
  }, [skills]);

  // The whole mob-skill category, once. Small enough to filter in the browser.
  useEffect(() => {
    setLoading(true);
    axios
      .get<SkillInfo[]>('/skills/admin/skills/', { params: { mob: 'true' } })
      .then((res) => setAllSkills(Array.isArray(res.data) ? res.data : []))
      .catch(() => toast.error('Не удалось загрузить навыки мобов'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    fetchMobTemplates({ page_size: 100 })
      .then((res) => setOtherTemplates(
        res.items.filter((t) => t.id !== templateId).map((t) => ({ id: t.id, name: t.name })),
      ))
      .catch(() => {
        // Copying is a convenience; failing to offer it is not worth a toast.
      });
  }, [templateId]);

  const grouped = useMemo(() => {
    const needle = filter.trim().toLowerCase();
    const matching = needle
      ? allSkills.filter((s) => s.name.toLowerCase().includes(needle))
      : allSkills;

    const groups = new Map<string, SkillInfo[]>();
    for (const skill of matching) {
      const label = groupLabelOf(skill.skill_type);
      groups.set(label, [...(groups.get(label) ?? []), skill]);
    }
    const order = [...SKILL_TYPE_GROUPS.map((g) => g.label), 'Прочее'];
    return order
      .filter((label) => groups.has(label))
      .map((label) => ({
        label,
        skills: [...groups.get(label)!].sort((a, b) => a.name.localeCompare(b.name, 'ru')),
      }));
  }, [allSkills, filter]);

  const toggleSkill = (skillId: number) => {
    setCurrentSkillIds((prev) =>
      prev.includes(skillId) ? prev.filter((id) => id !== skillId) : [...prev, skillId],
    );
  };

  const handleCopyFrom = async (sourceId: number) => {
    if (!sourceId) return;
    setCopying(true);
    try {
      const source = await fetchMobTemplate(sourceId);
      const ids = (source.skills ?? []).map((s) => s.skill_id);
      if (ids.length === 0) {
        toast.error('У этого моба нет навыков');
        return;
      }
      // Added to what is already picked rather than replacing it, so a copy
      // never silently throws away work.
      setCurrentSkillIds((prev) => [...new Set([...prev, ...ids])]);
      toast.success(`Добавлено навыков: ${ids.length}`);
    } catch {
      toast.error('Не удалось скопировать набор навыков');
    } finally {
      setCopying(false);
    }
  };

  const handleSave = async () => {
    try {
      await dispatch(updateMobSkills({ templateId, skillIds: currentSkillIds })).unwrap();
      onUpdate();
    } catch {
      // thunk already toasts
    }
  };

  const hasChanges = (() => {
    const original = skills.map((s) => s.skill_id).sort();
    const current = [...currentSkillIds].sort();
    if (original.length !== current.length) return true;
    return original.some((v, i) => v !== current[i]);
  })();

  const nameOf = (skillId: number) =>
    allSkills.find((s) => s.id === skillId)?.name
    ?? skills.find((s) => s.skill_id === skillId)?.skill_name
    ?? `Навык #${skillId}`;

  return (
    <div className="flex flex-col gap-5">
      {/* Chosen set */}
      <div>
        <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em] mb-3">
          Назначено навыков: {currentSkillIds.length}
        </h3>

        {currentSkillIds.length === 0 ? (
          <p className="text-yellow-400/90 text-sm">
            Ни одного навыка — в бою такой моб не сможет ничего сделать.
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {currentSkillIds.map((skillId) => (
              <div
                key={skillId}
                className="flex items-center gap-2 bg-white/[0.07] rounded-full px-3 py-1.5"
              >
                <span className="text-white text-sm">{nameOf(skillId)}</span>
                <button
                  type="button"
                  onClick={() => toggleSkill(skillId)}
                  className="text-site-red hover:text-white text-xs transition-colors"
                  title="Убрать"
                >
                  &times;
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Copy from another mob */}
      {otherTemplates.length > 0 && (
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-white/50 text-xs uppercase tracking-wide">Взять как у:</span>
          <select
            className="input-underline !py-1 text-sm max-w-[240px]"
            defaultValue=""
            disabled={copying}
            onChange={(e) => {
              handleCopyFrom(Number(e.target.value));
              e.target.value = '';
            }}
          >
            <option value="" className="bg-site-dark text-white">
              выберите моба…
            </option>
            {otherTemplates.map((t) => (
              <option key={t.id} value={t.id} className="bg-site-dark text-white">
                {t.name}
              </option>
            ))}
          </select>
          <span className="text-white/35 text-[11px]">
            навыки добавятся к уже выбранным
          </span>
        </div>
      )}

      {/* The whole category, grouped */}
      <div>
        <div className="flex flex-wrap items-center gap-3 mb-3">
          <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em]">
            Навыки мобов ({allSkills.length})
          </h3>
          <input
            className="input-underline !py-1 max-w-[240px] text-sm"
            placeholder="Фильтр по названию…"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
          />
        </div>

        {loading ? (
          <div className="flex items-center gap-2 text-white/50 text-sm">
            <div className="w-4 h-4 border-2 border-white/30 border-t-gold rounded-full animate-spin" />
            Загрузка...
          </div>
        ) : allSkills.length === 0 ? (
          <p className="text-white/50 text-sm">
            Навыков мобов пока нет. Создайте их в разделе «Навыки» → вкладка «Мобы».
          </p>
        ) : grouped.length === 0 ? (
          <p className="text-white/50 text-sm">Ничего не найдено по фильтру.</p>
        ) : (
          <div className="flex flex-col gap-4 max-h-[420px] overflow-y-auto gold-scrollbar pr-1">
            {grouped.map((group) => (
              <div key={group.label}>
                <div className="flex items-center gap-3 mb-2">
                  <span className="text-white/50 text-xs uppercase tracking-wider">
                    {group.label}
                  </span>
                  <span className="text-white/25 text-xs">{group.skills.length}</span>
                  <div className="h-px flex-1 bg-white/10" />
                </div>
                <div className="flex flex-col gap-1">
                  {group.skills.map((skill) => {
                    const isAdded = currentSkillIds.includes(skill.id);
                    return (
                      <label
                        key={skill.id}
                        title={skill.description ?? undefined}
                        className={`flex items-center gap-3 px-3 py-2 rounded cursor-pointer transition-colors ${
                          isAdded ? 'bg-white/[0.09]' : 'hover:bg-white/[0.05]'
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={isAdded}
                          onChange={() => toggleSkill(skill.id)}
                          className="accent-gold"
                        />
                        <span className={isAdded ? 'text-white text-sm' : 'text-white/70 text-sm'}>
                          {skill.name}
                        </span>
                        <span className="text-white/30 text-xs ml-auto">#{skill.id}</span>
                      </label>
                    );
                  })}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {hasChanges && (
        <div>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="btn-blue !text-base !px-8 !py-2 disabled:opacity-50"
          >
            {saving ? 'Сохранение...' : 'Сохранить навыки'}
          </button>
        </div>
      )}
    </div>
  );
};

export default AdminMobSkills;
