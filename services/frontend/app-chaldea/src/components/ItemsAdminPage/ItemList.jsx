import { useEffect, useState } from "react";
import styles from "./ItemsAdmin.module.scss";
import { deleteItem, fetchItems } from "../../api/items";
import useDebounce from "../../hooks/useDebounce";

export default function ItemList({ onSelect, onCreate, onIssue }) {
  const [items, setItems] = useState([]);
  const [query, setQuery] = useState("");
  const debounced = useDebounce(query);
  const [error, setError] = useState("");

  useEffect(() => {
    fetchItems(debounced)
      .then(setItems)
      .catch((e) => setError(e.message));
  }, [debounced]);

  const handleDelete = async (id) => {
    if (!confirm("Удалить предмет?")) return;
    try {
      await deleteItem(id);
      setItems((prev) => prev.filter((i) => i.id !== id));
    } catch (e) {
      setError(e.message);
    }
  };

  return (
    <div className={styles.wrapper}>
      {error && <p className={styles.error}>{error}</p>}

      <div className={styles.header}>
        <input
          placeholder="Поиск предметов"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button className="btn btn--primary" onClick={onCreate}>
          Создать предмет
        </button>
      </div>

      <table className={styles.table}>
        <thead>
          <tr>
            <th>ID</th>
            <th>Фото</th>
            <th>Название</th>
            <th>Тип</th>
            <th>Редкость</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((i) => (
            <tr key={i.id}>
              <td>{i.id}</td>
              <td>
                <img src={i?.image ? i.image : ""} alt="" />
              </td>
              <td>{i.name}</td>
              <td>{i.item_type}</td>
              <td>{i.item_rarity}</td>
              <td className={styles.actions}>
                <button onClick={() => onSelect(i.id)}>Редактировать</button>
                <button onClick={() => onIssue(i)}>Выдать</button>
                <button onClick={() => handleDelete(i.id)}>✖</button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
