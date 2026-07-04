import PlayerCard from "../../../CommonComponents/PlayerCard/PlayerCard";
import CharacterResourcesList from "./CharacterResourcesList/CharacterResourcesList";
import EffectCircle from "./EffectCircle/EffectCircle";
import type { EffectLike } from "../battleEffects";

// Skill/item inventory panels were removed from participant cards (FEAT-143):
// you only ever act through the centre slot pickers, and only with your own
// skills — so a card now shows just portrait + resources + active effects.

type EffectGroup = "StatModifier" | "Resist" | "Buff";

interface CharacterSideCharacter {
  participant_id?: number;
  name?: string;
  title?: string;
  avatar?: string | null;
  resources?: unknown[];
}

interface CharacterSideProps {
  isOpponent?: boolean;
  characterData: CharacterSideCharacter;
  runtimeData: {
    active_effects?: Record<number, EffectLike[]>;
  };
}

const groupOf = (name: string): EffectGroup =>
  name.includes("StatModifier")
    ? "StatModifier"
    : name.includes("Resist")
      ? "Resist"
      : "Buff";

const CharacterSide = ({
  isOpponent = false,
  characterData,
  runtimeData,
}: CharacterSideProps) => {
  const effects =
    characterData.participant_id != null
      ? runtimeData?.active_effects?.[characterData.participant_id]
      : undefined;

  const grouped = (effects ?? []).reduce<Record<string, EffectLike[]>>(
    (acc, effect) => {
      const key = groupOf(effect?.name || "");
      (acc[key] ??= []).push(effect);
      return acc;
    },
    {},
  );

  return (
    <div
      className={`flex items-center gap-4 sm:gap-6 ${
        isOpponent ? "flex-row-reverse" : ""
      }`}
    >
      <div className="relative">
        <div
          className={`absolute top-2.5 z-10 flex flex-col gap-[5px] max-h-[90%] overflow-y-auto ${
            isOpponent ? "-right-4" : "-left-4"
          }`}
        >
          {Object.entries(grouped).map(([type, groupedEffects]) => (
            <EffectCircle
              key={type}
              effects={groupedEffects}
              type={type as EffectGroup}
            />
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
  );
};

export default CharacterSide;
