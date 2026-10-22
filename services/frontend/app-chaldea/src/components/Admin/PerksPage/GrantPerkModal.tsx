import { useEffect, useState } from "react";
import { fetchCharacters } from "../../../api/characters";
import { fetchPerks, grantPerk } from "../../../api/perks";
import useDebounce from "../../../hooks/useDebounce";
import toast from "react-hot-toast";
import ModalShell from "../../CommonComponents/ModalShell/ModalShell";
import type { Perk } from "../../../types/perks";

/* ── Types ── */

interface Character {
  id: number;
  name: string;
}

interface GrantPerkModalProps {
  open: boolean;
  onClose: () => void;
}

/* ── Component ── */

const GrantPerkModal = ({ open, onClose }: GrantPerkModalProps) => {
  const [perkQ, setPerkQ] = useState("");
  const [charQ, setCharQ] = useState("");
  const [perks, setPerks] = useState<Perk[]>([]);
  const [chars, setChars] = useState<Character[]>([]);
  const [selectedPerk, setSelectedPerk] = useState<Perk | null>(null);
  const [selectedChar, setSelectedChar] = useState<Character | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const debPerk = useDebounce(perkQ);
  const debChar = useDebounce(charQ);

  /* Fetch perks */
  useEffect(() => {
    if (!open) return;
    fetchPerks({ page: 1, per_page: 200, search: debPerk || undefined })
      .then((res) => setPerks(res.items))
      .catch((e: Error) =>
        toast.error(e.message || "Не удалось загрузить перки"),
      );
  }, [debPerk, open]);

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
      setSelectedPerk(null);
      setSelectedChar(null);
      setPerkQ("");
      setCharQ("");
    }
  }, [open]);

  const visibleChars = chars.filter((c) =>
    c.name.toLowerCase().includes(debChar.toLowerCase()),
  );

  const handleGrant = async () => {
    if (!selectedChar || !selectedPerk) return;
    setSubmitting(true);
    try {
      await grantPerk(selectedChar.id, selectedPerk.id);
      toast.success(
        `Перк "${selectedPerk.name}" выдан персонажу "${selectedChar.name}"`,
      );
      onClose();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : "Ошибка при выдаче перка";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <ModalShell
      open={open}
      onClose={onClose}
      title="Выдать перк"
      size="sm"
      footer={
        <>
          <button
            className="btn-blue w-full sm:w-auto !text-base !px-6 !py-2"
            onClick={handleGrant}
            disabled={!selectedChar || !selectedPerk || submitting}
          >
            {submitting ? "Выдача..." : "Выдать"}
          </button>
          <button className="btn-line w-full sm:w-auto !px-6" onClick={onClose}>
            Отмена
          </button>
        </>
      }
    >
      <div className="flex flex-col gap-4">
        {/* Perk search */}
        <div className="flex flex-col gap-2">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
            Поиск перка
          </span>
          <input
            className="input-underline"
            placeholder="Название перка"
            value={perkQ}
            onChange={(e) => setPerkQ(e.target.value)}
          />
          <ul className="flex flex-col max-h-[180px] overflow-auto gold-scrollbar border border-white/10 rounded-card">
            {perks.map((p) => (
              <li
                key={p.id}
                className={`px-4 py-2.5 cursor-pointer text-sm transition-colors duration-200 ${
                  selectedPerk?.id === p.id
                    ? "bg-site-blue/25 text-white"
                    : "text-white/70 hover:bg-white/[0.07]"
                }`}
                onClick={() => setSelectedPerk(p)}
              >
                {p.name}{" "}
                <span className="text-white/40">(id {p.id})</span>
              </li>
            ))}
            {perks.length === 0 && (
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
      </div>
    </ModalShell>
  );
};

export default GrantPerkModal;
