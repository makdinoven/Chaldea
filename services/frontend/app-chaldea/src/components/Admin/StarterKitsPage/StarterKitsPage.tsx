import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { motion } from 'motion/react';
import {
  fetchStarterKits,
  fetchStarterKitCoverage,
  updateStarterKitDefault,
  updateStarterKitForOrigin,
  deleteStarterKitOverride,
  type StarterKit,
  type StarterKitItem,
  type StarterKitSkill,
  type StarterKitCoverage,
  type StarterKitCoverageClass,
} from '../../../api/starterKits';
import { fetchOrigins, type OriginCountry } from '../../../api/origins';
import CoverageMatrix, { kitKey } from './CoverageMatrix';

/**
 * FEAT-154 (rules 12a-12c, task #32) — starter kits in two dimensions.
 *
 * A kit belongs to a **pair** (class × origin). `origin_id = 0` is the class
 * default (D16) and is written through the pre-existing
 * `PUT /characters/starter-kits/{class_id}` endpoint — that path is untouched,
 * so editing a class default behaves exactly as it did before this feature.
 * A pair with `origin_id > 0` goes through the pair endpoints, and removing one
 * is a **return to the class default**, not a destruction of the kit.
 */

/* ── Types ── */

interface Item {
  id: number;
  name: string;
  item_type: string;
}

interface Skill {
  id: number;
  name: string;
  /** N1 — skills carry no class_id, only `class_limitations`. Not used here. */
  skill_type: string;
}

interface KitDraft {
  items: StarterKitItem[];
  skills: StarterKitSkill[];
  currency_amount: number;
}

const EMPTY_DRAFT: KitDraft = { items: [], skills: [], currency_amount: 0 };

/** Fallback class list, used only when `GET /starter-kits/coverage` fails, so
 *  that editing the class defaults keeps working exactly as before. */
const FALLBACK_CLASSES: StarterKitCoverageClass[] = [
  { id_class: 1, name: 'Воин', has_default: false },
  { id_class: 2, name: 'Плут', has_default: false },
  { id_class: 3, name: 'Маг', has_default: false },
];

const DEFAULT_ORIGIN_ID = 0;

const errorText = (error: unknown, fallback: string): string =>
  error instanceof Error && error.message ? error.message : fallback;

/* ── Component ── */

