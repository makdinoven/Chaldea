import InventorySectionBtn from "./InventorySectionBtn/InventorySectionBtn";
import { useState, ReactNode, Dispatch, SetStateAction } from "react";
import InventorySection from "./InventorySection/InventorySection";
import InventoryItemsBtnIcon from "../../../../../assets/IconComponents/InventoryItemsBtnIcon";
import InventorySkillsBtnIcon from "../../../../../assets/IconComponents/InventorySkillsBtnIcon";

interface SkillItem {
  id: number;
  skill_type?: string;
  name?: string;
  image?: string;
  rank_image?: string;
  rank_name?: string;
  cooldown?: number;
  cost_energy?: number;
  cost_mana?: number;
  damage_entries?: unknown[];
  effects?: unknown[];
  [key: string]: unknown;
}

interface FastSlotItem {
  item_id: number;
  slot_type: string;
  name?: string;
  image?: string;
  quantity?: number;
  health_recovery?: number;
  mana_recovery?: number;
  energy_recovery?: number;
  stamina_recovery?: number;
  [key: string]: unknown;
}

interface InventoryItems {
  skills: SkillItem[];
  items: FastSlotItem[];
}

interface InventorySectionData {
  name: string;
  items: (SkillItem | (FastSlotItem & { _cloneKey: string }))[];
  icon: ReactNode;
}

interface CharacterInventoryProps {
  items: InventoryItems;
  isOpponent: boolean;
  setTurnData: Dispatch<SetStateAction<Record<string, unknown>>> | null;
  cooldowns: Record<number, number> | null;
}

const CharacterInventory = ({
  items,
  isOpponent,
  setTurnData,
  cooldowns,
}: CharacterInventoryProps) => {
  const INVENTORY_SECTIONS: InventorySectionData[] = [
    {
      name: "Навыки",
      items: items.skills,
      icon: <InventorySkillsBtnIcon />,
    },
    {
      name: "Предметы",
      items: items.items.map((item) => ({
        ...item,
        _cloneKey: `${item.slot_type}-item`,
      })),
      icon: <InventoryItemsBtnIcon />,
    },
  ];

  const [openedSectionName, setOpenedSectionName] = useState("Навыки");

  const openedSection =
    INVENTORY_SECTIONS.find((sec) => sec.name === openedSectionName) ??
    INVENTORY_SECTIONS[0];

  const handleSelectSection = (name: string) => {
    setOpenedSectionName(name);
  };

  return (
    <div
      className={`flex gap-3.5 relative ${isOpponent ? "flex-row-reverse" : ""}`}
    >
      <div
        className={`absolute top-0 flex flex-col items-center gap-2 ${isOpponent ? "right-0" : "left-0"}`}
      >
        {INVENTORY_SECTIONS.map((sec) => (
          <div
            key={sec.name}
            className="flex items-center justify-center w-[68px] h-[68px]"
          >
            <InventorySectionBtn
              handleClick={handleSelectSection}
              isActive={openedSection.name === sec.name}
              name={sec.name}
              icon={sec.icon}
            />
          </div>
        ))}
      </div>
      <span
        className={`block w-0.5 h-full bg-gradient-to-b from-transparent via-[#999] to-transparent ${isOpponent ? "mr-[88px]" : "ml-[88px]"}`}
      />
      <InventorySection
        setTurnData={setTurnData}
        isOpponent={isOpponent}
        items={openedSection.items}
        cooldowns={cooldowns}
      />
    </div>
  );
};

export default CharacterInventory;
