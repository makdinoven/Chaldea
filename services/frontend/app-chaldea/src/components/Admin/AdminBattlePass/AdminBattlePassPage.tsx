import { useState } from "react";
import SeasonsTab from "./SeasonsTab";
import LevelsTab from "./LevelsTab";
import MissionsTab from "./MissionsTab";

const TABS = [
  { key: "seasons", label: "Сезоны" },
  { key: "levels", label: "Уровни и награды" },
  { key: "missions", label: "Задания" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

const AdminBattlePassPage = () => {
  const [activeTab, setActiveTab] = useState<TabKey>("seasons");

  return (
    <div className="w-full max-w-[1240px] mx-auto">
      <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em] mb-8">
        Батл Пасс — Администрирование
      </h1>

      {/* Tabs */}
      <div className="flex flex-wrap gap-2 mb-6">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-5 py-2 text-sm font-medium uppercase tracking-[0.06em] rounded-card transition-colors duration-200 ${
              activeTab === tab.key
                ? "bg-site-blue text-white"
                : "bg-white/[0.07] text-white/60 hover:text-white hover:bg-white/[0.12]"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === "seasons" && <SeasonsTab />}
      {activeTab === "levels" && <LevelsTab />}
      {activeTab === "missions" && <MissionsTab />}
    </div>
  );
};

export default AdminBattlePassPage;
