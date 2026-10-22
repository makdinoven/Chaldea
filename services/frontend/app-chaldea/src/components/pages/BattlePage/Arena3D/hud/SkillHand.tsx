import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { Ban, Hourglass, Info, Swords, X } from "lucide-react";
import {
  SkillCardModal,
  skillId,
  skillImage,
  skillName,
  useResolvedSkills,
  useSkillCard,
  type BattleItem,
  type BattleSkill,
  type SkillPickerProps,
} from "../../SkillPicker/SkillPicker";
import type {
  EffectEntry,
  ResolvedSkill,
} from "../../../../SkillTreeView/types";
import {
  damageLabel,
  describeEffect,
  pluralizeTurn,
} from "../../battleEffects";
import {
  COATING_BLOCKED_MESSAGE,
  describeActiveCoating,
  describeItemBattleLines,
  isCoatingBlocked,
} from "../../../../../utils/itemEffects";
import { effectIconOf } from "../arenaTypes";
import { RuneIcon } from "../EffectRunes";

const TITLES: Record<SkillPickerProps["type"], string> = {
  attack: "Навыки атаки",
  defense: "Навыки защиты",
  support: "Навыки поддержки",
  item: "Предметы",
};

// Who an effect lands on, as the card says it.
const TARGET_LABELS: Record<string, string> = {
  self: "на себя",
  enemy: "на цель",
  ally: "на союзника",
  all_allies: "на всех союзников",
  all_enemies: "на всех врагов",
};

// How a damage line spreads beyond the target (FEAT-146).
const AOE_LABELS: Record<string, string> = {
  splash: "всплеск",
  cleave: "рассечение",
  all: "по всем врагам",
  random_n: "по случайным",
};

// Fan geometry for the desktop hand (px / deg); a phone gets a scrolling strip.
const FAN_SPREAD = 760;
const FAN_MAX_STEP = 150;
const FAN_MAX_TILT = 6;
const FAN_DROP = 3;
// How long the chosen card flies up before it lands in its slot.
const PLAY_MS = 380;

const toEffectLike = (e: EffectEntry) => ({
  name: e.effect_name,
  attribute: e.attribute_key ?? undefined,
  magnitude: e.magnitude ?? 0,
  duration: e.duration ?? 0,
  secondary_magnitude: e.secondary_magnitude ?? null,
});

/** Where card `i` of `n` sits in the fan, and where it rises to on hover. */
const fanStyle = (i: number, n: number): CSSProperties => {
  const mid = (n - 1) / 2;
  const step = Math.min(FAN_MAX_STEP, FAN_SPREAD / Math.max(1, n));
  const tilt = Math.min(FAN_MAX_TILT, 30 / Math.max(1, n));
  const x = (i - mid) * step;
  const y = (i - mid) ** 2 * FAN_DROP;
  const base = `translateX(calc(-50% + ${x}px))`;
  return {
    "--fan": `${base} translateY(${y}px) rotate(${(i - mid) * tilt}deg)`,
    "--lift": `${base} translateY(-30px) rotate(0deg) scale(1.12)`,
  } as CSSProperties;
};

/** A resource cost set in a gem on the card's corner; red when the viewer can't pay it. */
const CostGem = ({
  kind,
  cost,
  short,
}: {
  kind: "energy" | "mana";
  cost: number;
  short: boolean;
}) => (
  <span
    title={kind === "energy" ? `Энергия: ${cost}` : `Мана: ${cost}`}
    className={`flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-extrabold tabular-nums text-white ring-2 shadow-[0_2px_4px_rgba(0,0,0,0.85),inset_0_-2px_3px_rgba(0,0,0,0.45)] [text-shadow:0_1px_2px_#000] sm:h-7 sm:w-7 sm:text-[11px] ${
      kind === "energy"
        ? "bg-[radial-gradient(circle_at_35%_30%,#fff2a8_0%,#c49a2c_55%,#4a3507_100%)]"
        : "bg-[radial-gradient(circle_at_35%_30%,#a8d8f0_0%,#2f6f9e_55%,#0b2236_100%)]"
    } ${short ? "ring-site-red" : "ring-[#d8b866]"}`}
  >
    {cost}
  </span>
);

