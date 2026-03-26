import { useState, useEffect, useCallback } from "react";
import {
  fetchAdminProfessions,
  createProfession,
  updateProfession,
  deleteProfession,
  createProfessionRank,
  updateProfessionRank,
  deleteProfessionRank,
  adminSetRank,
} from "../../../api/professions";
import { fetchCharacters } from "../../../api/characters";
import toast from "react-hot-toast";
import { motion, AnimatePresence } from "motion/react";
import useDebounce from "../../../hooks/useDebounce";
import type {
  Profession,
  ProfessionRank,
  ProfessionCreateRequest,
  ProfessionUpdateRequest,
  ProfessionRankCreateRequest,
  ProfessionRankUpdateRequest,
} from "../../../types/professions";

/* ── Helpers ── */

interface Character {
  id: number;
  name: string;
}

interface ProfessionFormState {
  name: string;
  slug: string;
  description: string;
  icon: string;
  sort_order: number;
  is_active: boolean;
}

const INITIAL_PROFESSION: ProfessionFormState = {
  name: "",
  slug: "",
  description: "",
  icon: "",
  sort_order: 0,
  is_active: true,
};

interface RankFormState {
  rank_number: number;
  name: string;
  description: string;
  required_experience: number;
  icon: string;
}

const INITIAL_RANK: RankFormState = {
  rank_number: 1,
  name: "",
  description: "",
  required_experience: 0,
  icon: "",
};

/* ── Main Component ── */

