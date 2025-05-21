import s from "./CharacterSide.module.scss";
import PlayerCard from "../../../CommonComponents/PlayerCard/PlayerCard.jsx";
import CharacterResourcesList from "./CharacterResourcesList/CharacterResourcesList.jsx";
import CharacterInventory from "./CharacterInventory/CharacterInventory.jsx";

const CharacterSide = ({ isOpponent, characterData, setTurnData }) => {
  return (
    <div className={s.character_side_container}>
      <div
        className={`${s.character_side_top_container} ${isOpponent ? s.opponent : ""}`}
      >
        <PlayerCard
          name={characterData.name}
          title={characterData.title}
          img={characterData.avatar}
        />
        <CharacterResourcesList resources={characterData.resources} />
      </div>
      <CharacterInventory
        items={{ skills: characterData.skills, items: characterData.items }}
        setTurnData={setTurnData}
        isOpponent={isOpponent}
      />
    </div>
  );
};

export default CharacterSide;