interface CardFrameProps {
  image: string | null;
  name: string;
  disabled: boolean;
  selected: boolean;
  playing: boolean;
  corners: ReactNode;
  overlay?: ReactNode;
  children: ReactNode;
  onPlay: () => void;
  title?: string;
}

/** The gilded card body shared by skills and items. */
const CardFrame = ({
  image,
  name,
  disabled,
  selected,
  playing,
  corners,
  overlay,
  children,
  onPlay,
  title,
}: CardFrameProps) => (
  <button
    type="button"
    disabled={disabled}
    onClick={onPlay}
    title={title}
    className={`relative block h-[178px] w-[118px] lg:h-[236px] lg:w-[160px] rounded-[12px] bg-[linear-gradient(145deg,#f6e3a1_0%,#b8913f_28%,#6e5320_52%,#d8b866_78%,#7a5c24_100%)] p-[3px] text-left shadow-[0_10px_22px_rgba(0,0,0,0.8)] transition-[filter,box-shadow] duration-200 sm:h-[200px] sm:w-[136px] ${
      selected
        ? "shadow-[0_0_24px_rgba(240,217,92,0.85),0_10px_22px_rgba(0,0,0,0.8)]"
        : ""
    } ${disabled ? "cursor-not-allowed" : "cursor-pointer"} ${playing ? "animate-card-play" : ""}`}
  >
    <div className="flex h-full flex-col overflow-hidden rounded-[10px] bg-[linear-gradient(180deg,#1c150e,#0d0a07)]">
      <div className="relative h-[44%] shrink-0 overflow-hidden">
        {image ? (
          <img
            src={image}
            alt=""
            draggable={false}
            className="h-full w-full object-cover"
          />
        ) : (
          <div className="flex h-full w-full items-center justify-center bg-white/5 text-white/25">
            <Swords size={28} />
          </div>
        )}
        <div className="pointer-events-none absolute inset-0 shadow-[inset_0_0_12px_rgba(0,0,0,0.85)]" />
        {corners}
      </div>
      <p className="gold-text line-clamp-2 border-y border-[#b8913f]/50 bg-black/40 px-1.5 py-0.5 text-center text-[10px] font-semibold uppercase leading-tight tracking-wide sm:text-[11px] lg:text-xs">
        {name}
      </p>
      <div className="flex min-h-0 flex-1 flex-col gap-0.5 overflow-hidden px-1.5 py-1 text-[9px] leading-tight text-white/80 sm:text-[10px] lg:text-[11px]">
        {children}
      </div>
    </div>
    {overlay}
  </button>
);

