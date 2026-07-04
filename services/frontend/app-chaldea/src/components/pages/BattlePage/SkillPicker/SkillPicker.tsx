// Battle skill / item picker (FEAT-143). Opened from a center slot: lists only
// the viewer's own skills of one type (or consumable items), shows cost +
// cooldown, lets you open the full skill card (reused from the profile), and
// sets the chosen entry into the turn slot. Replaces the old drag-from-inventory
// flow.
import { useEffect, useMemo, useState } from "react";
import axios from "axios";
import toast from "react-hot-toast";
import { X, Zap, Droplet, Clock, TrendingUp, Info, Ban } from "lucide-react";
import ResolvedSkillCard from "../../../ProfilePage/SkillsTab/ResolvedSkillCard";
import type {
  ResolvedSkill,
  SkillWithPerks,
} from "../../../SkillTreeView/types";

// --- Battle data shapes (flat snapshot rows) ---
export interface BattleSkill {
  id?: number;
  skill_id?: number;
  skill_name?: string;
  skill_image?: string;
  skill_type?: string;
  level?: number;
  skill?: { id?: number; name?: string; skill_image?: string; skill_type?: string };
  [key: string]: unknown;
}

export interface BattleItem {
  item_id: number;
  name?: string;
  image?: string;
  quantity?: number;
  health_recovery?: number;
  mana_recovery?: number;
  energy_recovery?: number;
  stamina_recovery?: number;
  slot_type?: string;
  [key: string]: unknown;
}

const TYPE_TITLES: Record<string, string> = {
  attack: "Навыки атаки",
  defense: "Навыки защиты",
  support: "Навыки поддержки",
  item: "Предметы",
};

const skillId = (s: BattleSkill): number =>
  Number(s.skill_id ?? s.id ?? s.skill?.id ?? 0);
const skillName = (s: BattleSkill): string =>
  s.skill_name ?? s.skill?.name ?? `Навык #${skillId(s)}`;
const skillImage = (s: BattleSkill): string | null =>
  s.skill_image ?? s.skill?.skill_image ?? null;

interface SkillPickerProps {
  type: "attack" | "defense" | "support" | "item";
  skills: BattleSkill[];
  items: BattleItem[];
  cooldowns: Record<string, number>;
  characterId: number;
  selectedId: number | null;
  onSelectSkill: (skill: BattleSkill) => void;
  onSelectItem: (item: BattleItem) => void;
  onClear: () => void;
  onClose: () => void;
}

