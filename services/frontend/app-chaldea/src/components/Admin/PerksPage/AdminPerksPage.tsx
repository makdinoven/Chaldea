import { useState } from "react";
import PerkList from "./PerkList";
import PerkForm from "./PerkForm";
import GrantPerkModal from "./GrantPerkModal";

const AdminPerksPage = () => {
  const [editingId, setEditingId] = useState<number | undefined>();
  const [creating, setCreating] = useState(false);
  const [grantOpen, setGrantOpen] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const closeForm = () => {
    setEditingId(undefined);
    setCreating(false);
    setRefreshKey((k) => k + 1);
  };

  return (
    <div className="w-full max-w-[1240px] mx-auto" key={refreshKey}>
      {!editingId && !creating && (
        <PerkList
          onSelect={(id: number) => setEditingId(id)}
          onCreate={() => setCreating(true)}
          onGrant={() => setGrantOpen(true)}
        />
      )}
      {(editingId || creating) && (
        <PerkForm
          selected={editingId}
          onSuccess={closeForm}
          onCancel={closeForm}
        />
      )}
      <GrantPerkModal
        open={grantOpen}
        onClose={() => {
          setGrantOpen(false);
          setRefreshKey((k) => k + 1);
        }}
      />
    </div>
  );
};

export default AdminPerksPage;