/** The face of one skill: cost, what it hits for, what it leaves behind. */
const SkillFace = ({
  skill,
  resolved,
  cooldown,
  resources,
  selected,
  playing,
  onPlay,
  onInfo,
}: {
  skill: BattleSkill;
  resolved: ResolvedSkill | undefined;
  cooldown: number;
  resources: { mana: number; energy: number };
  selected: boolean;
  playing: boolean;
  onPlay: () => void;
  onInfo: () => void;
}) => {
  const costEnergy = resolved?.cost_energy ?? 0;
  const costMana = resolved?.cost_mana ?? 0;
  const shortEnergy = costEnergy > resources.energy;
  const shortMana = costMana > resources.mana;
  const short = shortEnergy || shortMana;
  const onCooldown = cooldown > 0;
  const shortText =
    shortMana && shortEnergy
      ? "Не хватает маны и энергии"
      : shortMana
        ? "Не хватает маны"
        : "Не хватает энергии";

  const corners = (
    <>
      <span className="absolute left-1 top-1">
        <CostGem kind="energy" cost={costEnergy} short={shortEnergy} />
      </span>
      <span className="absolute right-1 top-1">
        <CostGem kind="mana" cost={costMana} short={shortMana} />
      </span>
      {resolved && resolved.level > 0 && (
        <span className="absolute bottom-1 left-1 rounded-sm bg-black/75 px-1 text-[9px] font-semibold text-gold-light ring-1 ring-gold/40">
          ур. {resolved.level}
        </span>
      )}
    </>
  );

  // Cooldown: the card lies face down with an hourglass.
  const overlay = onCooldown ? (
    <div className="absolute inset-[3px] flex flex-col items-center justify-center gap-1 rounded-[10px] bg-[repeating-linear-gradient(45deg,#1a120a_0px,#1a120a_6px,#22180d_6px,#22180d_12px)] ring-1 ring-[#b8913f]/60">
      <Hourglass size={26} className="text-gold-light" />
      <span className="text-[10px] font-semibold uppercase tracking-wide text-gold-light">
        ещё {pluralizeTurn(cooldown)}
      </span>
      <span className="px-2 text-center text-[9px] text-white/50">
        {skillName(skill)}
      </span>
    </div>
  ) : short ? (
    <div className="pointer-events-none absolute inset-x-[3px] bottom-[3px] rounded-b-[10px] bg-site-red/85 py-0.5 text-center text-[9px] font-semibold uppercase tracking-wide text-white">
      {shortText}
    </div>
  ) : null;

  return (
    <div className="relative">
      <CardFrame
        image={skillImage(skill)}
        name={skillName(skill)}
        disabled={onCooldown || short}
        selected={selected}
        playing={playing}
        corners={corners}
        overlay={overlay}
        onPlay={onPlay}
      >
        <div className={short ? "opacity-50 grayscale" : ""}>
          {!resolved && <p className="text-white/40">Загрузка…</p>}
          {resolved?.damage_entries.map((d, i) => {
            const aoe =
              d.aoe_shape && d.aoe_shape !== "single"
                ? AOE_LABELS[d.aoe_shape]
                : null;
            const chance =
              d.chance != null && d.chance < 100 ? `, ${d.chance}%` : "";
            return (
              <p key={`d${i}`} className="flex items-start gap-1">
                <Swords size={10} className="mt-px shrink-0 text-[#ff9a7a]" />
                <span>
                  {/* `amount` is a bonus on top of the attribute + weapon base */}
                  {Number(d.amount) !== 0 && (
                    <span className="font-semibold text-[#ffb8a0]">+{d.amount} </span>
                  )}
                  {damageLabel(d.damage_type).toLowerCase()} урон
                  {aoe && <span className="text-white/50"> · {aoe}</span>}
                  {chance}
                </span>
              </p>
            );
          })}
          {resolved?.effects.map((e, i) => {
            const like = toEffectLike(e);
            const d = describeEffect(like);
            const chance =
              e.chance != null && e.chance < 100 ? ` · ${e.chance}%` : "";
            const side = e.target_side ? TARGET_LABELS[e.target_side] : null;
            return (
              <p
                key={`e${i}`}
                className="flex items-start gap-1"
                title={[d.label, d.detail].filter(Boolean).join(" — ")}
              >
                <RuneIcon
                  icon={effectIconOf(like)}
                  className={`mt-px h-2.5 w-2.5 shrink-0 ${d.positive ? "text-emerald-400" : "text-site-red"}`}
                />
                <span className="line-clamp-2">
                  <span
                    className={
                      d.positive ? "text-emerald-200" : "text-[#ffb4a2]"
                    }
                  >
                    {d.label}
                  </span>
                  {d.detail && (
                    <span className="text-white/50"> {d.detail}</span>
                  )}
                  {side && <span className="text-white/40"> · {side}</span>}
                  {chance}
                </span>
              </p>
            );
          })}
          {resolved && resolved.cooldown > 0 && (
            <p className="mt-auto text-white/40">
              перезарядка {pluralizeTurn(resolved.cooldown)}
            </p>
          )}
        </div>
      </CardFrame>
      {/* Sits on the card art's lower-right corner, outside the card's own button */}
      <button
        type="button"
        onClick={onInfo}
        aria-label="Карточка навыка"
        title="Карточка навыка"
        className="absolute right-1.5 top-[calc(44%-22px)] flex h-5 w-5 items-center justify-center rounded-full bg-black/75 text-white/70 ring-1 ring-white/25 transition-colors hover:text-gold"
      >
        <Info size={12} />
      </button>
    </div>
  );
};

