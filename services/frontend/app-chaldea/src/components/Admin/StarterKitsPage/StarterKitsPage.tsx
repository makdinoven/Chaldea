import { useEffect, useState, useCallback } from 'react';
import axios from 'axios';
import toast from 'react-hot-toast';
import { motion } from 'motion/react';

/* ── Types ── */

interface StarterKitItem {
  item_id: number;
  quantity: number;
}

interface StarterKitSkill {
  skill_id: number;
}

interface StarterKit {
  id: number;
  class_id: number;
  items: StarterKitItem[];
  skills: StarterKitSkill[];
  currency_amount: number;
}

interface Item {
  id: number;
  name: string;
  item_type: string;
}

interface Skill {
  id: number;
  name: string;
  skill_type: string;
}

interface ClassKitState {
  items: StarterKitItem[];
  skills: StarterKitSkill[];
  currency_amount: number;
  saving: boolean;
}

const CLASS_NAMES: Record<number, string> = {
  1: 'Воин',
  2: 'Плут',
  3: 'Маг',
};

const CLASS_IDS = [1, 2, 3];

/* ── Component ── */

const StarterKitsPage = () => {
  const [allItems, setAllItems] = useState<Item[]>([]);
  const [allSkills, setAllSkills] = useState<Skill[]>([]);
  const [kits, setKits] = useState<Record<number, ClassKitState>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /* ── Fetch all data ── */
  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [kitsRes, itemsRes, skillsRes] = await Promise.all([
        axios.get<StarterKit[]>('/characters/starter-kits'),
        axios.get<Item[]>('/inventory/items'),
        axios.get<Skill[]>('/skills/admin/skills/'),
      ]);

      setAllItems(itemsRes.data);
      setAllSkills(skillsRes.data);

      const state: Record<number, ClassKitState> = {};
      for (const cid of CLASS_IDS) {
        const kit = kitsRes.data.find((k) => k.class_id === cid);
        state[cid] = {
          items: kit?.items ?? [],
          skills: kit?.skills ?? [],
          currency_amount: kit?.currency_amount ?? 0,
          saving: false,
        };
      }
      setKits(state);
    } catch {
      setError('Не удалось загрузить данные. Попробуйте позже.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  /* ── Handlers ── */

  const updateKit = (classId: number, patch: Partial<ClassKitState>) => {
    setKits((prev) => ({
      ...prev,
      [classId]: { ...prev[classId], ...patch },
    }));
  };

  const addItem = (classId: number, itemId: number) => {
    const kit = kits[classId];
    if (kit.items.some((i) => i.item_id === itemId)) return;
    updateKit(classId, { items: [...kit.items, { item_id: itemId, quantity: 1 }] });
  };

  const removeItem = (classId: number, itemId: number) => {
    const kit = kits[classId];
    updateKit(classId, { items: kit.items.filter((i) => i.item_id !== itemId) });
  };

  const setItemQuantity = (classId: number, itemId: number, quantity: number) => {
    const kit = kits[classId];
    updateKit(classId, {
      items: kit.items.map((i) => (i.item_id === itemId ? { ...i, quantity: Math.max(1, quantity) } : i)),
    });
  };

  const addSkill = (classId: number, skillId: number) => {
    const kit = kits[classId];
    if (kit.skills.some((s) => s.skill_id === skillId)) return;
    updateKit(classId, { skills: [...kit.skills, { skill_id: skillId }] });
  };

  const removeSkill = (classId: number, skillId: number) => {
    const kit = kits[classId];
    updateKit(classId, { skills: kit.skills.filter((s) => s.skill_id !== skillId) });
  };

  const setCurrency = (classId: number, value: number) => {
    updateKit(classId, { currency_amount: Math.max(0, value) });
  };

  const saveKit = async (classId: number) => {
    const kit = kits[classId];
    updateKit(classId, { saving: true });
    try {
      await axios.put(`/characters/starter-kits/${classId}`, {
        items: kit.items,
        skills: kit.skills,
        currency_amount: kit.currency_amount,
      });
      toast.success(`Набор для класса «${CLASS_NAMES[classId]}» сохранён`);
    } catch {
      toast.error(`Не удалось сохранить набор для класса «${CLASS_NAMES[classId]}»`);
    } finally {
      updateKit(classId, { saving: false });
    }
  };

  /* ── Helpers ── */

  const itemName = (id: number): string => allItems.find((i) => i.id === id)?.name ?? `#${id}`;
  const skillName = (id: number): string => allSkills.find((s) => s.id === id)?.name ?? `#${id}`;

  /* ── Render ── */

  if (loading) {
    return (
      <div className="w-full max-w-[1240px] mx-auto">
        <span className="text-white text-lg">Загрузка...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="w-full max-w-[1240px] mx-auto flex flex-col items-center gap-4 mt-8">
        <p className="text-site-red text-xl font-semibold">{error}</p>
        <button className="btn-blue" onClick={fetchData}>
          Повторить
        </button>
      </div>
    );
  }

  return (
    <div className="w-full max-w-[1240px] mx-auto">
      <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em] mb-8">
        Стартовые наборы
      </h1>

      <motion.div
        className="grid grid-cols-1 lg:grid-cols-3 gap-6"
        initial="hidden"
        animate="visible"
        variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.08 } } }}
      >
        {CLASS_IDS.map((classId) => {
          const kit = kits[classId];
          if (!kit) return null;

          return (
            <motion.div
              key={classId}
              variants={{
                hidden: { opacity: 0, y: 10 },
                visible: { opacity: 1, y: 0 },
              }}
              className="gray-bg p-6 flex flex-col gap-6"
            >
              {/* Class name */}
              <h2 className="gold-text text-xl font-medium uppercase tracking-[0.06em]">
                {CLASS_NAMES[classId]}
              </h2>

              {/* ── Items ── */}
              <section className="flex flex-col gap-3">
                <h3 className="text-white text-sm font-medium uppercase tracking-[0.06em]">
                  Предметы
                </h3>

                {kit.items.length === 0 && (
                  <p className="text-white/50 text-sm">Нет предметов</p>
                )}

                <div className="flex flex-col gap-2 gold-scrollbar overflow-y-auto max-h-[200px]">
                  {kit.items.map((kitItem) => (
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
                          setItemQuantity(classId, kitItem.item_id, parseInt(e.target.value) || 1)
                        }
                        className="w-16 text-center bg-transparent border-b border-white/30 text-white text-sm outline-none focus:border-site-blue transition-colors"
                      />
                      <button
                        onClick={() => removeItem(classId, kitItem.item_id)}
                        className="text-site-red text-sm hover:text-white transition-colors duration-200"
                        title="Удалить"
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
                    const id = parseInt(e.target.value);
                    if (id) addItem(classId, id);
                  }}
                >
                  <option value="">Добавить предмет...</option>
                  {allItems
                    .filter((item) => !kit.items.some((ki) => ki.item_id === item.id))
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

                {kit.skills.length === 0 && (
                  <p className="text-white/50 text-sm">Нет навыков</p>
                )}

                <div className="flex flex-col gap-2 gold-scrollbar overflow-y-auto max-h-[200px]">
                  {kit.skills.map((kitSkill) => (
                    <div
                      key={kitSkill.skill_id}
                      className="flex items-center justify-between gap-2 bg-white/[0.05] rounded-[10px] px-3 py-2"
                    >
                      <span className="text-white text-sm truncate flex-1">
                        {skillName(kitSkill.skill_id)}
                      </span>
                      <button
                        onClick={() => removeSkill(classId, kitSkill.skill_id)}
                        className="text-site-red text-sm hover:text-white transition-colors duration-200"
                        title="Удалить"
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
                    const id = parseInt(e.target.value);
                    if (id) addSkill(classId, id);
                  }}
                >
                  <option value="">Добавить навык...</option>
                  {allSkills
                    .filter((skill) => !kit.skills.some((ks) => ks.skill_id === skill.id))
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
                  value={kit.currency_amount}
                  onChange={(e) => setCurrency(classId, parseInt(e.target.value) || 0)}
                  className="input-underline"
                  placeholder="0"
                />
              </section>

              {/* ── Save ── */}
              <button
                className="btn-blue mt-auto"
                onClick={() => saveKit(classId)}
                disabled={kit.saving}
              >
                {kit.saving ? 'Сохранение...' : 'Сохранить'}
              </button>
            </motion.div>
          );
        })}
      </motion.div>
    </div>
  );
};

export default StarterKitsPage;
