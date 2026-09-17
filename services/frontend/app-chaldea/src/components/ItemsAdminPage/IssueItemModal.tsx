import { useEffect, useState } from "react";
import { fetchCharacters } from "../../api/characters";
import { fetchItems, issueItem } from "../../api/items";
import useDebounce from "../../hooks/useDebounce";
import toast from "react-hot-toast";
import { itemGrantErrorMessage } from "../../api/errors";
import { motion, AnimatePresence } from "motion/react";
import type { ItemData } from "./ItemsAdminPage";

/* ── Types ── */

interface Character {
  id: number;
  name: string;
}

interface IssueItemModalProps {
  open: boolean;
  onClose: () => void;
  initialItem?: ItemData;
}

/* ── Component ── */

const IssueItemModal = ({ open, onClose, initialItem }: IssueItemModalProps) => {
  const [itemQ, setItemQ] = useState("");
  const [charQ, setCharQ] = useState("");
  const [items, setItems] = useState<ItemData[]>([]);
  const [chars, setChars] = useState<Character[]>([]);
  const [selectedItem, setSelectedItem] = useState<ItemData | null>(initialItem || null);
  const [selectedChar, setSelectedChar] = useState<Character | null>(null);
  const [qty, setQty] = useState(1);
  const [issuing, setIssuing] = useState(false);
  /** Inline copy of the last failure — the toast alone can be missed. */
  const [issueError, setIssueError] = useState<string | null>(null);

  const debItem = useDebounce(itemQ);
  const debChar = useDebounce(charQ);

  /* Fetch items */
  useEffect(() => {
    if (!open) return;
    fetchItems(debItem)
      .then(setItems)
      .catch((e: Error) => toast.error(e.message || "Не удалось загрузить предметы"));
  }, [debItem, open]);

  /* Fetch characters */
  useEffect(() => {
    if (!open) return;
    setSelectedItem(initialItem || null);
    fetchCharacters()
      .then(setChars)
      .catch((e: Error) => toast.error(e.message || "Не удалось загрузить персонажей"));
  }, [open, initialItem]);

  const visibleChars = chars.filter((c) =>
    c.name.toLowerCase().includes(debChar.toLowerCase()),
  );

  const give = async () => {
    if (!selectedChar || !selectedItem) return;
    setIssuing(true);
    setIssueError(null);
    try {
      await issueItem(selectedChar.id, selectedItem.id, qty);
      toast.success(`Предмет «${selectedItem.name}» выдан персонажу «${selectedChar.name}»`);
      onClose();
    } catch (e: unknown) {
      // FEAT-167: the grant route is now behind `items:update`, so 401/403 are
      // expected outcomes and must be explained in Russian, never swallowed.
      const msg = itemGrantErrorMessage(e);
      setIssueError(msg);
      toast.error(msg);
    } finally {
      setIssuing(false);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <div className="modal-overlay" onClick={onClose}>
          <motion.div
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.2, ease: "easeOut" }}
            className="modal-content gold-outline gold-outline-thick w-full max-w-[480px] mx-4 !p-5 sm:!p-8 max-h-[85dvh] flex flex-col gap-4 overflow-auto gold-scrollbar"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="gold-text text-2xl font-medium uppercase tracking-[0.06em]">
              Выдать предмет
            </h2>

            {/* ── Item search ── */}
            <div className="flex flex-col gap-2">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                Поиск предмета
              </span>
              <input
                className="input-underline"
                placeholder="Название предмета"
                value={itemQ}
                onChange={(e) => setItemQ(e.target.value)}
              />
              <ul className="flex flex-col max-h-[180px] overflow-auto gold-scrollbar border border-white/10 rounded-card">
                {items.map((i) => (
                  <li
                    key={i.id}
                    className={`px-4 py-2.5 cursor-pointer text-sm transition-colors duration-200 ${
                      selectedItem?.id === i.id
                        ? "bg-site-blue/25 text-white"
                        : "text-white/70 hover:bg-white/[0.07]"
                    }`}
                    onClick={() => setSelectedItem(i)}
                  >
                    {i.name}{" "}
                    <span className="text-white/40">(id {i.id})</span>
                  </li>
                ))}
                {items.length === 0 && (
                  <li className="px-4 py-2.5 text-sm text-white/30">Ничего не найдено</li>
                )}
              </ul>
            </div>

            {/* ── Character search ── */}
            <div className="flex flex-col gap-2">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                Поиск персонажа
              </span>
              <input
                className="input-underline"
                placeholder="Имя персонажа"
                value={charQ}
                onChange={(e) => setCharQ(e.target.value)}
              />
              <ul className="flex flex-col max-h-[180px] overflow-auto gold-scrollbar border border-white/10 rounded-card">
                {visibleChars.map((c) => (
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
                {visibleChars.length === 0 && (
                  <li className="px-4 py-2.5 text-sm text-white/30">Ничего не найдено</li>
                )}
              </ul>
            </div>

            {/* ── Quantity ── */}
            <label className="flex flex-col gap-1">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                Количество
              </span>
              <input
                type="number"
                min={1}
                value={qty}
                onChange={(e) => setQty(+e.target.value)}
                className="input-underline w-24"
              />
            </label>

            {/* ── Error ── */}
            {issueError && (
              <p
                role="alert"
                className="text-site-red text-sm leading-snug break-words rounded-card border border-site-red/30 bg-site-red/10 px-3 py-2"
              >
                {issueError}
              </p>
            )}

            {/* ── Buttons ── */}
            <div className="flex flex-col sm:flex-row sm:justify-end gap-3 sm:gap-4 pt-2">
              <button
                className="btn-blue !text-base !px-6 !py-2"
                onClick={give}
                disabled={!selectedChar || !selectedItem || issuing}
              >
                {issuing ? "Выдаём…" : "Выдать"}
              </button>
              <button
                className="btn-line !w-auto !px-6"
                onClick={onClose}
              >
                Отмена
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};

export default IssueItemModal;
