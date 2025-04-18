import { useState } from "react";
import ItemList from "./ItemList";
import ItemForm from "./ItemForm";
import IssueItemModal from "./IssueItemModal";
import styles from "./ItemsAdmin.module.scss";

export default function ItemsAdminPage() {
  const [editingId, setEditingId] = useState();
  const [creating, setCreating] = useState(false);
  const [issue, setIssue] = useState();
  const refreshKey = Math.random(); // force reload list after actions

  const closeForm = () => {
    setEditingId(undefined);
    setCreating(false);
  };

  return (
    <div className={styles.page} key={refreshKey}>
      {!editingId && !creating && (
        <ItemList
          onSelect={(id) => setEditingId(id)}
          onCreate={() => setCreating(true)}
        />
      )}

      {(editingId || creating) && (
        <ItemForm
          selected={editingId}
          onSuccess={closeForm}
          onCancel={closeForm}
        />
      )}

      {editingId && (
        <button onClick={() => setIssue(editingId)}>Выдать предмет</button>
      )}
      <IssueItemModal
        open={Boolean(issue)}
        onClose={() => setIssue(undefined)}
        itemId={issue}
      />
    </div>
  );
}
