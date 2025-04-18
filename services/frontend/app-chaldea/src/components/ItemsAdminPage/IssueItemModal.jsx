import { useEffect, useState } from "react";
import styles from "./ItemsAdmin.module.scss";
import { fetchCharacters } from "../../api/characters";
import { fetchItems, issueItem } from "../../api/items";
import useDebounce from "../../hooks/useDebounce";

export default function IssueItemModal({ open, onClose, initialItem }) {
  const [itemQ, setItemQ] = useState("");
  const [charQ, setCharQ] = useState("");
  const [items, setItems] = useState([]);
  const [chars, setChars] = useState([]);
  const [selectedItem, setSelectedItem] = useState(initialItem || null);
  const [selectedChar, setSelectedChar] = useState(null);
  const [qty, setQty] = useState(1);
  const [error, setError] = useState("");

  const debItem = useDebounce(itemQ);
  const debChar = useDebounce(charQ);

  /* — предметы — */
  useEffect(() => {
    if (!open) return;
    fetchItems(debItem)
      .then(setItems)
      .catch((e) => setError(e.message));
  }, [debItem, open]);

  /* — персонажи — */
  useEffect(() => {
    if (!open) return;
    setSelectedItem(initialItem);
    fetchCharacters()
      .then(setChars)
      .catch((e) => setError(e.message));
  }, [open]);

  const visibleChars = chars.filter((c) =>
    c.name.toLowerCase().includes(debChar.toLowerCase()),
  );

  const give = async () => {
    try {
      await issueItem(selectedChar.id, selectedItem.id, qty);
      onClose();
    } catch (e) {
      setError(e.message);
    }
  };

  if (!open) return null;
  return (
    <div className={styles.backdrop}>
      <div className={styles.modal}>
        <h2>Выдать предмет</h2>
        {error && <p className={styles.error}>{error}</p>}

        {/* --- поиск предмета --- */}
        <div>
          <label>Поиск предмета</label>
          <input
            placeholder="Название предмета"
            value={itemQ}
            onChange={(e) => setItemQ(e.target.value)}
          />
          <ul className={styles.list}>
            {items.map((i) => (
              <li
                key={i.id}
                className={
                  selectedItem?.id === i.id ? styles.active : undefined
                }
                onClick={() => setSelectedItem(i)}
              >
                {i.name} (id {i.id})
              </li>
            ))}
          </ul>
        </div>

        {/* --- поиск персонажа --- */}
        <div>
          <label>Поиск персонажа</label>
          <input
            placeholder="Имя персонажа"
            value={charQ}
            onChange={(e) => setCharQ(e.target.value)}
          />
          <ul className={styles.list}>
            {visibleChars.map((c) => (
              <li
                key={c.id}
                className={
                  selectedChar?.id === c.id ? styles.active : undefined
                }
                onClick={() => setSelectedChar(c)}
              >
                {c.name} (id {c.id})
              </li>
            ))}
          </ul>
        </div>

        <label>
          Кол‑во
          <input
            type="number"
            min={1}
            value={qty}
            onChange={(e) => setQty(+e.target.value)}
          />
        </label>

        <div className={styles.actions}>
          <button
            className="btn btn--primary"
            onClick={give}
            disabled={!selectedChar || !selectedItem}
          >
            Выдать
          </button>
          <button className="btn btn--ghost" onClick={onClose}>
            Отмена
          </button>
        </div>
      </div>
    </div>
  );
}