const recoveryText = (it: BattleItem): string =>
  [
    it.health_recovery ? `+${it.health_recovery} HP` : "",
    it.mana_recovery ? `+${it.mana_recovery} маны` : "",
    it.energy_recovery ? `+${it.energy_recovery} энергии` : "",
    it.stamina_recovery ? `+${it.stamina_recovery} выносл.` : "",
  ]
    .filter(Boolean)
    .join(", ");

/** A consumable from a belt slot as a card: picture and what it does. */
const ItemFace = ({
  item,
  blocked,
  selected,
  playing,
  onPlay,
}: {
  item: BattleItem;
  blocked: boolean;
  selected: boolean;
  playing: boolean;
  onPlay: () => void;
}) => {
  const rec = recoveryText(item);
  return (
    <CardFrame
      image={item.image ?? null}
      name={item.name ?? `Предмет #${item.item_id}`}
      disabled={blocked}
      selected={selected}
      playing={playing}
      title={blocked ? COATING_BLOCKED_MESSAGE : undefined}
      // A belt slot holds exactly one item — no count on the card.
      corners={null}
      overlay={
        blocked ? (
          <div className="pointer-events-none absolute inset-x-[3px] bottom-[3px] rounded-b-[10px] bg-site-red/85 px-1 py-0.5 text-center text-[9px] font-semibold text-white">
            Яд уже нанесён
          </div>
        ) : null
      }
      onPlay={onPlay}
    >
      {rec && <p className="text-emerald-300">{rec}</p>}
      {describeItemBattleLines(item).map((line, i) => (
        <p key={i} className="line-clamp-2 text-site-blue">
          {line}
        </p>
      ))}
    </CardFrame>
  );
};

interface SkillHandProps extends SkillPickerProps {
  resources: { mana: number; energy: number };
}

/**
 * The 3D battle's chooser: the skills of one type (or the consumables) dealt as a
 * hand of cards over the table. Hover lifts a card; a click plays it into the slot.
 * Phones get a scrolling strip instead of a fan.
 */
