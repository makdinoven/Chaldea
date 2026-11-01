import PlayerCard from "../../../CommonComponents/PlayerCard/PlayerCard";
import CharacterResourcesList from "./CharacterResourcesList/CharacterResourcesList";
import EffectCircle from "./EffectCircle/EffectCircle";
import type { EffectLike } from "../battleEffects";
import type { SubclassPassive } from "../../../../api/subclasses";
import { Shield } from "lucide-react";
import PassiveBadge from "../../../CommonComponents/PassiveBadge/PassiveBadge";

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
  /** FEAT-188 — subclass passive; null / absent for mobs and old battles. */
  passive?: SubclassPassive | null;
  /** FEAT-190 — total passive shield (absorbs damage before HP); 0 / absent = none. */
  shield?: number;
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

  const shield = Math.round(Number(characterData.shield ?? 0));
  const hasShield = Number.isFinite(shield) && shield > 0;

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
        {/* FEAT-188: subclass passive on the card's inner top corner — the
            effect circles take the outer edge. Its tap does not pick the target. */}
        {characterData.passive && (
          <PassiveBadge
            passive={characterData.passive}
            size="md"
            className={`absolute top-1.5 z-10 ${isOpponent ? "left-1.5" : "right-1.5"}`}
          />
        )}
        {/* FEAT-190: a passive shield (Священный обет / Прилив) — under the
            passive badge on the same inner corner; hidden when there is none. */}
        {hasShield && (
          <span
            title={`Щит: ${shield} — поглощает урон до здоровья`}
            className={`pointer-events-none absolute z-10 flex items-center gap-0.5 rounded-full bg-black/70 px-1.5 py-0.5 text-[10px] font-medium tabular-nums text-white ring-1 ring-site-blue/70 shadow-[0_0_8px_rgba(118,166,189,0.5)] sm:text-[11px] ${
              characterData.passive ? "top-10" : "top-1.5"
            } ${isOpponent ? "left-1.5" : "right-1.5"}`}
          >
            <Shield size={11} className="shrink-0 text-site-blue" />
            Щит {shield}
          </span>
        )}
      </div>
      <CharacterResourcesList resources={characterData.resources} />
    </div>
  );
};

export default CharacterSide;
