import { useEffect, useState } from "react";
import { fetchRules, deleteRule } from "../../../api/rules";
import type { GameRule } from "../../../api/rules";
import toast from "react-hot-toast";
import { motion } from "motion/react";

/* ── Props ── */

interface RuleListProps {
  onEdit: (rule: GameRule) => void;
  onCreate: () => void;
}

const RuleList = ({ onEdit, onCreate }: RuleListProps) => {
  const [rules, setRules] = useState<GameRule[]>([]);
  const [deleteTarget, setDeleteTarget] = useState<GameRule | null>(null);

  useEffect(() => {
    fetchRules()
      .then(setRules)
      .catch((e: Error) =>
        toast.error(e.message || "Не удалось загрузить правила")
      );
  }, []);

  const confirmDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteRule(deleteTarget.id);
      setRules((prev) => prev.filter((r) => r.id !== deleteTarget.id));
      toast.success("Правило удалено");
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Ошибка при удалении";
      toast.error(msg);
    } finally {
      setDeleteTarget(null);
    }
  };

  return (
    <div className="flex flex-col gap-5">
      <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em]">
        Правила
      </h1>

      {/* Create button */}
      <div className="flex items-center justify-end">
        <button className="btn-blue !text-base !px-6 !py-2" onClick={onCreate}>
          Создать правило
        </button>
      </div>

      {/* Table */}
      <div className="gray-bg overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="border-b border-white/10">
              <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">
                Порядок
              </th>
              <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">
                Фото
              </th>
              <th className="text-left text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">
                Название
              </th>
              <th className="text-right text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3">
                Действия
              </th>
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
            {rules.map((rule) => (
              <motion.tr
                key={rule.id}
                variants={{
                  hidden: { opacity: 0, y: 6 },
                  visible: { opacity: 1, y: 0 },
                }}
                className="border-b border-white/5 hover:bg-white/[0.05] transition-colors duration-200"
              >
                <td className="px-4 py-3 text-sm text-white/70">
                  {rule.sort_order}
                </td>
                <td className="px-4 py-3">
                  {rule.image_url ? (
                    <img
                      src={rule.image_url}
                      alt={rule.title}
                      className="w-[60px] h-[40px] object-cover rounded-[6px]"
                    />
                  ) : (
                    <div className="w-[60px] h-[40px] rounded-[6px] bg-white/[0.05] flex items-center justify-center text-white/20 text-xs">
                      Нет
                    </div>
                  )}
                </td>
                <td className="px-4 py-3 text-sm text-white">{rule.title}</td>
                <td className="px-4 py-3">
                  <div className="flex flex-col items-end gap-1.5">
                    <button
                      onClick={() => onEdit(rule)}
                      className="text-sm text-white hover:text-site-blue transition-colors duration-200"
                    >
                      Редактировать
                    </button>
                    <button
                      onClick={() => setDeleteTarget(rule)}
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

        {rules.length === 0 && (
          <p className="text-center text-white/50 text-sm py-8">
            Правила пока не добавлены
          </p>
        )}
      </div>

      {/* Delete confirmation modal */}
      {deleteTarget && (
        <div className="modal-overlay">
          <div className="modal-content gold-outline gold-outline-thick">
            <h2 className="gold-text text-2xl uppercase mb-4">
              Удаление правила
            </h2>
            <p className="text-white mb-6">
              Удалить правило &laquo;{deleteTarget.title}&raquo;? Это действие
              нельзя отменить.
            </p>
            <div className="flex gap-4">
              <button
                className="btn-blue !text-base !px-6 !py-2"
                onClick={confirmDelete}
              >
                Удалить
              </button>
              <button
                className="btn-line !w-auto !px-6"
                onClick={() => setDeleteTarget(null)}
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

export default RuleList;
