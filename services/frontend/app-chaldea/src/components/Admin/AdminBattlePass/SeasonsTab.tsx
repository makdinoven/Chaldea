import { useState, useEffect, useCallback } from "react";
import toast from "react-hot-toast";
import { motion } from "motion/react";
import {
  getAdminSeasons,
  createSeason,
  updateSeason,
  deleteSeason,
} from "../../../api/battlePassAdmin";
import type {
  AdminSeason,
  SeasonCreatePayload,
  SeasonUpdatePayload,
} from "../../../api/battlePassAdmin";

/* ── Constants ── */

const SEGMENTS = [
  { value: "spring", label: "Весна" },
  { value: "summer", label: "Лето" },
  { value: "autumn", label: "Осень" },
  { value: "winter", label: "Зима" },
];

const SEGMENT_LABELS: Record<string, string> = Object.fromEntries(
  SEGMENTS.map((s) => [s.value, s.label]),
);

const emptyForm: SeasonCreatePayload = {
  name: "",
  segment_name: "spring",
  year: 1,
  start_date: "",
  end_date: "",
};

/* ── Helper: format datetime for display ── */
const fmtDate = (iso: string) => {
  if (!iso) return "\u2014";
  try {
    return new Date(iso).toLocaleDateString("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  } catch {
    return iso;
  }
};

/* ── Helper: format datetime for input[type=datetime-local] ── */
const toInputDateTime = (iso: string) => {
  if (!iso) return "";
  return iso.slice(0, 16); // "YYYY-MM-DDTHH:MM"
};

/* ── Component ── */

const SeasonsTab = () => {
  const [seasons, setSeasons] = useState<AdminSeason[]>([]);
  const [loading, setLoading] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState<SeasonCreatePayload>({ ...emptyForm });

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getAdminSeasons();
      setSeasons(res.items);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Не удалось загрузить сезоны";
      toast.error(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const openCreate = () => {
    setEditingId(null);
    setForm({ ...emptyForm });
    setShowForm(true);
  };

  const openEdit = (s: AdminSeason) => {
    setEditingId(s.id);
    setForm({
      name: s.name,
      segment_name: s.segment_name,
      year: s.year,
      start_date: toInputDateTime(s.start_date),
      end_date: toInputDateTime(s.end_date),
    });
    setShowForm(true);
  };

  const closeForm = () => {
    setShowForm(false);
    setEditingId(null);
    setForm({ ...emptyForm });
  };

  const handleSubmit = async () => {
    if (!form.name.trim()) {
      toast.error("Укажите название сезона");
      return;
    }
    if (!form.start_date || !form.end_date) {
      toast.error("Укажите даты начала и окончания");
      return;
    }

    try {
      if (editingId !== null) {
        const payload: SeasonUpdatePayload = {
          name: form.name,
          segment_name: form.segment_name,
          year: form.year,
          start_date: form.start_date,
          end_date: form.end_date,
        };
        await updateSeason(editingId, payload);
        toast.success("Сезон обновлён");
      } else {
        await createSeason(form);
        toast.success("Сезон создан");
      }
      closeForm();
      load();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Ошибка сохранения";
      toast.error(msg);
    }
  };

  const handleToggleActive = async (id: number, active: boolean) => {
    try {
      await updateSeason(id, { is_active: active });
      toast.success(active ? "Сезон активирован" : "Сезон деактивирован");
      load();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Ошибка обновления";
      toast.error(msg);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Удалить сезон? Это действие необратимо.")) return;
    try {
      await deleteSeason(id);
      toast.success("Сезон удалён");
      load();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Ошибка удаления";
      toast.error(msg);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      {/* Toolbar */}
      <div className="flex items-center justify-between">
        <h2 className="gold-text text-2xl font-medium uppercase">Сезоны</h2>
        <button className="btn-blue !text-base !px-5 !py-2" onClick={openCreate}>
          Создать сезон
        </button>
      </div>

      {/* Create/Edit form */}
      {showForm && (
        <div className="gray-bg p-6 flex flex-col gap-4">
          <h3 className="text-white text-lg font-medium">
            {editingId !== null ? "Редактирование сезона" : "Новый сезон"}
          </h3>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="flex flex-col gap-1">
              <label className="text-xs text-white/50 uppercase tracking-[0.06em]">
                Название
              </label>
              <input
                className="input-underline"
                placeholder="Весна Первого Года"
                value={form.name}
                onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs text-white/50 uppercase tracking-[0.06em]">
                Сегмент
              </label>
              <select
                className="input-underline"
                value={form.segment_name}
                onChange={(e) =>
                  setForm((f) => ({ ...f, segment_name: e.target.value }))
                }
              >
                {SEGMENTS.map((s) => (
                  <option key={s.value} value={s.value} className="bg-site-dark text-white">
                    {s.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs text-white/50 uppercase tracking-[0.06em]">
                Год
              </label>
              <input
                className="input-underline"
                type="number"
                min={1}
                value={form.year}
                onChange={(e) =>
                  setForm((f) => ({ ...f, year: parseInt(e.target.value) || 1 }))
                }
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs text-white/50 uppercase tracking-[0.06em]">
                Начало
              </label>
              <input
                className="input-underline"
                type="datetime-local"
                value={form.start_date}
                onChange={(e) =>
                  setForm((f) => ({ ...f, start_date: e.target.value }))
                }
              />
            </div>

            <div className="flex flex-col gap-1">
              <label className="text-xs text-white/50 uppercase tracking-[0.06em]">
                Окончание
              </label>
              <input
                className="input-underline"
                type="datetime-local"
                value={form.end_date}
                onChange={(e) =>
                  setForm((f) => ({ ...f, end_date: e.target.value }))
                }
              />
            </div>
          </div>

          <div className="flex gap-3 mt-2">
            <button className="btn-blue !text-base !px-5 !py-2" onClick={handleSubmit}>
              {editingId !== null ? "Сохранить" : "Создать"}
            </button>
            <button
              className="btn-line !text-base !px-5 !py-2"
              onClick={closeForm}
            >
              Отмена
            </button>
          </div>
        </div>
      )}

      {/* Loading */}
      {loading && (
        <p className="text-white/60 text-sm py-4">Загрузка...</p>
      )}

      {/* Table */}
      {!loading && (
        <div className="gray-bg overflow-x-auto">
          <table className="w-full min-w-[700px]">
            <thead>
              <tr className="border-b border-white/10">
                {["ID", "Название", "Сегмент", "Год", "Начало", "Окончание", "Grace", "Активен", "Действия"].map(
                  (h, i) => (
                    <th
                      key={h}
                      className={`text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3 ${
                        i === 8 ? "text-right" : "text-left"
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
              {seasons.map((s) => (
                <motion.tr
                  key={s.id}
                  variants={{
                    hidden: { opacity: 0, y: 6 },
                    visible: { opacity: 1, y: 0 },
                  }}
                  className="border-b border-white/5 hover:bg-white/[0.05] transition-colors duration-200"
                >
                  <td className="px-4 py-3 text-sm text-white/70">{s.id}</td>
                  <td className="px-4 py-3 text-sm text-white">{s.name}</td>
                  <td className="px-4 py-3 text-sm text-white/70">
                    {SEGMENT_LABELS[s.segment_name] ?? s.segment_name}
                  </td>
                  <td className="px-4 py-3 text-sm text-white/70">{s.year}</td>
                  <td className="px-4 py-3 text-sm text-white/70">{fmtDate(s.start_date)}</td>
                  <td className="px-4 py-3 text-sm text-white/70">{fmtDate(s.end_date)}</td>
                  <td className="px-4 py-3 text-sm text-white/70">{fmtDate(s.grace_end_date)}</td>
                  <td className="px-4 py-3 text-sm">
                    {s.is_active ? (
                      <span className="text-green-400">Да</span>
                    ) : (
                      <span className="text-white/40">Нет</span>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex flex-col items-end gap-1.5">
                      <button
                        onClick={() => handleToggleActive(s.id, !s.is_active)}
                        className={`text-sm transition-colors duration-200 ${
                          s.is_active
                            ? "text-yellow-400 hover:text-white"
                            : "text-green-400 hover:text-white"
                        }`}
                      >
                        {s.is_active ? "Деактивировать" : "Активировать"}
                      </button>
                      <button
                        onClick={() => openEdit(s)}
                        className="text-sm text-white hover:text-site-blue transition-colors duration-200"
                      >
                        Редактировать
                      </button>
                      <button
                        onClick={() => handleDelete(s.id)}
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

          {seasons.length === 0 && !loading && (
            <p className="text-center text-white/50 text-sm py-8">
              Сезоны не найдены
            </p>
          )}
        </div>
      )}
    </div>
  );
};

export default SeasonsTab;
