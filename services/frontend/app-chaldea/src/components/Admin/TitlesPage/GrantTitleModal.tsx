import { useEffect, useState } from "react";
import { fetchCharacters } from "../../../api/characters";
import { fetchTitles, grantTitle } from "../../../api/titles";
import useDebounce from "../../../hooks/useDebounce";
import toast from "react-hot-toast";
import { motion, AnimatePresence } from "motion/react";
import type { Title } from "../../../types/titles";

/* ── Types ── */

interface Character {
  id: number;
  name: string;
}

interface GrantTitleModalProps {
  open: boolean;
  onClose: () => void;
}

/* ── Component ── */

const GrantTitleModal = ({ open, onClose }: GrantTitleModalProps) => {
  const [titleQ, setTitleQ] = useState("");
  const [charQ, setCharQ] = useState("");
  const [titles, setTitles] = useState<Title[]>([]);
  const [chars, setChars] = useState<Character[]>([]);
  const [selectedTitle, setSelectedTitle] = useState<Title | null>(null);
  const [selectedChar, setSelectedChar] = useState<Character | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const debTitle = useDebounce(titleQ);
  const debChar = useDebounce(charQ);

  /* Fetch titles */
  useEffect(() => {
    if (!open) return;
    fetchTitles({ page: 1, per_page: 200, search: debTitle || undefined })
      .then((res) => setTitles(res.items))
      .catch((e: Error) =>
        toast.error(e.message || "Не удалось загрузить титулы"),
      );
  }, [debTitle, open]);

  /* Fetch characters */
  useEffect(() => {
    if (!open) return;
    fetchCharacters()
      .then(setChars)
      .catch((e: Error) =>
        toast.error(e.message || "Не удалось загрузить персонажей"),
      );
  }, [open]);

  /* Reset on close */
  useEffect(() => {
    if (!open) {
      setSelectedTitle(null);
      setSelectedChar(null);
      setTitleQ("");
      setCharQ("");
    }
  }, [open]);

  const visibleChars = chars.filter((c) =>
    c.name.toLowerCase().includes(debChar.toLowerCase()),
  );

  const handleGrant = async () => {
    if (!selectedChar || !selectedTitle) return;
    setSubmitting(true);
    try {
      await grantTitle(selectedChar.id, selectedTitle.id_title);
      toast.success(
        `Титул "${selectedTitle.name}" выдан персонажу "${selectedChar.name}"`,
      );
      onClose();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Ошибка при выдаче титула";
      toast.error(msg);
    } finally {
      setSubmitting(false);
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
            className="modal-content gold-outline gold-outline-thick w-full max-w-[480px] max-h-[85vh] flex flex-col gap-4 overflow-auto gold-scrollbar mx-4"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="gold-text text-2xl font-medium uppercase tracking-[0.06em]">
              Выдать титул
            </h2>

            {/* Title search */}
            <div className="flex flex-col gap-2">
              <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                Поиск титула
              </span>
              <input
                className="input-underline"
                placeholder="Название титула"
                value={titleQ}
                onChange={(e) => setTitleQ(e.target.value)}
              />
              <ul className="flex flex-col max-h-[180px] overflow-auto gold-scrollbar border border-white/10 rounded-card">
                {titles.map((t) => (
                  <li
                    key={t.id_title}
                    className={`px-4 py-2.5 cursor-pointer text-sm transition-colors duration-200 ${
                      selectedTitle?.id_title === t.id_title
                        ? "bg-site-blue/25 text-white"
                        : "text-white/70 hover:bg-white/[0.07]"
                    }`}
                    onClick={() => setSelectedTitle(t)}
                  >
                    {t.name}{" "}
                    <span className="text-white/40">(id {t.id_title})</span>
                  </li>
                ))}
                {titles.length === 0 && (
                  <li className="px-4 py-2.5 text-sm text-white/30">
                    Ничего не найдено
                  </li>
                )}
              </ul>
            </div>

            {/* Character search */}
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
                  <li className="px-4 py-2.5 text-sm text-white/30">
                    Ничего не найдено
                  </li>
                )}
              </ul>
            </div>

            {/* Buttons */}
            <div className="flex justify-end gap-4 pt-2">
              <button
                className="btn-blue !text-base !px-6 !py-2"
                onClick={handleGrant}
                disabled={!selectedChar || !selectedTitle || submitting}
              >
                {submitting ? "Выдача..." : "Выдать"}
              </button>
              <button className="btn-line !w-auto !px-6" onClick={onClose}>
                Отмена
              </button>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
};

export default GrantTitleModal;
