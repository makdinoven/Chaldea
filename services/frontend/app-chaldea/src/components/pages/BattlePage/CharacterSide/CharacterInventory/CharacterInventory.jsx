import s from "./CharacterInventory.module.scss";
import InventorySectionBtn from "./InventorySectionBtn/InventorySectionBtn.jsx";
import { useState } from "react";
import InventorySection from "./InventorySection/InventorySection.jsx";
import InventoryItemsBtnIcon from "../../../../../assets/Icons/InventoryItemsBtnIcon.jsx";
import InventorySkillsBtnIcon from "../../../../../assets/Icons/InventorySkillsBtnIcon.jsx";

const CharacterInventory = ({ items, isOpponent, setTurnData }) => {
  const INVENTORY_SECTIONS = [
    {
      name: "Навыки",
      items: items.skills,
      icon: <InventorySkillsBtnIcon />,
    },
    {
      name: "Предметы",
      items: items.items,
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
          <div className={s.btn_wrapper}>
            <InventorySectionBtn
              key={sec.name}
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
      />
    </div>
  );
};

export default CharacterInventory;
