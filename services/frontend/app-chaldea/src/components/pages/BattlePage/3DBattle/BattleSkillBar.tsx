import { SKILLS_KEYS } from "../../../../helpers/commonConstants";

interface SkillSlot {
  id?: number;
  item_id?: number;
  name?: string;
  icon?: string;
  [key: string]: unknown;
}

interface BattleSkillBarProps {
  selectedSkills: Record<string, SkillSlot | null>;
  onSkillSelect?: (type: string) => void;
  isMyTurn?: boolean;
  controlFullSkip?: string | null;
  blockedSkills?: string[];
}

const getSkillColor = (type: string) => {
  switch (type) {
    case SKILLS_KEYS.attack:
      return "bg-red-600 hover:bg-red-500";
    case SKILLS_KEYS.defense:
      return "bg-blue-600 hover:bg-blue-500";
    case SKILLS_KEYS.support:
      return "bg-green-600 hover:bg-green-500";
    case SKILLS_KEYS.item:
      return "bg-yellow-600 hover:bg-yellow-500";
    default:
      return "bg-gray-600 hover:bg-gray-500";
  }
};

const getSkillLabel = (type: string) => {
  switch (type) {
    case SKILLS_KEYS.attack:
      return "Атака";
    case SKILLS_KEYS.defense:
      return "Защита";
    case SKILLS_KEYS.support:
      return "Поддержка";
    case SKILLS_KEYS.item:
      return "Предмет";
    default:
      return type;
  }
};

const BattleSkillBar = ({
  selectedSkills,
  onSkillSelect,
  isMyTurn = false,
  controlFullSkip,
  blockedSkills = [],
}: BattleSkillBarProps) => {
  const skillTypes = [
    SKILLS_KEYS.attack,
    SKILLS_KEYS.defense,
    SKILLS_KEYS.support,
    SKILLS_KEYS.item,
  ];

  const isBlocked = (type: string) =>
    blockedSkills.includes(type) || controlFullSkip !== null;

  return (
    <div className="absolute bottom-0 left-1/2 transform -translate-x-1/2 w-full max-w-4xl">
      {/* Основная панель */}
      <div className="rounded-t-lg bg-black/80 border-t border-l border-r border-gold/30 backdrop-blur-sm shadow-lg px-6 py-4">
        {/* Навыки */}
        <div className="flex gap-4 justify-center flex-wrap mb-4">
          {skillTypes.map((type) => {
            const skill = selectedSkills[type];
            const blocked = isBlocked(type);

            return (
              <button
                key={type}
                onClick={() => !blocked && onSkillSelect?.(type)}
                disabled={blocked || !isMyTurn}
                className={`
                  relative flex flex-col items-center gap-2 px-6 py-3 rounded-lg
                  transition-all duration-200 font-semibold uppercase text-sm
                  ${getSkillColor(type)}
                  ${blocked ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}
                  ${!isMyTurn ? "opacity-40 cursor-not-allowed" : ""}
                  active:scale-95
                `}
              >
                {/* Иконка или первая буква */}
                <div className="text-2xl w-8 h-8 flex items-center justify-center">
                  {skill?.icon ? "🎯" : "•"}
                </div>

                {/* Название */}
                <span className="text-xs">{getSkillLabel(type)}</span>

                {/* Статус блокировки */}
                {blocked && (
                  <div className="absolute -top-2 -right-2 w-5 h-5 rounded-full bg-red-600 text-white text-xs flex items-center justify-center font-bold">
                    ✕
                  </div>
                )}
              </button>
            );
          })}
        </div>

        {/* Выбранные навыки */}
        <div className="border-t border-gold/20 pt-4">
          <p className="text-xs text-gray-400 uppercase tracking-wide mb-2">Выбрано:</p>
          <div className="flex flex-wrap gap-2">
            {skillTypes.map((type) => {
              const skill = selectedSkills[type];
              if (!skill) return null;

              return (
                <div
                  key={type}
                  className="px-3 py-1 rounded-md bg-gold/10 border border-gold/50 text-xs text-gold font-semibold flex items-center gap-2"
                >
                  <span>{getSkillLabel(type)}:</span>
                  <span className="font-normal text-gold/80">
                    {skill.name || "Выбрано"}
                  </span>
                </div>
              );
            })}
          </div>

          {Object.values(selectedSkills).every((s) => s === null) && (
            <p className="text-xs text-gray-500 italic">Выберите действия для этого хода</p>
          )}
        </div>

        {/* Предупреждение о контроле */}
        {controlFullSkip && (
          <div className="mt-4 p-3 rounded-md bg-red-900/30 border border-red-500/50">
            <p className="text-xs text-red-400 font-semibold">
              ⚠️ {controlFullSkip}: ваш ход будет пропущен
            </p>
          </div>
        )}
      </div>
    </div>
  );
};

export default BattleSkillBar;
