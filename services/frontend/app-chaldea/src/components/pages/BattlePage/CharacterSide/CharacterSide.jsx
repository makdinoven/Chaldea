import s from "./CharacterSide.module.scss";
import PlayerCard from "../../../CommonComponents/PlayerCard/PlayerCard.jsx";
import CharacterResourcesList from "./CharacterResourcesList/CharacterResourcesList.jsx";
import CharacterInventory from "./CharacterInventory/CharacterInventory.jsx";
import EffectCircle from "./EffectCircle/EffectCircle.jsx";

const CharacterSide = ({
  isOpponent,
  characterData,
  setTurnData,
  runtimeData,
}) => {
  const effects = runtimeData?.active_effects[characterData.participant_id];

  return (
    <div className={s.character_side_container}>
      <div
        className={`${s.character_side_top_container} ${isOpponent ? s.opponent : ""}`}
      >
        <div className={s.card_wrapper}>
          <div
            className={`${s.effects_circle_container} ${isOpponent ? s.opponent : ""}`}
          >
            {effects &&
              Object.entries(
                effects.reduce((acc, effect) => {
                  const name = effect?.name || "";
                  const key = name.includes("StatModifier")
                    ? "StatModifier"
                    : name.includes("Resist")
                      ? "Resist"
                      : "Buff";

                  if (!acc[key]) acc[key] = [];
                  acc[key].push(effect);
                  return acc;
                }, {}),
              ).map(([type, groupedEffects]) => (
                <EffectCircle key={type} effects={groupedEffects} type={type} />
              ))}
          </div>
          <PlayerCard
            name={characterData.name}
            title={characterData.title}
            img={characterData.avatar}
          />
        </div>
        <CharacterResourcesList resources={characterData.resources} />
      </div>
      <CharacterInventory
        cooldowns={
          runtimeData.participants[characterData.participant_id].cooldowns
        }
        items={{ skills: characterData.skills, items: characterData.items }}
        setTurnData={setTurnData}
        isOpponent={isOpponent}
      />
    </div>
  );
};

export default CharacterSide;
