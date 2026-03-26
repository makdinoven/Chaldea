import { useState, useEffect, useCallback } from "react";
import {
  fetchAdminRecipes,
  fetchAdminProfessions,
  createRecipe,
  updateRecipe,
  deleteRecipe,
  uploadRecipeImage,
} from "../../../api/professions";
import { fetchItems } from "../../../api/items";
import toast from "react-hot-toast";
import { motion } from "motion/react";
import useDebounce from "../../../hooks/useDebounce";
import type {
  AdminRecipe,
  Profession,
  RecipeCreateRequest,
  RecipeUpdateRequest,
  RecipeIngredientInput,
} from "../../../types/professions";

/* ── Dictionaries ── */

const RARITY_OPTIONS = [
  { value: "common", label: "Обычный" },
  { value: "uncommon", label: "Необычный" },
  { value: "rare", label: "Редкий" },
  { value: "epic", label: "Эпический" },
  { value: "legendary", label: "Легендарный" },
] as const;

const RARITY_LABELS: Record<string, string> = Object.fromEntries(
  RARITY_OPTIONS.map((r) => [r.value, r.label]),
);

const RARITY_FILTER_OPTIONS = [{ value: "", label: "Все редкости" }, ...RARITY_OPTIONS];

/* ── Types ── */

interface IngredientRow {
  item_id: number | "";
  quantity: number;
}

interface RecipeFormState {
  name: string;
  description: string;
  profession_id: number | "";
  required_rank: number;
  result_item_id: number | "";
  result_quantity: number;
  rarity: string;
  icon: string;
  auto_learn_rank: number | "";
  xp_reward: number | "";
  ingredients: IngredientRow[];
  is_active: boolean;
}

const INITIAL_FORM: RecipeFormState = {
  name: "",
  description: "",
  profession_id: "",
  required_rank: 1,
  result_item_id: "",
  result_quantity: 1,
  rarity: "common",
  icon: "",
  auto_learn_rank: "",
  xp_reward: "",
  ingredients: [{ item_id: "", quantity: 1 }],
  is_active: true,
};

interface ItemOption {
  id: number;
  name: string;
}

/* ── Component ── */