const SkillPicker = ({
  type,
  skills,
  items,
  cooldowns,
  characterId,
  selectedId,
  onSelectSkill,
  onSelectItem,
  onClear,
  onClose,
}: SkillPickerProps) => {
  const isItems = type === "item";
  // skill_id -> resolved (cost / level_requirement / damage / effects)
  const [resolvedById, setResolvedById] = useState<Record<number, ResolvedSkill>>({});
  const [loading, setLoading] = useState(!isItems);
  // Skill whose full card is open (nested), plus its perks payload.
  const [cardSkill, setCardSkill] = useState<BattleSkill | null>(null);
  const [cardPerks, setCardPerks] = useState<SkillWithPerks | null>(null);
  const [cardLoading, setCardLoading] = useState(false);

  // Load resolved data for every skill of this type (cost + level for sorting).
  useEffect(() => {
    if (isItems || skills.length === 0) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    Promise.all(
      skills.map((s) =>
        axios
          .get<ResolvedSkill>(`/skills/${skillId(s)}/resolved`, {
            params: { character_id: characterId },
          })
          .then((r) => r.data)
          .catch(() => null),
      ),
    )
      .then((results) => {
        if (cancelled) return;
        const map: Record<number, ResolvedSkill> = {};
        results.forEach((r) => {
          if (r) map[r.skill_id] = r;
        });
        setResolvedById(map);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [skills, characterId, isItems]);

  // Sort skills by level requirement (1-5-10-…-50), then name.
  const sortedSkills = useMemo(() => {
    return [...skills].sort((a, b) => {
      const la = resolvedById[skillId(a)]?.level_requirement ?? 999;
      const lb = resolvedById[skillId(b)]?.level_requirement ?? 999;
      if (la !== lb) return la - lb;
      return skillName(a).localeCompare(skillName(b));
    });
  }, [skills, resolvedById]);

  const openCard = (s: BattleSkill) => {
    setCardSkill(s);
    setCardPerks(null);
    setCardLoading(true);
    axios
      .get<SkillWithPerks>(`/skills/${skillId(s)}`)
      .then((r) => setCardPerks(r.data))
      .catch(() => toast.error("Не удалось загрузить карточку навыка"))
      .finally(() => setCardLoading(false));
  };

  const recoveryText = (it: BattleItem): string => {
    const parts: string[] = [];
    if (it.health_recovery) parts.push(`+${it.health_recovery} HP`);
    if (it.mana_recovery) parts.push(`+${it.mana_recovery} маны`);
    if (it.energy_recovery) parts.push(`+${it.energy_recovery} энергии`);
    if (it.stamina_recovery) parts.push(`+${it.stamina_recovery} выносл.`);
    return parts.join(", ");
  };

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div
        className="modal-content gold-outline w-full max-w-lg mx-4 max-h-[85vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-3">
          <h3 className="gold-text text-lg font-medium uppercase">
            {TYPE_TITLES[type]}
          </h3>
          <button
            type="button"
            onClick={onClose}
            className="text-white/40 hover:text-white transition-colors"
            aria-label="Закрыть"
          >
            <X size={20} />
          </button>
        </div>

        {selectedId != null && (
          <button
            type="button"
            onClick={() => {
              onClear();
              onClose();
            }}
            className="mb-3 flex items-center gap-1.5 text-sm text-white/60 hover:text-site-red transition-colors self-start"
          >
            <Ban size={15} /> Убрать из слота
          </button>
        )}

        {/* Body */}
        <div className="flex-1 overflow-y-auto gold-scrollbar pr-1 -mr-1">
          {loading ? (
            <div className="flex justify-center py-10">
              <div className="w-7 h-7 border-2 border-gold border-t-transparent rounded-full animate-spin" />
            </div>
          ) : isItems ? (
            items.length === 0 ? (
              <p className="text-white/40 text-center py-8">Нет предметов</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {items.map((it) => {
                  const selected = selectedId === it.item_id;
                  const rec = recoveryText(it);
                  return (
                    <li key={it.item_id}>
                      <button
                        type="button"
                        onClick={() => {
                          onSelectItem(it);
                          onClose();
                        }}
                        className={`w-full flex items-center gap-3 p-2.5 rounded-card border text-left transition-all duration-200 ease-site ${
                          selected
                            ? "border-gold/60 bg-gold/10"
                            : "border-white/10 bg-white/[0.03] hover:border-white/25"
                        }`}
                      >
                        <ItemIcon image={it.image} />
                        <div className="min-w-0 flex-1">
                          <p className="text-white text-sm font-medium truncate">
                            {it.name ?? `Предмет #${it.item_id}`}
                            {it.quantity ? (
                              <span className="text-white/40"> ×{it.quantity}</span>
                            ) : null}
                          </p>
                          {rec && (
                            <p className="text-emerald-300/80 text-xs mt-0.5 truncate">
                              {rec}
                            </p>
                          )}
                        </div>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )
          ) : sortedSkills.length === 0 ? (
            <p className="text-white/40 text-center py-8">
              Нет навыков этого типа
            </p>
          ) : (
            <ul className="flex flex-col gap-2">
              {sortedSkills.map((s) => {
                const id = skillId(s);
                const resolved = resolvedById[id];
                const cd = cooldowns?.[String(id)] ?? 0;
                const onCd = cd > 0;
                const selected = selectedId === id;
                return (
                  <li key={id} className="flex items-stretch gap-1.5">
                    <button
                      type="button"
                      disabled={onCd}
                      onClick={() => {
                        onSelectSkill(s);
                        onClose();
                      }}
                      className={`flex-1 flex items-center gap-3 p-2.5 rounded-card border text-left transition-all duration-200 ease-site ${
                        onCd
                          ? "border-white/10 bg-white/[0.02] opacity-50 cursor-not-allowed"
                          : selected
                            ? "border-gold/60 bg-gold/10"
                            : "border-white/10 bg-white/[0.03] hover:border-white/25"
                      }`}
                    >
                      <SkillIcon image={skillImage(s)} />
                      <div className="min-w-0 flex-1">
                        <p className="text-white text-sm font-medium truncate">
                          {skillName(s)}
                        </p>
                        <div className="flex items-center gap-2 mt-1 flex-wrap text-xs">
                          {resolved && (
                            <span className="flex items-center gap-0.5 text-emerald-300/80">
                              <TrendingUp size={11} /> ур. {resolved.level_requirement}
                            </span>
                          )}
                          {resolved && (
                            <span className="flex items-center gap-0.5 text-amber-300/80">
                              <Zap size={11} /> {resolved.cost_energy}
                            </span>
                          )}
                          {resolved && (
                            <span className="flex items-center gap-0.5 text-sky-300/80">
                              <Droplet size={11} /> {resolved.cost_mana}
                            </span>
                          )}
                          {onCd && (
                            <span className="flex items-center gap-0.5 text-site-red">
                              <Clock size={11} /> КД: {cd}
                            </span>
                          )}
                        </div>
                      </div>
                    </button>
                    <button
                      type="button"
                      onClick={() => openCard(s)}
                      title="Карточка навыка"
                      className="shrink-0 w-10 flex items-center justify-center rounded-card border border-white/10 bg-white/[0.03] text-white/50 hover:text-gold hover:border-gold/40 transition-colors"
                    >
                      <Info size={16} />
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </div>

      {/* Nested skill card modal */}
      {cardSkill && (
        <div
          className="modal-overlay"
          onClick={(e) => {
            e.stopPropagation();
            setCardSkill(null);
          }}
        >
          <div
            className="modal-content gold-outline w-full max-w-md mx-4 max-h-[85vh] overflow-y-auto gold-scrollbar"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-end mb-1">
              <button
                type="button"
                onClick={() => setCardSkill(null)}
                className="text-white/40 hover:text-white transition-colors"
                aria-label="Закрыть"
              >
                <X size={20} />
              </button>
            </div>
            {cardLoading && !resolvedById[skillId(cardSkill)] ? (
              <div className="flex justify-center py-6">
                <div className="w-6 h-6 border-2 border-gold border-t-transparent rounded-full animate-spin" />
              </div>
            ) : resolvedById[skillId(cardSkill)] ? (
              <ResolvedSkillCard
                resolved={resolvedById[skillId(cardSkill)]}
                skill={cardPerks}
              />
            ) : (
              <p className="text-white/50 text-center py-4">
                Характеристики навыка недоступны
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
};

const SkillIcon = ({ image }: { image: string | null }) =>
  image ? (
    <img
      src={image}
      alt=""
      className="w-11 h-11 rounded-lg object-cover border border-white/10 shrink-0"
    />
  ) : (
    <div className="w-11 h-11 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center shrink-0 text-white/25">
      <Zap size={18} />
    </div>
  );

const ItemIcon = ({ image }: { image?: string }) =>
  image ? (
    <img
      src={image}
      alt=""
      className="w-11 h-11 rounded-lg object-cover border border-white/10 shrink-0"
    />
  ) : (
    <div className="w-11 h-11 rounded-lg bg-white/5 border border-white/10 flex items-center justify-center shrink-0 text-white/25">
      🧪
    </div>
  );

export default SkillPicker;
