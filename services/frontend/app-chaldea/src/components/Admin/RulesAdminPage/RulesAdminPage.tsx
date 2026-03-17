import { useState } from "react";
import RuleList from "./RuleList";
import RuleForm from "./RuleForm";
import type { GameRule } from "../../../api/rules";

const RulesAdminPage = () => {
  const [editingRule, setEditingRule] = useState<GameRule | undefined>();
  const [creating, setCreating] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const closeForm = () => {
    setEditingRule(undefined);
    setCreating(false);
    setRefreshKey((k) => k + 1);
  };

  return (
    <div className="w-full max-w-[1240px] mx-auto" key={refreshKey}>
      {!editingRule && !creating && (
        <RuleList
          onEdit={(rule: GameRule) => setEditingRule(rule)}
          onCreate={() => setCreating(true)}
        />
      )}
      {(editingRule || creating) && (
        <RuleForm
          rule={editingRule}
          onSuccess={closeForm}
          onCancel={closeForm}
        />
      )}
    </div>
  );
};

export default RulesAdminPage;
