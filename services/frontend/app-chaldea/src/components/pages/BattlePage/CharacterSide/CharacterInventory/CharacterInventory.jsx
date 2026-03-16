import s from "./CharacterInventory.module.scss";
import InventorySectionBtn from "./InventorySectionBtn/InventorySectionBtn";
import { useState } from "react";
import InventorySection from "./InventorySection/InventorySection";
import InventoryItemsBtnIcon from "../../../../../assets/Icons/InventoryItemsBtnIcon";
import InventorySkillsBtnIcon from "../../../../../assets/Icons/InventorySkillsBtnIcon";

const CharacterInventory = ({ items, isOpponent, setTurnData, cooldowns }) => {
  const INVENTORY_SECTIONS = [
    {
      name: "Навыки",
      items: items.skills,
      icon: <InventorySkillsBtnIcon />,
    },
    {
      name: "Предметы",
      items: items.items.flatMap((item) =>
        Array.from({ length: item.quantity || 1 }, (_, index) => ({
          ...item,
          _cloneKey: `${item.id}-item-${index}`,
        })),
      ),
      icon: <InventoryItemsBtnIcon />,
    },
  ];

  const [openedSection, setOpenedSection] = useState(INVENTORY_SECTIONS[0]);
  const handleSelectSection = (name) => {
    const section = INVENTORY_SECTIONS.find((sec) => sec.name === name);
    if (section) {
      setOpenedSection(section);
    }
  };

  return (
    <div className={`${s.character_inventory} ${isOpponent ? s.opponent : ""}`}>
      <div className={s.inventory_sections_btns}>
        {INVENTORY_SECTIONS.map((sec) => (
          <div key={sec.name} className={s.btn_wrapper}>
            <InventorySectionBtn
              handleClick={handleSelectSection}
              isActive={openedSection.name === sec.name}
              name={sec.name}
              icon={sec.icon}
            />
          </div>
        ))}
      </div>
      <span className={s.line}></span>
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
