import { useEffect, useState } from "react";
import styles from "./ItemsAdmin.module.scss";
import { fetchCharacters } from "../../api/characters";
import { issueItem } from "../../api/items";
import useDebounce from "../../hooks/useDebounce";

export default function IssueItemModal({ open, onClose, itemId }) {
  const [chars, setChars] = useState([]);
  const [filter, setFilter] = useState("");
  const [selected, setSelected] = useState();
  const [qty, setQty] = useState(1);
  const [error, setError] = useState();

  const deb = useDebounce(filter);

  useEffect(() => {
    if (!open) return;
    fetchCharacters()
      .then(setChars)
      .catch((e) => setError(e.message));
  }, [open]);

  const visible = chars.filter((c) =>
    c.name.toLowerCase().includes(deb.toLowerCase()),
  );

  const give = async () => {
    try {
      await issueItem(selected.id, itemId, qty);
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
        <input
          placeholder="Поиск персонажа"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        />
        <ul className={styles.list}>
          {visible.map((c) => (
            <li
              key={c.id}
              className={selected?.id === c.id ? styles.active : ""}
              onClick={() => setSelected(c)}
            >
              {c.name}
            </li>
          ))}
        </ul>
        <label>
          Кол-во
          <input
            type="number"
            min={1}
            value={qty}
            onChange={(e) => setQty(+e.target.value)}
          />
        </label>
        <div className={styles.actions}>
          <button onClick={give} disabled={!selected}>
            Выдать
          </button>
          <button onClick={onClose}>Отмена</button>
        </div>
      </div>
    </div>
  );
}