const StarterKitsPage = () => {
  const [allItems, setAllItems] = useState<Item[]>([]);
  const [allSkills, setAllSkills] = useState<Skill[]>([]);

  /** Every stored row, keyed by `${class_id}:${origin_id}`. */
  const [kitRows, setKitRows] = useState<Record<string, StarterKit>>({});
  const [coverage, setCoverage] = useState<StarterKitCoverage | null>(null);
  const [coverageError, setCoverageError] = useState<string | null>(null);
  const [origins, setOrigins] = useState<OriginCountry[]>([]);
  const [originsError, setOriginsError] = useState<string | null>(null);

  /** Unsaved edits, keyed the same way. Absent = show what the server has. */
  const [drafts, setDrafts] = useState<Record<string, KitDraft>>({});
  /** Which origin each class card is currently editing (0 = class default). */
  const [selectedOrigin, setSelectedOrigin] = useState<Record<number, number>>({});
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [confirmRevert, setConfirmRevert] = useState<{
    classId: number;
    originId: number;
  } | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const cardRefs = useRef<Record<number, HTMLDivElement | null>>({});

  /* ── Fetch ── */

  /** Kits + coverage — reloaded after every write so the matrix stays honest. */
  const reloadKits = useCallback(async () => {
    const [kits, cov] = await Promise.all([
      fetchStarterKits(true),
      fetchStarterKitCoverage().catch((err: unknown) => {
        setCoverageError(errorText(err, 'Не удалось загрузить заполненность комбинаций.'));
        return null;
      }),
    ]);
    const rows: Record<string, StarterKit> = {};
    kits.forEach((kit) => {
      rows[kitKey(kit.class_id, kit.origin_id ?? DEFAULT_ORIGIN_ID)] = kit;
    });
    setKitRows(rows);
    if (cov) {
      setCoverage(cov);
      setCoverageError(null);
    }
  }, []);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    setCoverageError(null);
    setOriginsError(null);
    try {
      const [itemsRes, skillsRes] = await Promise.all([
        axios.get<Item[]>('/inventory/items'),
        axios.get<Skill[]>('/skills/admin/skills/'),
      ]);
      setAllItems(itemsRes.data ?? []);
      setAllSkills(skillsRes.data ?? []);

      await reloadKits();

      // The origin registry is the second dimension. Its failure degrades the
      // page to class defaults only — it must not hide the editor entirely.
      try {
        setOrigins(await fetchOrigins());
      } catch (err) {
        setOriginsError(errorText(err, 'Не удалось загрузить список происхождений.'));
      }
    } catch (err) {
      setError(errorText(err, 'Не удалось загрузить данные. Попробуйте позже.'));
    } finally {
      setLoading(false);
    }
  }, [reloadKits]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  /* ── Derived ── */

  const classes = coverage?.classes?.length ? coverage.classes : FALLBACK_CLASSES;

  const overrideKeys = useMemo(() => {
    const keys = new Set<string>();
    (coverage?.overrides ?? []).forEach((o) => keys.add(kitKey(o.class_id, o.origin_id)));
    return keys;
  }, [coverage]);

  const originName = useCallback(
    (originId: number): string =>
      originId === DEFAULT_ORIGIN_ID
        ? 'по умолчанию для класса'
        : origins.find((o) => o.id === originId)?.name ?? `#${originId}`,
    [origins],
  );

  const originFor = (classId: number) => selectedOrigin[classId] ?? DEFAULT_ORIGIN_ID;

  const rowToDraft = (row: StarterKit | undefined): KitDraft | null =>
    row
      ? {
          items: row.items ?? [],
          skills: row.skills ?? [],
          currency_amount: row.currency_amount ?? 0,
        }
      : null;

  /**
   * What the editor shows for a pair: the unsaved draft, else the pair's own
   * row, else — for an inheriting pair — the class default as a starting point,
   * else an empty kit.
   */
  const draftFor = (classId: number, originId: number): KitDraft => {
    const key = kitKey(classId, originId);
    if (drafts[key]) return drafts[key];
    const own = rowToDraft(kitRows[key]);
    if (own) return own;
    if (originId !== DEFAULT_ORIGIN_ID) {
      const fallback = rowToDraft(kitRows[kitKey(classId, DEFAULT_ORIGIN_ID)]);
      if (fallback) return fallback;
    }
    return EMPTY_DRAFT;
  };

  const hasOwnRow = (classId: number, originId: number) =>
    Boolean(kitRows[kitKey(classId, originId)]);

  /* ── Draft mutations ── */

  const patchDraft = (classId: number, originId: number, patch: Partial<KitDraft>) => {
    const key = kitKey(classId, originId);
    const current = draftFor(classId, originId);
    setDrafts((prev) => ({ ...prev, [key]: { ...current, ...patch } }));
  };

  const addItem = (classId: number, originId: number, itemId: number) => {
    const draft = draftFor(classId, originId);
    if (draft.items.some((i) => i.item_id === itemId)) return;
    patchDraft(classId, originId, { items: [...draft.items, { item_id: itemId, quantity: 1 }] });
  };

  const removeItem = (classId: number, originId: number, itemId: number) => {
    const draft = draftFor(classId, originId);
    patchDraft(classId, originId, { items: draft.items.filter((i) => i.item_id !== itemId) });
  };

  const setItemQuantity = (
    classId: number,
    originId: number,
    itemId: number,
    quantity: number,
  ) => {
    const draft = draftFor(classId, originId);
    patchDraft(classId, originId, {
      items: draft.items.map((i) =>
        i.item_id === itemId ? { ...i, quantity: Math.max(1, quantity) } : i,
      ),
    });
  };

  const addSkill = (classId: number, originId: number, skillId: number) => {
    const draft = draftFor(classId, originId);
    if (draft.skills.some((s) => s.skill_id === skillId)) return;
    patchDraft(classId, originId, { skills: [...draft.skills, { skill_id: skillId }] });
  };

  const removeSkill = (classId: number, originId: number, skillId: number) => {
    const draft = draftFor(classId, originId);
    patchDraft(classId, originId, {
      skills: draft.skills.filter((s) => s.skill_id !== skillId),
    });
  };

  const setCurrency = (classId: number, originId: number, value: number) => {
    patchDraft(classId, originId, { currency_amount: Math.max(0, value) });
  };

  /* ── Server writes ── */

  const clearDraft = (key: string) =>
    setDrafts((prev) => {
      const next = { ...prev };
      delete next[key];
      return next;
    });

  const saveKit = async (classId: number, originId: number, className: string) => {
    const key = kitKey(classId, originId);
    const draft = draftFor(classId, originId);
    const payload = {
      items: draft.items,
      skills: draft.skills,
      currency_amount: draft.currency_amount,
    };
    setBusyKey(key);
    try {
      // origin 0 keeps using the untouched pre-FEAT-154 endpoint.
      if (originId === DEFAULT_ORIGIN_ID) {
        await updateStarterKitDefault(classId, payload);
        toast.success(`Набор по умолчанию для класса «${className}» сохранён`);
      } else {
        await updateStarterKitForOrigin(classId, originId, payload);
        toast.success(`Набор «${className} × ${originName(originId)}» сохранён`);
      }
      clearDraft(key);
      await reloadKits();
    } catch (err) {
      toast.error(errorText(err, 'Не удалось сохранить стартовый набор.'));
    } finally {
      setBusyKey(null);
    }
  };

  /** Deleting an override = the pair goes back to using the class default. */
  const revertToClassDefault = async () => {
    if (!confirmRevert) return;
    const { classId, originId } = confirmRevert;
    const key = kitKey(classId, originId);
    setBusyKey(key);
    try {
      await deleteStarterKitOverride(classId, originId);
      clearDraft(key);
      await reloadKits();
      toast.success(
        `Отдельный набор для «${originName(originId)}» убран — пара снова берёт набор класса`,
      );
    } catch (err) {
      toast.error(errorText(err, 'Не удалось вернуть пару к набору класса.'));
    } finally {
      setBusyKey(null);
      setConfirmRevert(null);
    }
  };

  /* ── Helpers ── */

  const itemName = (id: number): string => allItems.find((i) => i.id === id)?.name ?? `#${id}`;
  const skillName = (id: number): string => allSkills.find((s) => s.id === id)?.name ?? `#${id}`;

  const selectPair = (classId: number, originId: number) => {
    setSelectedOrigin((prev) => ({ ...prev, [classId]: originId }));
    cardRefs.current[classId]?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  /* ── Render ── */

  if (loading) {
    return (
      <div className="w-full max-w-container mx-auto p-4">
        <span className="text-white text-lg">Загрузка...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-full max-w-container mx-auto flex flex-col items-center gap-4 mt-8 p-4">
        <p className="text-site-red text-xl font-semibold text-center">{error}</p>
        <button className="btn-blue" onClick={fetchData}>
          Повторить
        </button>
      </div>
    );
  }

  return (
    <div className="w-full max-w-container mx-auto p-4 sm:p-5">
      <h1 className="gold-text text-2xl sm:text-3xl font-semibold uppercase tracking-[0.06em] mb-2">
        Стартовые наборы
      </h1>
      <p className="text-white/50 text-sm max-w-[820px] mb-6">
        Набор задаётся парой «класс × происхождение». Если у пары своего набора нет, персонаж
        получит набор по умолчанию для своего класса — заполнять все комбинации не обязательно.
      </p>

      {/* Every failure is visible and retryable. */}
      {coverageError && (
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-4 p-3 rounded border border-site-red/40 bg-site-red/10">
          <p className="text-site-red text-sm flex-1">{coverageError}</p>
          <button
            type="button"
            onClick={() => {
              setCoverageError(null);
              reloadKits().catch((err: unknown) =>
                setCoverageError(errorText(err, 'Не удалось загрузить стартовые наборы.')),
              );
            }}
            className="px-4 py-1.5 bg-white/10 text-white rounded text-sm transition-colors hover:bg-white/20"
          >
            Повторить
          </button>
        </div>
      )}

      {originsError && (
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 mb-4 p-3 rounded border border-site-red/40 bg-site-red/10">
          <p className="text-site-red text-sm flex-1">
            {originsError} Доступно только редактирование наборов по умолчанию.
          </p>
          <button
            type="button"
            onClick={async () => {
              setOriginsError(null);
              try {
                setOrigins(await fetchOrigins());
              } catch (err) {
                setOriginsError(errorText(err, 'Не удалось загрузить список происхождений.'));
              }
            }}
            className="px-4 py-1.5 bg-white/10 text-white rounded text-sm transition-colors hover:bg-white/20"
          >
            Повторить
          </button>
        </div>
      )}

      {/* Rendered strictly from GET /starter-kits/coverage — when that call
          failed the banner above explains why the matrix is missing, rather
          than the matrix showing a made-up picture. */}
      <CoverageMatrix
        classes={coverage?.classes ?? []}
        origins={origins}
        overrideKeys={overrideKeys}
        selectedByClass={selectedOrigin}
        onSelect={selectPair}
      />

      <motion.div
        className="grid grid-cols-1 lg:grid-cols-3 gap-6"
        initial="hidden"
        animate="visible"
        variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.08 } } }}
      >
        {classes.map((klass) => {
          const classId = klass.id_class;
          const originId = originFor(classId);
          const key = kitKey(classId, originId);
          const draft = draftFor(classId, originId);
          const own = hasOwnRow(classId, originId);
          const busy = busyKey === key;
          const dirty = Boolean(drafts[key]);

          return (
            <motion.div
              key={classId}
              ref={(el) => {
                cardRefs.current[classId] = el;
              }}
              variants={{
                hidden: { opacity: 0, y: 10 },
                visible: { opacity: 1, y: 0 },
              }}
              className="gray-bg p-4 sm:p-6 flex flex-col gap-6 scroll-mt-24"
            >
              {/* Class name */}
              <h2 className="gold-text text-lg sm:text-xl font-medium uppercase tracking-[0.06em]">
                {klass.name}
              </h2>

              {/* ── Origin dimension ── */}
              <section className="flex flex-col gap-2">
                <label
                  className="text-white text-sm font-medium uppercase tracking-[0.06em]"
                  htmlFor={`origin-${classId}`}
                >
                  Происхождение
                </label>
                <select
                  id={`origin-${classId}`}
                  className="input-underline text-sm"
                  value={originId}
                  onChange={(e) =>
                    setSelectedOrigin((prev) => ({
                      ...prev,
                      [classId]: parseInt(e.target.value, 10) || DEFAULT_ORIGIN_ID,
                    }))
                  }
                >
                  <option value={DEFAULT_ORIGIN_ID}>По умолчанию для класса</option>
                  {origins.map((origin) => (
                    <option key={origin.id} value={origin.id}>
                      {origin.name}
                      {hasOwnRow(classId, origin.id) ? ' — задан' : ''}
                    </option>
                  ))}
                </select>

                {originId === DEFAULT_ORIGIN_ID ? (
                  <p className="text-white/50 text-xs">
                    Базовый набор класса. Его получают все, у кого нет своего набора.
                  </p>
                ) : own ? (
                  <p className="text-gold text-xs">
                    У этой пары свой набор — он важнее набора класса.
                  </p>
                ) : (
                  <p className="text-white/50 text-xs">
                    Пара наследует набор класса — он и показан ниже. Сохранение создаст для неё
                    отдельный набор.
                  </p>
                )}
              </section>

              {/* ── Items ── */}
              <section className="flex flex-col gap-3">
                <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em]">
                  Предметы
                </h3>

                {draft.items.length === 0 && <p className="text-white/50 text-sm">Нет предметов</p>}

                <div className="flex flex-col gap-2 gold-scrollbar overflow-y-auto max-h-[200px]">
                  {draft.items.map((kitItem) => (
                    <div
                      key={kitItem.item_id}
                      className="flex items-center justify-between gap-2 bg-white/[0.05] rounded-[10px] px-3 py-2"
                    >
                      <span className="text-white text-sm truncate flex-1">
                        {itemName(kitItem.item_id)}
                      </span>
                      <input
                        type="number"
                        min={1}
                        value={kitItem.quantity}
                        onChange={(e) =>
                          setItemQuantity(
                            classId,
                            originId,
                            kitItem.item_id,
                            parseInt(e.target.value, 10) || 1,
                          )
                        }
                        className="w-16 text-center bg-transparent border-b border-white/30 text-white text-sm outline-none focus:border-site-blue transition-colors"
                      />
                      <button
                        onClick={() => removeItem(classId, originId, kitItem.item_id)}
                        className="text-site-red text-sm hover:text-white transition-colors duration-200"
                        title="Убрать из набора"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>

                {/* Add item select */}
                <select
                  className="input-underline text-sm"
                  value=""
                  onChange={(e) => {
                    const id = parseInt(e.target.value, 10);
                    if (id) addItem(classId, originId, id);
                  }}
                >
                  <option value="">Добавить предмет...</option>
                  {allItems
                    .filter((item) => !draft.items.some((ki) => ki.item_id === item.id))
                    .map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name} ({item.item_type})
                      </option>
                    ))}
                </select>
              </section>

              {/* ── Skills ── */}
              <section className="flex flex-col gap-3">
                <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em]">
                  Навыки
                </h3>

                {draft.skills.length === 0 && <p className="text-white/50 text-sm">Нет навыков</p>}

                <div className="flex flex-col gap-2 gold-scrollbar overflow-y-auto max-h-[200px]">
                  {draft.skills.map((kitSkill) => (
                    <div
                      key={kitSkill.skill_id}
                      className="flex items-center justify-between gap-2 bg-white/[0.05] rounded-[10px] px-3 py-2"
                    >
                      <span className="text-white text-sm truncate flex-1">
                        {skillName(kitSkill.skill_id)}
                      </span>
                      <button
                        onClick={() => removeSkill(classId, originId, kitSkill.skill_id)}
                        className="text-site-red text-sm hover:text-white transition-colors duration-200"
                        title="Убрать из набора"
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>

                {/* Add skill select */}
                <select
                  className="input-underline text-sm"
                  value=""
                  onChange={(e) => {
                    const id = parseInt(e.target.value, 10);
                    if (id) addSkill(classId, originId, id);
                  }}
                >
                  <option value="">Добавить навык...</option>
                  {allSkills
                    .filter((skill) => !draft.skills.some((ks) => ks.skill_id === skill.id))
                    .map((skill) => (
                      <option key={skill.id} value={skill.id}>
                        {skill.name} ({skill.skill_type})
                      </option>
                    ))}
                </select>
              </section>

              {/* ── Currency ── */}
              <section className="flex flex-col gap-2">
                <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em]">
                  Стартовое золото
                </h3>
                <input
                  type="number"
                  min={0}
                  value={draft.currency_amount}
                  onChange={(e) =>
                    setCurrency(classId, originId, parseInt(e.target.value, 10) || 0)
                  }
                  className="input-underline"
                  placeholder="0"
                />
              </section>

              {/* ── Actions ── */}
              <div className="flex flex-col gap-2 mt-auto">
                {dirty && <p className="text-white/50 text-xs">Есть несохранённые изменения.</p>}
                <button
                  className="btn-blue"
                  onClick={() => saveKit(classId, originId, klass.name)}
                  disabled={busy}
                >
                  {busy
                    ? 'Сохранение...'
                    : originId === DEFAULT_ORIGIN_ID || own
                      ? 'Сохранить'
                      : 'Создать набор для пары'}
                </button>

                {originId !== DEFAULT_ORIGIN_ID && own && (
                  <button
                    type="button"
                    className="px-3 py-1.5 bg-site-red/20 text-site-red rounded text-sm transition-colors hover:bg-site-red/30"
                    onClick={() => setConfirmRevert({ classId, originId })}
                    disabled={busy}
                  >
                    Вернуть к набору класса
                  </button>
                )}
              </div>
            </motion.div>
          );
        })}
      </motion.div>

      {confirmRevert && (
        <div className="modal-overlay" onClick={() => setConfirmRevert(null)}>
          <div
            className="modal-content gold-outline gold-outline-thick w-full max-w-md"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="gold-text text-lg sm:text-xl uppercase mb-4">Вернуть к набору класса</h2>
            <p className="text-white mb-2">
              Пара «
              {classes.find((c) => c.id_class === confirmRevert.classId)?.name ??
                `#${confirmRevert.classId}`}{' '}
              × {originName(confirmRevert.originId)}» перестанет иметь свой набор и снова начнёт
              выдавать набор по умолчанию для класса.
            </p>
            <p className="text-white/60 text-sm mb-6">
              Набор класса при этом не меняется, и уже созданные персонажи ничего не теряют — им
              выданное остаётся при них. Свой набор для пары можно будет собрать заново в любой
              момент.
            </p>
            <div className="flex flex-col sm:flex-row gap-3">
              <button
                type="button"
                onClick={revertToClassDefault}
                disabled={busyKey !== null}
                className="btn-blue flex-1"
              >
                {busyKey !== null ? 'Выполняется...' : 'Вернуть к набору класса'}
              </button>
              <button
                type="button"
                onClick={() => setConfirmRevert(null)}
                className="px-4 py-2 bg-white/10 text-white rounded text-sm transition-colors hover:bg-white/20 flex-1"
              >
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default StarterKitsPage;