const SkillHand = ({
  type,
  skills,
  items,
  cooldowns,
  characterId,
  weaponCoating = null,
  selectedId,
  onSelectSkill,
  onSelectItem,
  onClear,
  onClose,
  resources,
}: SkillHandProps) => {
  const isItems = type === "item";
  const { resolvedById, loading } = useResolvedSkills(
    skills,
    characterId,
    !isItems,
  );
  const { cardSkill, cardPerks, cardLoading, openCard, closeCard } =
    useSkillCard();
  const [playing, setPlaying] = useState<number | null>(null);

  useEffect(() => {
    // While the skill card (a ModalShell) is open, Escape closes only the card.
    if (cardSkill) return undefined;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose, cardSkill]);

  const sortedSkills = [...skills].sort((a, b) => {
    const la = resolvedById[skillId(a)]?.level_requirement ?? 999;
    const lb = resolvedById[skillId(b)]?.level_requirement ?? 999;
    return la !== lb ? la - lb : skillName(a).localeCompare(skillName(b));
  });

  /** The chosen card flies up, then lands in its slot. */
  const play = (id: number, commit: () => void) => {
    if (playing !== null) return;
    setPlaying(id);
    window.setTimeout(() => {
      commit();
      onClose();
    }, PLAY_MS);
  };

  const cards: { key: number; node: ReactNode }[] = isItems
    ? items.map((it) => ({
        key: it.item_id,
        node: (
          <ItemFace
            item={it}
            blocked={isCoatingBlocked(it, weaponCoating)}
            selected={selectedId === it.item_id}
            playing={playing === it.item_id}
            onPlay={() => play(it.item_id, () => onSelectItem(it))}
          />
        ),
      }))
    : sortedSkills.map((s) => {
        const id = skillId(s);
        const resolved = resolvedById[id];
        return {
          key: id,
          node: (
            <SkillFace
              skill={s}
              resolved={resolved}
              cooldown={cooldowns?.[String(id)] ?? 0}
              resources={resources}
              selected={selectedId === id}
              playing={playing === id}
              onInfo={() => openCard(s)}
              onPlay={() =>
                play(id, () =>
                  // Flag a skill that buffs / heals a chosen ally, so the battle
                  // screen offers an ally target (FEAT-143).
                  onSelectSkill({
                    ...s,
                    targets_ally: !!resolved?.effects?.some(
                      (e) => e.target_side === "ally",
                    ),
                  }),
                )
              }
            />
          ),
        };
      });

  const coatingText = isItems ? describeActiveCoating(weaponCoating) : null;
  const empty = !loading && cards.length === 0;

  return (
    <div
      className="fixed inset-0 z-[950]"
      role="dialog"
      aria-label={TITLES[type]}
    >
      {/* The table dims toward the hand; a click anywhere off the cards puts them away */}
      <div
        className="absolute inset-0 animate-fade-in bg-[linear-gradient(to_top,rgba(5,4,7,0.95),rgba(5,4,7,0.75)_50%,rgba(5,4,7,0.4))]"
        onClick={onClose}
      />

      <div className="pointer-events-none absolute inset-x-0 bottom-3 flex flex-col items-center gap-3 sm:bottom-[7vh] sm:gap-10">
        <div className="pointer-events-auto flex flex-wrap items-center justify-center gap-3 px-4">
          <h3 className="gold-text text-base font-medium uppercase tracking-[0.2em] sm:text-lg">
            {TITLES[type]}
          </h3>
          {selectedId != null && (
            <button
              type="button"
              onClick={() => {
                onClear();
                onClose();
              }}
              className="flex items-center gap-1.5 rounded-full border border-white/15 bg-black/50 px-3 py-1 text-xs text-white/70 transition-colors hover:border-site-red/60 hover:text-site-red"
            >
              <Ban size={13} /> Убрать из слота
            </button>
          )}
          <button
            type="button"
            onClick={onClose}
            aria-label="Закрыть"
            className="flex h-8 w-8 items-center justify-center rounded-full border border-white/15 bg-black/50 text-white/60 transition-colors hover:text-white"
          >
            <X size={16} />
          </button>
        </div>
        {coatingText && (
          <p className="pointer-events-auto mx-4 rounded-card border border-gold/30 bg-black/60 px-3 py-1.5 text-xs text-gold">
            {coatingText}
          </p>
        )}

        {loading ? (
          <div className="flex h-[200px] items-center justify-center">
            <div className="h-8 w-8 animate-spin rounded-full border-2 border-gold border-t-transparent" />
          </div>
        ) : empty ? (
          <p className="pointer-events-auto rounded-card bg-black/60 px-4 py-3 text-sm text-white/60">
            {isItems
              ? "Нет предметов в быстрых слотах"
              : "Нет навыков этого типа"}
          </p>
        ) : (
          <ul className="pointer-events-auto flex w-full snap-x gap-2 overflow-x-auto px-4 pb-2 pt-8 gold-scrollbar sm:relative sm:block sm:h-[230px] lg:h-[290px] sm:overflow-visible sm:p-0">
            {cards.map(({ key, node }, i) => (
              <li
                key={key}
                style={fanStyle(i, cards.length)}
                className="shrink-0 snap-center transition-transform duration-200 ease-out hover:z-50 sm:absolute sm:bottom-0 sm:left-1/2 sm:origin-bottom sm:[transform:var(--fan)] sm:hover:[transform:var(--lift)]"
              >
                <div
                  className="animate-hand-deal"
                  style={{ animationDelay: `${i * 45}ms` }}
                >
                  {node}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      {cardSkill && (
        <SkillCardModal
          resolved={resolvedById[skillId(cardSkill)] ?? null}
          perks={cardPerks}
          loading={cardLoading}
          onClose={closeCard}
        />
      )}
    </div>
  );
};

export default SkillHand;
