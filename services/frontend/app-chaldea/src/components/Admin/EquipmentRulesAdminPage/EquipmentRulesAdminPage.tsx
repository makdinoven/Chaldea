import { useCallback, useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { useAppSelector } from '../../../redux/store';
import { selectPermissions, selectRole } from '../../../redux/slices/userSlice';
import { hasPermission } from '../../../utils/permissions';
import { fetchClasses, type GameClass } from '../../../api/characterRequests';
import { fetchSubclasses, type Subclass } from '../../../api/subclasses';
import {
  deleteEquipmentRule,
  fetchEquipmentRuleRows,
  saveEquipmentRule,
  type EquipmentRuleRow,
  type HandToken,
} from '../../../api/equipmentRules';
import {
  ARMOR_SUBCLASS_LABELS,
  TWO_HANDED_WEAPON_CATEGORIES,
} from '../../../constants/items';
import HandRulesColumn from './HandRulesColumn';

/* ── Scope helpers ── */

interface Scope {
  classId: number;
  subclassKey: string | null;
}

const scopeId = (s: Scope) => `${s.classId}:${s.subclassKey ?? ''}`;

interface Draft {
  enabled: boolean;
  armor: Set<string>;
  mainHand: Set<HandToken>;
  offHand: Set<HandToken>;
}

const draftFromRow = (row: EquipmentRuleRow | undefined): Draft => ({
  enabled: Boolean(row),
  armor: new Set(row?.armor_classes ?? []),
  mainHand: new Set(row?.main_hand ?? []),
  offHand: new Set(row?.off_hand ?? []),
});

const sameSet = (a: Set<string>, b: Set<string>) => a.size === b.size && [...a].every((v) => b.has(v));

const sameDraft = (a: Draft, b: Draft) =>
  a.enabled === b.enabled &&
  (!a.enabled || (sameSet(a.armor, b.armor) && sameSet(a.mainHand, b.mainHand) && sameSet(a.offHand, b.offHand)));

/* ── Component ── */

const EquipmentRulesAdminPage = () => {
  const permissions = useAppSelector(selectPermissions);
  const role = useAppSelector(selectRole);
  const canEdit = role === 'admin' || hasPermission(permissions ?? [], 'items:update');

  const [classes, setClasses] = useState<GameClass[]>([]);
  const [subclasses, setSubclasses] = useState<Subclass[]>([]);
  const [rows, setRows] = useState<EquipmentRuleRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [selected, setSelected] = useState<Scope | null>(null);
  const [draft, setDraft] = useState<Draft>(draftFromRow(undefined));

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [cls, subs, ruleRows] = await Promise.all([fetchClasses(), fetchSubclasses(), fetchEquipmentRuleRows()]);
      const sortedClasses = [...cls].sort((a, b) => a.id_class - b.id_class);
      setClasses(sortedClasses);
      setSubclasses(subs);
      setRows(ruleRows);
      setSelected((prev) => prev ?? (sortedClasses[0] ? { classId: sortedClasses[0].id_class, subclassKey: null } : null));
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Не удалось загрузить данные';
      setLoadError(msg);
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const rowFor = useCallback(
    (scope: Scope) => rows.find((r) => r.class_id === scope.classId && (r.subclass_key ?? null) === scope.subclassKey),
    [rows],
  );

  const savedDraft = useMemo(() => draftFromRow(selected ? rowFor(selected) : undefined), [selected, rowFor]);

  // Reset the editor whenever the selected scope or its saved row changes
  useEffect(() => {
    setDraft(savedDraft);
  }, [savedDraft]);

  const dirty = !sameDraft(draft, savedDraft);

  const scopeLabel = (scope: Scope) => {
    const cls = classes.find((c) => c.id_class === scope.classId)?.name ?? `Класс ${scope.classId}`;
    if (!scope.subclassKey) return `${cls} — до выбора подкласса`;
    return subclasses.find((s) => s.key === scope.subclassKey)?.name ?? scope.subclassKey;
  };

  const selectScope = (scope: Scope) => {
    if (dirty && !confirm('Есть несохранённые изменения. Перейти без сохранения?')) return;
    setSelected(scope);
  };

  const copyFrom = (sourceId: string) => {
    const source = rows.find((r) => scopeId({ classId: r.class_id, subclassKey: r.subclass_key ?? null }) === sourceId);
    if (!source) return;
    setDraft({ ...draftFromRow(source), enabled: true });
    toast.success('Правила скопированы — не забудьте сохранить');
  };

  const handleSave = async () => {
    if (!selected) return;
    setSaving(true);
    try {
      if (!draft.enabled) {
        if (rowFor(selected)) await deleteEquipmentRule(selected.classId, selected.subclassKey);
        setRows((prev) =>
          prev.filter((r) => !(r.class_id === selected.classId && (r.subclass_key ?? null) === selected.subclassKey)),
        );
        toast.success('Ограничения сняты');
      } else {
        const saved = await saveEquipmentRule({
          class_id: selected.classId,
          subclass_key: selected.subclassKey,
          armor_classes: [...draft.armor],
          main_hand: [...draft.mainHand],
          off_hand: [...draft.offHand],
        });
        setRows((prev) => [
          ...prev.filter((r) => !(r.class_id === saved.class_id && (r.subclass_key ?? null) === (saved.subclass_key ?? null))),
          saved,
        ]);
        toast.success('Ограничения сохранены');
      }
    } catch (e) {
      toast.error(e instanceof Error ? e.message : 'Не удалось сохранить');
    } finally {
      setSaving(false);
    }
  };

  const toggleArmor = (value: string) =>
    setDraft((d) => {
      const armor = new Set(d.armor);
      if (armor.has(value)) armor.delete(value);
      else armor.add(value);
      return { ...d, armor };
    });

  /* ── Render ── */

  if (loading) {
    return (
      <div className="flex items-center justify-center py-24">
        <div className="w-8 h-8 border-2 border-gold border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="w-full max-w-container mx-auto flex flex-col items-center gap-4 py-16">
        <p className="text-site-red text-sm text-center">{loadError}</p>
        <button type="button" onClick={load} className="btn-line !w-auto !px-8">
          Повторить
        </button>
      </div>
    );
  }

  const editorDisabled = !canEdit || saving;

  return (
    <div className="w-full max-w-container mx-auto flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <h1 className="gold-text text-2xl sm:text-3xl font-semibold uppercase tracking-[0.06em]">Экипировка классов</h1>
        <p className="text-white/50 text-sm">
          Что может носить каждый класс и подкласс. Без ограничений персонаж носит всё. До выбора подкласса действуют
          правила класса, после — только правила подкласса.
        </p>
      </div>

      <div className="flex flex-col lg:flex-row gap-5">
        {/* Scopes */}
        <aside className="gray-bg p-3 lg:w-72 shrink-0 flex flex-col gap-4 lg:max-h-[75vh] lg:overflow-y-auto gold-scrollbar">
          {classes.map((cls) => {
            const scopes: Scope[] = [
              { classId: cls.id_class, subclassKey: null },
              ...subclasses
                .filter((s) => s.class_id === cls.id_class)
                .map((s) => ({ classId: cls.id_class, subclassKey: s.key })),
            ];
            return (
              <div key={cls.id_class} className="flex flex-col gap-1">
                <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em] px-2">{cls.name}</span>
                {scopes.map((scope) => {
                  const active = selected !== null && scopeId(selected) === scopeId(scope);
                  const restricted = Boolean(rowFor(scope));
                  return (
                    <button
                      key={scopeId(scope)}
                      type="button"
                      onClick={() => selectScope(scope)}
                      className={`flex items-center justify-between gap-2 text-left rounded-card px-3 py-2 text-sm transition-colors ${
                        active ? 'bg-white/[0.08] text-gold' : 'text-white/80 hover:bg-white/[0.05] hover:text-white'
                      }`}
                    >
                      <span className="truncate">{scope.subclassKey ? scopeLabel(scope) : 'До выбора подкласса'}</span>
                      <span className={`text-[10px] shrink-0 ${restricted ? 'text-site-blue' : 'text-white/30'}`}>
                        {restricted ? 'настроено' : 'без огр.'}
                      </span>
                    </button>
                  );
                })}
              </div>
            );
          })}
        </aside>

        {/* Editor */}
        {selected && (
          <section className="gray-bg p-4 sm:p-6 flex-1 min-w-0 flex flex-col gap-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h2 className="gold-text text-xl font-medium uppercase">{scopeLabel(selected)}</h2>
              <label className="flex items-center gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  checked={draft.enabled}
                  onChange={(e) => setDraft((d) => ({ ...d, enabled: e.target.checked }))}
                  disabled={editorDisabled}
                  className="w-5 h-5 accent-site-blue"
                />
                <span className="text-sm text-white">Ограничения включены</span>
              </label>
            </div>

            {!draft.enabled ? (
              <p className="text-white/50 text-sm">
                Ограничений нет — {selected.subclassKey ? 'этот подкласс' : 'персонажи этого класса без подкласса'} могут
                носить любую броню и любое оружие в обеих руках.
              </p>
            ) : (
              <>
                {rows.length > 0 && (
                  <label className="flex flex-col gap-1 max-w-sm">
                    <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">Скопировать из…</span>
                    <select
                      className="input-underline bg-transparent text-sm"
                      value=""
                      onChange={(e) => copyFrom(e.target.value)}
                      disabled={editorDisabled}
                    >
                      <option value="" className="bg-site-dark">—</option>
                      {rows
                        .map((r) => ({ id: scopeId({ classId: r.class_id, subclassKey: r.subclass_key ?? null }), row: r }))
                        .filter(({ id }) => id !== scopeId(selected))
                        .map(({ id, row }) => (
                          <option key={id} value={id} className="bg-site-dark">
                            {scopeLabel({ classId: row.class_id, subclassKey: row.subclass_key ?? null })}
                          </option>
                        ))}
                    </select>
                  </label>
                )}

                <div className="flex flex-col gap-2">
                  <h3 className="gold-text text-base font-medium uppercase tracking-[0.06em]">Броня</h3>
                  <p className="text-white/40 text-xs">Касается шлемов и нагрудников. Плащи и пояса носят все.</p>
                  <div className="flex flex-wrap gap-x-6 gap-y-2">
                    {Object.entries(ARMOR_SUBCLASS_LABELS).map(([value, label]) => (
                      <label key={value} className="flex items-center gap-2 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={draft.armor.has(value)}
                          onChange={() => toggleArmor(value)}
                          disabled={editorDisabled}
                          className="w-4 h-4 accent-site-blue"
                        />
                        <span className="text-sm text-white/80">{label}</span>
                      </label>
                    ))}
                  </div>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  <HandRulesColumn
                    title="Основная рука"
                    tokens={draft.mainHand}
                    onChange={(mainHand) => setDraft((d) => ({ ...d, mainHand }))}
                    disabled={editorDisabled}
                  />
                  <HandRulesColumn
                    title="Доп. рука"
                    tokens={draft.offHand}
                    onChange={(offHand) => setDraft((d) => ({ ...d, offHand }))}
                    excludedCategories={TWO_HANDED_WEAPON_CATEGORIES}
                    note="Двуручное и древковое оружие занимает обе руки и берётся только в основную. Щиты только в доп. руку — отметьте их здесь и не отмечайте слева."
                    disabled={editorDisabled}
                  />
                </div>
              </>
            )}

            <div className="flex flex-col gap-3 pt-2 border-t border-white/10">
              <p className="text-white/40 text-xs">
                После сохранения с персонажей этого {selected.subclassKey ? 'подкласса' : 'класса'} автоматически снимаются
                вещи, которые им больше нельзя носить — они вернутся в инвентарь.
              </p>
              <div className="flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={!canEdit || !dirty || saving}
                  className="btn-blue !text-base !px-8 !py-2 disabled:opacity-50"
                >
                  {saving ? 'Сохранение…' : 'Сохранить'}
                </button>
                {dirty && (
                  <button
                    type="button"
                    onClick={() => setDraft(savedDraft)}
                    disabled={saving}
                    className="btn-line !w-auto !px-8"
                  >
                    Отменить изменения
                  </button>
                )}
              </div>
              {!canEdit && <p className="text-white/40 text-xs">Нет права на изменение (items:update).</p>}
            </div>
          </section>
        )}
      </div>
    </div>
  );
};

export default EquipmentRulesAdminPage;