const ProfessionsAdminPage = () => {
  const [professions, setProfessions] = useState<Profession[]>([]);
  const [loading, setLoading] = useState(true);

  /* Profession form */
  const [editingProfession, setEditingProfession] = useState<Profession | null>(null);
  const [creatingProfession, setCreatingProfession] = useState(false);
  const [profForm, setProfForm] = useState<ProfessionFormState>(INITIAL_PROFESSION);
  const [submitting, setSubmitting] = useState(false);

  /* Rank management */
  const [expandedProfId, setExpandedProfId] = useState<number | null>(null);
  const [editingRank, setEditingRank] = useState<ProfessionRank | null>(null);
  const [creatingRank, setCreatingRank] = useState(false);
  const [rankForm, setRankForm] = useState<RankFormState>(INITIAL_RANK);
  const [rankProfessionId, setRankProfessionId] = useState<number | null>(null);

  /* Set rank modal */
  const [setRankOpen, setSetRankOpen] = useState(false);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [charQuery, setCharQuery] = useState("");
  const debouncedCharQuery = useDebounce(charQuery);
  const [selectedChar, setSelectedChar] = useState<Character | null>(null);
  const [setRankNumber, setSetRankNumber] = useState(1);
  const [setRankProfId, setSetRankProfId] = useState<number | null>(null);

  /* ── Load professions ── */

  const load = useCallback(() => {
    setLoading(true);
    fetchAdminProfessions()
      .then((data) => setProfessions(data))
      .catch((e: Error) => toast.error(e.message || "Не удалось загрузить профессии"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  /* ── Load characters for set-rank modal ── */

  useEffect(() => {
    if (!setRankOpen) return;
    fetchCharacters()
      .then(setCharacters)
      .catch((e: Error) => toast.error(e.message || "Не удалось загрузить персонажей"));
  }, [setRankOpen]);

  const filteredChars = characters.filter((c) =>
    c.name.toLowerCase().includes(debouncedCharQuery.toLowerCase()),
  );

  /* ── Profession CRUD ── */

  const openCreateProfession = () => {
    setEditingProfession(null);
    setProfForm(INITIAL_PROFESSION);
    setCreatingProfession(true);
  };

  const openEditProfession = (p: Profession) => {
    setCreatingProfession(false);
    setEditingProfession(p);
    setProfForm({
      name: p.name,
      slug: p.slug,
      description: p.description ?? "",
      icon: p.icon ?? "",
      sort_order: p.sort_order,
      is_active: p.is_active,
    });
  };

  const closeProfessionForm = () => {
    setEditingProfession(null);
    setCreatingProfession(false);
    setProfForm(INITIAL_PROFESSION);
  };

  const handleProfFormChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
  ) => {
    const target = e.target;
    const name = target.name;
    const value =
      target instanceof HTMLInputElement && target.type === "checkbox"
        ? target.checked
        : target.value;
    setProfForm((s) => ({ ...s, [name]: value }));
  };

  const handleProfessionSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!profForm.name.trim()) {
      toast.error("Название профессии обязательно");
      return;
    }
    if (!profForm.slug.trim()) {
      toast.error("Slug профессии обязателен");
      return;
    }

    setSubmitting(true);
    try {
      if (editingProfession) {
        const payload: ProfessionUpdateRequest = {
          name: profForm.name.trim(),
          slug: profForm.slug.trim(),
          description: profForm.description.trim() || null,
          icon: profForm.icon.trim() || null,
          sort_order: Number(profForm.sort_order) || 0,
          is_active: profForm.is_active,
        };
        await updateProfession(editingProfession.id, payload);
        toast.success("Профессия обновлена");
      } else {
        const payload: ProfessionCreateRequest = {
          name: profForm.name.trim(),
          slug: profForm.slug.trim(),
          description: profForm.description.trim() || null,
          icon: profForm.icon.trim() || null,
          sort_order: Number(profForm.sort_order) || 0,
        };
        await createProfession(payload);
        toast.success("Профессия создана");
      }
      closeProfessionForm();
      load();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Ошибка при сохранении";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteProfession = async (id: number) => {
    if (!confirm("Удалить профессию? Все связанные ранги и рецепты будут удалены.")) return;
    try {
      await deleteProfession(id);
      toast.success("Профессия удалена");
      load();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Ошибка при удалении";
      toast.error(msg);
    }
  };

  /* ── Rank CRUD ── */

  const openCreateRank = (professionId: number) => {
    setEditingRank(null);
    setCreatingRank(true);
    setRankProfessionId(professionId);
    const prof = professions.find((p) => p.id === professionId);
    const maxRank = prof?.ranks?.length ? Math.max(...prof.ranks.map((r) => r.rank_number)) : 0;
    setRankForm({ ...INITIAL_RANK, rank_number: maxRank + 1 });
  };

  const openEditRank = (rank: ProfessionRank, professionId: number) => {
    setCreatingRank(false);
    setEditingRank(rank);
    setRankProfessionId(professionId);
    setRankForm({
      rank_number: rank.rank_number,
      name: rank.name,
      description: rank.description ?? "",
      required_experience: rank.required_experience,
      icon: rank.icon ?? "",
    });
  };

  const closeRankForm = () => {
    setEditingRank(null);
    setCreatingRank(false);
    setRankProfessionId(null);
    setRankForm(INITIAL_RANK);
  };

  const handleRankFormChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
  ) => {
    const { name, value } = e.target;
    setRankForm((s) => ({ ...s, [name]: value }));
  };

  const handleRankSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!rankForm.name.trim()) {
      toast.error("Название ранга обязательно");
      return;
    }
    if (!rankProfessionId) return;

    setSubmitting(true);
    try {
      if (editingRank) {
        const payload: ProfessionRankUpdateRequest = {
          rank_number: Number(rankForm.rank_number),
          name: rankForm.name.trim(),
          description: rankForm.description.trim() || null,
          required_experience: Number(rankForm.required_experience) || 0,
          icon: rankForm.icon.trim() || null,
        };
        await updateProfessionRank(editingRank.id, payload);
        toast.success("Ранг обновлён");
      } else {
        const payload: ProfessionRankCreateRequest = {
          rank_number: Number(rankForm.rank_number),
          name: rankForm.name.trim(),
          description: rankForm.description.trim() || null,
          required_experience: Number(rankForm.required_experience) || 0,
          icon: rankForm.icon.trim() || null,
        };
        await createProfessionRank(rankProfessionId, payload);
        toast.success("Ранг создан");
      }
      closeRankForm();
      load();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Ошибка при сохранении ранга";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  const handleDeleteRank = async (rankId: number) => {
    if (!confirm("Удалить ранг?")) return;
    try {
      await deleteProfessionRank(rankId);
      toast.success("Ранг удалён");
      load();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Ошибка при удалении ранга";
      toast.error(msg);
    }
  };

  /* ── Set rank for character ── */

  const openSetRank = (professionId: number) => {
    setSetRankProfId(professionId);
    setSelectedChar(null);
    setCharQuery("");
    setSetRankNumber(1);
    setSetRankOpen(true);
  };

  const handleSetRank = async () => {
    if (!selectedChar || !setRankProfId) return;
    setSubmitting(true);
    try {
      await adminSetRank(selectedChar.id, { rank_number: setRankNumber });
      toast.success(
        `Ранг ${setRankNumber} установлен персонажу "${selectedChar.name}"`,
      );
      setSetRankOpen(false);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Ошибка при установке ранга";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  /* ── Render: Profession Form ── */

  const showingForm = creatingProfession || editingProfession;

  if (showingForm) {
    return (
      <div className="w-full max-w-[1240px] mx-auto">
        <form className="gray-bg p-6 flex flex-col gap-6" onSubmit={handleProfessionSubmit}>
          <h2 className="gold-text text-2xl font-medium uppercase tracking-[0.06em]">
            {editingProfession ? "Редактирование профессии" : "Создание профессии"}
          </h2>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                Название
              </span>
              <input
                name="name"
                value={profForm.name}
                onChange={handleProfFormChange}
                required
                className="input-underline"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                Slug
              </span>
              <input
                name="slug"
                value={profForm.slug}
                onChange={handleProfFormChange}
                required
                placeholder="blacksmith"
                className="input-underline"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                Иконка (URL)
              </span>
              <input
                name="icon"
                value={profForm.icon}
                onChange={handleProfFormChange}
                placeholder="/images/professions/icon.png"
                className="input-underline"
              />
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                Порядок сортировки
              </span>
              <input
                type="number"
                name="sort_order"
                value={profForm.sort_order}
                onChange={handleProfFormChange}
                min={0}
                className="input-underline"
              />
            </label>

            {editingProfession && (
              <label className="flex items-center gap-3 self-end pb-2">
                <input
                  type="checkbox"
                  name="is_active"
                  checked={profForm.is_active}
                  onChange={handleProfFormChange}
                  className="w-5 h-5 accent-site-blue"
                />
                <span className="text-sm text-white">Активна</span>
              </label>
            )}

            <label className="flex flex-col gap-1 col-span-full">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                Описание
              </span>
              <textarea
                name="description"
                value={profForm.description}
                onChange={handleProfFormChange}
                rows={3}
                className="textarea-bordered"
              />
            </label>
          </div>

          <div className="flex gap-4 pt-2">
            <button
              type="submit"
              disabled={submitting}
              className="btn-blue !text-base !px-8 !py-2"
            >
              {submitting
                ? "Сохранение..."
                : editingProfession
                  ? "Сохранить"
                  : "Создать"}
            </button>
            <button
              type="button"
              onClick={closeProfessionForm}
              className="btn-line !w-auto !px-8"
            >
              Отмена
            </button>
          </div>
        </form>
      </div>
    );
  }

  /* ── Render: Rank Form (inline) ── */

  const renderRankForm = () => {
    if (!creatingRank && !editingRank) return null;
    return (
      <form
        className="bg-white/[0.03] border border-white/10 rounded-card p-4 flex flex-col gap-4 mt-3"
        onSubmit={handleRankSubmit}
      >
        <h4 className="text-white text-sm font-medium uppercase tracking-[0.06em]">
          {editingRank ? "Редактирование ранга" : "Создание ранга"}
        </h4>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <label className="flex flex-col gap-1">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
              Номер ранга
            </span>
            <input
              type="number"
              name="rank_number"
              value={rankForm.rank_number}
              onChange={handleRankFormChange}
              min={1}
              required
              className="input-underline"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
              Название
            </span>
            <input
              name="name"
              value={rankForm.name}
              onChange={handleRankFormChange}
              required
              className="input-underline"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
              Необходимый опыт
            </span>
            <input
              type="number"
              name="required_experience"
              value={rankForm.required_experience}
              onChange={handleRankFormChange}
              min={0}
              className="input-underline"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
              Иконка (URL)
            </span>
            <input
              name="icon"
              value={rankForm.icon}
              onChange={handleRankFormChange}
              className="input-underline"
            />
          </label>
          <label className="flex flex-col gap-1 col-span-full">
            <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
              Описание
            </span>
            <textarea
              name="description"
              value={rankForm.description}
              onChange={handleRankFormChange}
              rows={2}
              className="textarea-bordered"
            />
          </label>
        </div>
        <div className="flex gap-4">
          <button
            type="submit"
            disabled={submitting}
            className="btn-blue !text-base !px-6 !py-2"
          >
            {submitting ? "Сохранение..." : editingRank ? "Сохранить" : "Создать"}
          </button>
          <button
            type="button"
            onClick={closeRankForm}
            className="btn-line !w-auto !px-6"
          >
            Отмена
          </button>
        </div>
      </form>
    );
  };

  /* ── Render: Main list ── */

  return (
    <div className="w-full max-w-[1240px] mx-auto flex flex-col gap-5">
      <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em]">
        Профессии
      </h1>

      {/* Toolbar */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <p className="text-white/50 text-sm">
          Всего: {professions.length}
        </p>
        <button
          className="btn-blue !text-base !px-5 !py-2 whitespace-nowrap"
          onClick={openCreateProfession}
        >
          Создать профессию
        </button>
      </div>

      {loading && (
        <p className="text-white/50 text-sm py-8 text-center">Загрузка...</p>
      )}

      {!loading && professions.length === 0 && (
        <p className="text-white/50 text-sm py-8 text-center">
          Профессии не найдены
        </p>
      )}

      {/* Professions list */}
      <motion.div
        initial="hidden"
        animate="visible"
        variants={{
          hidden: {},
          visible: { transition: { staggerChildren: 0.05 } },
        }}
        className="flex flex-col gap-4"
      >
        {professions.map((p) => (
          <motion.div
            key={p.id}
            variants={{
              hidden: { opacity: 0, y: 10 },
              visible: { opacity: 1, y: 0 },
            }}
            className="gray-bg p-5"
          >
            {/* Profession header */}
            <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                {p.icon && (
                  <img
                    src={p.icon}
                    alt={p.name}
                    className="w-10 h-10 rounded-full object-cover"
                  />
                )}
                <div>
                  <h3 className="gold-text text-xl font-medium uppercase">
                    {p.name}
                  </h3>
                  <p className="text-white/40 text-xs">
                    slug: {p.slug} | id: {p.id} | порядок: {p.sort_order}
                    {!p.is_active && (
                      <span className="text-site-red ml-2">Неактивна</span>
                    )}
                  </p>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <button
                  onClick={() =>
                    setExpandedProfId(expandedProfId === p.id ? null : p.id)
                  }
                  className="text-sm text-white hover:text-site-blue transition-colors duration-200"
                >
                  {expandedProfId === p.id ? "Скрыть ранги" : `Ранги (${p.ranks?.length ?? 0})`}
                </button>
                <button
                  onClick={() => openSetRank(p.id)}
                  className="text-sm text-white hover:text-site-blue transition-colors duration-200"
                >
                  Установить ранг
                </button>
                <button
                  onClick={() => openEditProfession(p)}
                  className="text-sm text-white hover:text-site-blue transition-colors duration-200"
                >
                  Редактировать
                </button>
                <button
                  onClick={() => handleDeleteProfession(p.id)}
                  className="text-sm text-site-red hover:text-white transition-colors duration-200"
                >
                  Удалить
                </button>
              </div>
            </div>

            {p.description && (
              <p className="text-white/60 text-sm mt-2">{p.description}</p>
            )}

            {/* Expanded ranks */}
            <AnimatePresence>
              {expandedProfId === p.id && (
                <motion.div
                  initial={{ opacity: 0, height: 0 }}
                  animate={{ opacity: 1, height: "auto" }}
                  exit={{ opacity: 0, height: 0 }}
                  transition={{ duration: 0.2 }}
                  className="overflow-hidden"
                >
                  <div className="mt-4 border-t border-white/10 pt-4">
                    <div className="flex items-center justify-between mb-3">
                      <h4 className="text-white text-sm font-medium uppercase tracking-[0.06em]">
                        Ранги
                      </h4>
                      <button
                        onClick={() => openCreateRank(p.id)}
                        className="text-sm text-site-blue hover:text-white transition-colors duration-200"
                      >
                        + Добавить ранг
                      </button>
                    </div>

                    {(!p.ranks || p.ranks.length === 0) && (
                      <p className="text-white/30 text-sm">Рангов пока нет</p>
                    )}

                    {p.ranks && p.ranks.length > 0 && (
                      <div className="overflow-x-hidden">
                        <table className="w-full min-w-[500px]">
                          <thead>
                            <tr className="border-b border-white/10">
                              {["#", "Название", "Опыт", "Действия"].map(
                                (h, i) => (
                                  <th
                                    key={h}
                                    className={`text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-3 py-2 ${
                                      i === 3 ? "text-right" : "text-left"
                                    }`}
                                  >
                                    {h}
                                  </th>
                                ),
                              )}
                            </tr>
                          </thead>
                          <tbody>
                            {[...p.ranks]
                              .sort((a, b) => a.rank_number - b.rank_number)
                              .map((r) => (
                                <tr
                                  key={r.id}
                                  className="border-b border-white/5 hover:bg-white/[0.03] transition-colors duration-200"
                                >
                                  <td className="px-3 py-2 text-sm text-white/70">
                                    {r.rank_number}
                                  </td>
                                  <td className="px-3 py-2 text-sm text-white">
                                    {r.name}
                                    {r.description && (
                                      <span className="text-white/40 ml-2 text-xs">
                                        ({r.description})
                                      </span>
                                    )}
                                  </td>
                                  <td className="px-3 py-2 text-sm text-white/70">
                                    {r.required_experience}
                                  </td>
                                  <td className="px-3 py-2">
                                    <div className="flex justify-end gap-3">
                                      <button
                                        onClick={() => openEditRank(r, p.id)}
                                        className="text-sm text-white hover:text-site-blue transition-colors duration-200"
                                      >
                                        Изменить
                                      </button>
                                      <button
                                        onClick={() => handleDeleteRank(r.id)}
                                        className="text-sm text-site-red hover:text-white transition-colors duration-200"
                                      >
                                        Удалить
                                      </button>
                                    </div>
                                  </td>
                                </tr>
                              ))}
                          </tbody>
                        </table>
                      </div>
                    )}

                    {/* Inline rank form */}
                    {rankProfessionId === p.id && renderRankForm()}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </motion.div>
        ))}
      </motion.div>

      {/* Set Rank Modal */}
      <AnimatePresence>
        {setRankOpen && (
          <div className="modal-overlay" onClick={() => setSetRankOpen(false)}>
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, ease: "easeOut" }}
              className="modal-content gold-outline gold-outline-thick w-full max-w-[480px] max-h-[85vh] flex flex-col gap-4 overflow-auto gold-scrollbar mx-4"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 className="gold-text text-2xl font-medium uppercase tracking-[0.06em]">
                Установить ранг
              </h2>

              {/* Character search */}
              <div className="flex flex-col gap-2">
                <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                  Поиск персонажа
                </span>
                <input
                  className="input-underline"
                  placeholder="Имя персонажа"
                  value={charQuery}
                  onChange={(e) => setCharQuery(e.target.value)}
                />
                <ul className="flex flex-col max-h-[180px] overflow-auto gold-scrollbar border border-white/10 rounded-card">
                  {filteredChars.map((c) => (
                    <li
                      key={c.id}
                      className={`px-4 py-2.5 cursor-pointer text-sm transition-colors duration-200 ${
                        selectedChar?.id === c.id
                          ? "bg-site-blue/25 text-white"
                          : "text-white/70 hover:bg-white/[0.07]"
                      }`}
                      onClick={() => setSelectedChar(c)}
                    >
                      {c.name}{" "}
                      <span className="text-white/40">(id {c.id})</span>
                    </li>
                  ))}
                  {filteredChars.length === 0 && (
                    <li className="px-4 py-2.5 text-sm text-white/30">
                      Ничего не найдено
                    </li>
                  )}
                </ul>
              </div>

              {/* Rank number */}
              <label className="flex flex-col gap-1">
                <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                  Номер ранга
                </span>
                <input
                  type="number"
                  min={1}
                  value={setRankNumber}
                  onChange={(e) => setSetRankNumber(Number(e.target.value))}
                  className="input-underline"
                />
              </label>

              {/* Buttons */}
              <div className="flex justify-end gap-4 pt-2">
                <button
                  className="btn-blue !text-base !px-6 !py-2"
                  onClick={handleSetRank}
                  disabled={!selectedChar || submitting}
                >
                  {submitting ? "Установка..." : "Установить"}
                </button>
                <button
                  className="btn-line !w-auto !px-6"
                  onClick={() => setSetRankOpen(false)}
                >
                  Отмена
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default ProfessionsAdminPage;
