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
      {/*<BackButton />*/}
      {!editingId && !creating && (
        <ItemList
          onSelect={(id) => setEditingId(id)}
          onCreate={() => setCreating(true)}
          onIssue={(id) => setIssue(id)}
        />
      )}
      {(editingId || creating) && (
        <ItemForm
          selected={editingId}
          onSuccess={closeForm}
          onCancel={closeForm}
        />
      )}
      <IssueItemModal
        open={Boolean(issue)}
        onClose={() => setIssue(undefined)}
        initialItem={issue}
      />
    </div>
  );
}
