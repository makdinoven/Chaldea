import { useState } from "react";
import TitleList from "./TitleList";
import TitleForm from "./TitleForm";
import GrantTitleModal from "./GrantTitleModal";

const AdminTitlesPage = () => {
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
        <TitleList
          onSelect={(id: number) => setEditingId(id)}
          onCreate={() => setCreating(true)}
          onGrant={() => setGrantOpen(true)}
        />
      )}
      {(editingId || creating) && (
        <TitleForm
          selected={editingId}
          onSuccess={closeForm}
          onCancel={closeForm}
        />
      )}
      <GrantTitleModal
        open={grantOpen}
        onClose={() => {
          setGrantOpen(false);
          setRefreshKey((k) => k + 1);
        }}
      />
    </div>
  );
};

export default AdminTitlesPage;