const RecipesAdminPage = () => {
  /* List state */
  const [recipes, setRecipes] = useState<AdminRecipe[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [query, setQuery] = useState("");
  const [filterProfession, setFilterProfession] = useState<string>("");
  const [filterRarity, setFilterRarity] = useState("");
  const debouncedQuery = useDebounce(query);
  const perPage = 20;

  /* Professions for dropdowns */
  const [professions, setProfessions] = useState<Profession[]>([]);

  /* Form state */
  const [showForm, setShowForm] = useState(false);
  const [editingRecipe, setEditingRecipe] = useState<AdminRecipe | null>(null);
  const [form, setForm] = useState<RecipeFormState>(INITIAL_FORM);
  const [submitting, setSubmitting] = useState(false);

  /* Image upload state */
  const [imgFile, setImgFile] = useState<File | null>(null);

  /* Item search for result_item and ingredients */
  const [itemSearch, setItemSearch] = useState("");
  const debouncedItemSearch = useDebounce(itemSearch);
  const [itemOptions, setItemOptions] = useState<ItemOption[]>([]);

  /* ── Load data ── */

  const loadRecipes = useCallback(() => {
    fetchAdminRecipes({
      page,
      per_page: perPage,
      search: debouncedQuery || undefined,
      profession_id: filterProfession ? Number(filterProfession) : undefined,
      rarity: filterRarity || undefined,
    })
      .then((res) => {
        setRecipes(res.items);
        setTotal(res.total);
      })
      .catch((e: Error) => toast.error(e.message || "Не удалось загрузить рецепты"));
  }, [page, debouncedQuery, filterProfession, filterRarity]);

  useEffect(() => {
    loadRecipes();
  }, [loadRecipes]);

  useEffect(() => {
    setPage(1);
  }, [debouncedQuery, filterProfession, filterRarity]);

  useEffect(() => {
    fetchAdminProfessions()
      .then(setProfessions)
      .catch((e: Error) => toast.error(e.message || "Не удалось загрузить профессии"));
  }, []);

  /* Item search for dropdowns */
  useEffect(() => {
    if (!showForm) return;
    fetchItems(debouncedItemSearch || "", 1, 50)
      .then((data: ItemOption[]) => setItemOptions(data))
      .catch(() => {
        /* silently ignore — items list is optional helper */
      });
  }, [debouncedItemSearch, showForm]);

  /* ── Form handlers ── */

  const openCreate = () => {
    setEditingRecipe(null);
    setForm(INITIAL_FORM);
    setImgFile(null);
    setShowForm(true);
  };

  const openEdit = (r: AdminRecipe) => {
    setEditingRecipe(r);
    setImgFile(null);
    setForm({
      name: r.name,
      description: r.description ?? "",
      profession_id: r.profession_id,
      required_rank: r.required_rank,
      result_item_id: r.result_item_id,
      result_quantity: r.result_quantity,
      rarity: r.rarity,
      icon: r.icon ?? "",
      auto_learn_rank: r.auto_learn_rank ?? "",
      xp_reward: r.xp_reward ?? "",
      ingredients: r.ingredients.length
        ? r.ingredients.map((ing) => ({
            item_id: ing.item_id,
            quantity: ing.quantity,
          }))
        : [{ item_id: "", quantity: 1 }],
      is_active: r.is_active,
    });
    setShowForm(true);
  };

  const closeForm = () => {
    setShowForm(false);
    setEditingRecipe(null);
    setForm(INITIAL_FORM);
    setImgFile(null);
  };

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>,
  ) => {
    const target = e.target;
    const name = target.name;
    const value =
      target instanceof HTMLInputElement && target.type === "checkbox"
        ? target.checked
        : target.value;
    setForm((s) => ({ ...s, [name]: value }));
  };

  /* Ingredient management */

  const addIngredient = () => {
    setForm((s) => ({
      ...s,
      ingredients: [...s.ingredients, { item_id: "", quantity: 1 }],
    }));
  };

  const removeIngredient = (idx: number) => {
    setForm((s) => ({
      ...s,
      ingredients: s.ingredients.filter((_, i) => i !== idx),
    }));
  };

  const updateIngredient = (idx: number, field: keyof IngredientRow, value: number | string) => {
    setForm((s) => {
      const ingredients = [...s.ingredients];
      ingredients[idx] = { ...ingredients[idx], [field]: value };
      return { ...s, ingredients };
    });
  };

  /* Submit */

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!form.name.trim()) {
      toast.error("Название рецепта обязательно");
      return;
    }
    if (!form.profession_id) {
      toast.error("Выберите профессию");
      return;
    }
    if (!form.result_item_id) {
      toast.error("Выберите результирующий предмет");
      return;
    }

    const validIngredients: RecipeIngredientInput[] = form.ingredients
      .filter((ing) => ing.item_id !== "")
      .map((ing) => ({
        item_id: Number(ing.item_id),
        quantity: Number(ing.quantity) || 1,
      }));

    if (validIngredients.length === 0) {
      toast.error("Добавьте хотя бы один ингредиент");
      return;
    }

    setSubmitting(true);
    try {
      let savedId: number;

      if (editingRecipe) {
        const payload: RecipeUpdateRequest = {
          name: form.name.trim(),
          description: form.description.trim() || null,
          profession_id: Number(form.profession_id),
          required_rank: Number(form.required_rank) || 1,
          result_item_id: Number(form.result_item_id),
          result_quantity: Number(form.result_quantity) || 1,
          rarity: form.rarity,
          icon: form.icon.trim() || null,
          auto_learn_rank: form.auto_learn_rank !== "" ? Number(form.auto_learn_rank) : null,
          xp_reward: form.xp_reward !== "" ? Number(form.xp_reward) : null,
          is_active: form.is_active,
          ingredients: validIngredients,
        };
        const updated = await updateRecipe(editingRecipe.id, payload);
        savedId = updated.id;
        toast.success("Рецепт обновлён");
      } else {
        const payload: RecipeCreateRequest = {
          name: form.name.trim(),
          description: form.description.trim() || null,
          profession_id: Number(form.profession_id),
          required_rank: Number(form.required_rank) || 1,
          result_item_id: Number(form.result_item_id),
          result_quantity: Number(form.result_quantity) || 1,
          rarity: form.rarity,
          icon: form.icon.trim() || null,
          auto_learn_rank: form.auto_learn_rank !== "" ? Number(form.auto_learn_rank) : null,
          xp_reward: form.xp_reward !== "" ? Number(form.xp_reward) : null,
          ingredients: validIngredients,
        };
        const result = await createRecipe(payload);
        savedId = result.id;
        if (result.recipe_item_id) {
          toast.success(
            `Рецепт создан. Предмет-рецепт "${result.recipe_item_name}" (id: ${result.recipe_item_id}) создан автоматически.`,
            { duration: 5000 },
          );
        } else {
          toast.success("Рецепт создан (авто-изучение, предмет не создан)");
        }
      }

      if (imgFile) {
        try {
          await uploadRecipeImage(savedId, imgFile);
          toast.success("Изображение рецепта загружено");
        } catch (imgErr: unknown) {
          const imgMsg = imgErr instanceof Error ? imgErr.message : "Ошибка загрузки изображения";
          toast.error(imgMsg);
        }
      }

      closeForm();
      loadRecipes();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Ошибка при сохранении";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Удалить рецепт? Это действие необратимо.")) return;
    try {
      await deleteRecipe(id);
      toast.success("Рецепт удалён");
      loadRecipes();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Ошибка при удалении";
      toast.error(msg);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / perPage));

  /* ── Render: Form ── */

  if (showForm) {
    return (
      <div className="w-full max-w-[1240px] mx-auto">
        <form className="gray-bg p-6 flex flex-col gap-6" onSubmit={handleSubmit}>
          <h2 className="gold-text text-2xl font-medium uppercase tracking-[0.06em]">
            {editingRecipe ? "Редактирование рецепта" : "Создание рецепта"}
          </h2>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {/* Name */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                Название
              </span>
              <input
                name="name"
                value={form.name}
                onChange={handleChange}
                required
                className="input-underline"
              />
            </label>

            {/* Profession */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                Профессия
              </span>
              <select
                name="profession_id"
                value={form.profession_id}
                onChange={handleChange}
                required
                className="input-underline"
              >
                <option value="" disabled className="bg-site-dark text-white">
                  — Выберите —
                </option>
                {professions.map((p) => (
                  <option key={p.id} value={p.id} className="bg-site-dark text-white">
                    {p.name}
                  </option>
                ))}
              </select>
            </label>

            {/* Required rank */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                Необходимый ранг
              </span>
              <input
                type="number"
                name="required_rank"
                value={form.required_rank}
                onChange={handleChange}
                min={1}
                className="input-underline"
              />
            </label>

            {/* Result item */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                Результат (предмет)
              </span>
              <input
                placeholder="Поиск предмета..."
                value={itemSearch}
                onChange={(e) => setItemSearch(e.target.value)}
                className="input-underline mb-1"
              />
              <select
                name="result_item_id"
                value={form.result_item_id}
                onChange={handleChange}
                required
                className="input-underline"
              >
                <option value="" disabled className="bg-site-dark text-white">
                  — Выберите предмет —
                </option>
                {itemOptions.map((item) => (
                  <option key={item.id} value={item.id} className="bg-site-dark text-white">
                    {item.name} (id: {item.id})
                  </option>
                ))}
              </select>
            </label>

            {/* Result quantity */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                Количество
              </span>
              <input
                type="number"
                name="result_quantity"
                value={form.result_quantity}
                onChange={handleChange}
                min={1}
                className="input-underline"
              />
            </label>

            {/* Rarity */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                Редкость
              </span>
              <select
                name="rarity"
                value={form.rarity}
                onChange={handleChange}
                className="input-underline"
              >
                {RARITY_OPTIONS.map((r) => (
                  <option key={r.value} value={r.value} className="bg-site-dark text-white">
                    {r.label}
                  </option>
                ))}
              </select>
            </label>

            {/* Auto-learn rank */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                Авто-изучение (ранг)
              </span>
              <input
                type="number"
                name="auto_learn_rank"
                value={form.auto_learn_rank}
                onChange={handleChange}
                min={1}
                placeholder="Не задано"
                className="input-underline"
              />
            </label>

            {/* XP reward override */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                XP за крафт
              </span>
              <input
                type="number"
                name="xp_reward"
                value={form.xp_reward}
                onChange={handleChange}
                min={0}
                placeholder="По умолчанию (по редкости)"
                className="input-underline"
              />
            </label>

            {/* Icon upload */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                Иконка
              </span>
              {editingRecipe?.icon && !imgFile && (
                <img
                  src={editingRecipe.icon}
                  alt={editingRecipe.name}
                  className="w-[100px] h-[100px] object-cover rounded-[10px] mb-2"
                />
              )}
              {imgFile && (
                <span className="text-white/60 text-xs truncate mb-1">{imgFile.name}</span>
              )}
              <input
                type="file"
                accept="image/*"
                onChange={(e) => setImgFile(e.target.files?.[0] ?? null)}
                className="text-white text-sm file:mr-4 file:py-2 file:px-4 file:rounded-card file:border-0 file:text-sm file:font-medium file:bg-white/[0.07] file:text-white hover:file:bg-white/[0.12] file:cursor-pointer file:transition-colors"
              />
            </label>

            {editingRecipe && (
              <label className="flex items-center gap-3 self-end pb-2">
                <input
                  type="checkbox"
                  name="is_active"
                  checked={form.is_active}
                  onChange={handleChange}
                  className="w-5 h-5 accent-site-blue"
                />
                <span className="text-sm text-white">Активен</span>
              </label>
            )}

            {/* Description */}
            <label className="flex flex-col gap-1 col-span-full">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                Описание
              </span>
              <textarea
                name="description"
                value={form.description}
                onChange={handleChange}
                rows={3}
                className="textarea-bordered"
              />
            </label>
          </div>

          {/* Ingredients */}
          <fieldset className="col-span-full border border-white/10 rounded-card p-4 bg-white/[0.03]">
            <legend className="text-white/50 text-xs font-medium uppercase tracking-[0.06em] px-2">
              Ингредиенты
            </legend>
            <div className="flex flex-col gap-3 mt-2">
              {form.ingredients.map((ing, idx) => (
                <div
                  key={idx}
                  className="flex flex-col sm:flex-row items-start sm:items-center gap-2 bg-white/[0.03] p-3 rounded-card"
                >
                  <select
                    value={ing.item_id}
                    onChange={(e) =>
                      updateIngredient(idx, "item_id", e.target.value ? Number(e.target.value) : "")
                    }
                    className="input-underline text-sm flex-1 min-w-0"
                  >
                    <option value="" disabled className="bg-site-dark text-white">
                      — Предмет —
                    </option>
                    {itemOptions.map((item) => (
                      <option key={item.id} value={item.id} className="bg-site-dark text-white">
                        {item.name} (id: {item.id})
                      </option>
                    ))}
                  </select>

                  <input
                    type="number"
                    value={ing.quantity}
                    onChange={(e) =>
                      updateIngredient(idx, "quantity", Number(e.target.value) || 1)
                    }
                    min={1}
                    placeholder="Кол-во"
                    className="input-underline text-sm w-24"
                  />

                  <button
                    type="button"
                    onClick={() => removeIngredient(idx)}
                    className="text-sm text-site-red hover:text-white transition-colors duration-200"
                  >
                    Убрать
                  </button>
                </div>
              ))}
              <button
                type="button"
                onClick={addIngredient}
                className="text-sm text-site-blue hover:text-white transition-colors duration-200 self-start"
              >
                + Добавить ингредиент
              </button>
            </div>
          </fieldset>

          {/* Buttons */}
          <div className="flex gap-4 pt-2">
            <button
              type="submit"
              disabled={submitting}
              className="btn-blue !text-base !px-8 !py-2"
            >
              {submitting
                ? "Сохранение..."
                : editingRecipe
                  ? "Сохранить"
                  : "Создать"}
            </button>
            <button
              type="button"
              onClick={closeForm}
              className="btn-line !w-auto !px-8"
            >
              Отмена
            </button>
          </div>
        </form>
      </div>
    );
  }

  /* ── Render: List ── */

  return (
    <div className="w-full max-w-[1240px] mx-auto flex flex-col gap-5">
      <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em]">
        Рецепты
      </h1>

      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex flex-col sm:flex-row items-start sm:items-center gap-3 flex-1">
          <input
            className="input-underline max-w-[240px] w-full"
            placeholder="Поиск по названию..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />

          <select
            value={filterProfession}
            onChange={(e) => setFilterProfession(e.target.value)}
            className="input-underline max-w-[180px] w-full"
          >
            <option value="" className="bg-site-dark text-white">
              Все профессии
            </option>
            {professions.map((p) => (
              <option key={p.id} value={p.id} className="bg-site-dark text-white">
                {p.name}
              </option>
            ))}
          </select>

          <select
            value={filterRarity}
            onChange={(e) => setFilterRarity(e.target.value)}
            className="input-underline max-w-[160px] w-full"
          >
            {RARITY_FILTER_OPTIONS.map((r) => (
              <option key={r.value} value={r.value} className="bg-site-dark text-white">
                {r.label}
              </option>
            ))}
          </select>
        </div>

        <button
          className="btn-blue !text-base !px-5 !py-2 whitespace-nowrap"
          onClick={openCreate}
        >
          Создать рецепт
        </button>
      </div>

      {/* Table */}
      <div className="gray-bg overflow-x-hidden">
        <table className="w-full min-w-[780px]">
          <thead>
            <tr className="border-b border-white/10">
              {["ID", "Название", "Профессия", "Ранг", "Результат", "Редкость", "Предмет-рецепт", "Действия"].map(
                (h, i) => (
                  <th
                    key={h}
                    className={`text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3 ${
                      i === 7 ? "text-right" : "text-left"
                    }`}
                  >
                    {h}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <motion.tbody
            initial="hidden"
            animate="visible"
            variants={{
              hidden: {},
              visible: { transition: { staggerChildren: 0.03 } },
            }}
          >
            {recipes.map((r) => (
              <motion.tr
                key={r.id}
                variants={{
                  hidden: { opacity: 0, y: 6 },
                  visible: { opacity: 1, y: 0 },
                }}
                className="border-b border-white/5 hover:bg-white/[0.05] transition-colors duration-200"
              >
                <td className="px-4 py-3 text-sm text-white/70">{r.id}</td>
                <td className="px-4 py-3 text-sm text-white">{r.name}</td>
                <td className="px-4 py-3 text-sm text-white/70">{r.profession_name}</td>
                <td className="px-4 py-3 text-sm text-white/70">{r.required_rank}</td>
                <td className="px-4 py-3 text-sm text-white/70">
                  {r.result_item_name || `item #${r.result_item_id}`}
                  {r.result_quantity > 1 && ` x${r.result_quantity}`}
                </td>
                <td className="px-4 py-3 text-sm text-white/70">
                  {RARITY_LABELS[r.rarity] ?? r.rarity}
                </td>
                <td className="px-4 py-3 text-sm text-white/70">
                  {r.recipe_item_id ? (
                    <span className="text-site-blue">
                      {r.recipe_item_name} (id: {r.recipe_item_id})
                    </span>
                  ) : r.auto_learn_rank ? (
                    <span className="text-white/40">авто (ранг {r.auto_learn_rank})</span>
                  ) : (
                    <span className="text-white/40">—</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-col items-end gap-1.5">
                    <button
                      onClick={() => openEdit(r)}
                      className="text-sm text-white hover:text-site-blue transition-colors duration-200"
                    >
                      Редактировать
                    </button>
                    <button
                      onClick={() => handleDelete(r.id)}
                      className="text-sm text-site-red hover:text-white transition-colors duration-200"
                    >
                      Удалить
                    </button>
                  </div>
                </td>
              </motion.tr>
            ))}
          </motion.tbody>
        </table>

        {recipes.length === 0 && (
          <p className="text-center text-white/50 text-sm py-8">
            Рецепты не найдены
          </p>
        )}
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-center gap-3">
          <button
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="text-sm text-white hover:text-site-blue transition-colors duration-200 disabled:text-white/20 disabled:cursor-not-allowed"
          >
            Назад
          </button>
          <span className="text-sm text-white/60">
            {page} / {totalPages}
          </span>
          <button
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            className="text-sm text-white hover:text-site-blue transition-colors duration-200 disabled:text-white/20 disabled:cursor-not-allowed"
          >
            Вперёд
          </button>
        </div>
      )}
    </div>
  );
};

export default RecipesAdminPage;
