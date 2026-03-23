import { motion } from 'motion/react';
import type { BestiaryEntry } from '../../api/bestiary';
import { ArcaneCircle, ArcaneSeal } from './GrimoireMagic';

const titleFont = "'MedievalSharp', 'Georgia', serif";
const scriptFont = "'Marck Script', 'Georgia', cursive";
const statFont = "'Cormorant Garamond', 'Georgia', serif";

const inkColor = '#2a1a08';
const inkLight = '#5a4020';
const inkFaded = '#8a7050';

const TIER_STYLE: Record<string, { label: string; color: string }> = {
  normal: { label: 'Обычный', color: '#5a4a2a' },
  elite: { label: 'Элитный', color: '#6a3a8a' },
  boss: { label: 'Босс', color: '#8b2020' },
};

const STAT_LABELS: Record<string, string> = {
  strength: 'Сила',
  agility: 'Ловкость',
  endurance: 'Выносливость',
  intelligence: 'Интеллект',
  wisdom: 'Мудрость',
  luck: 'Удача',
  res_physical: 'Сопр. физическому',
  res_magic: 'Сопр. магии',
  res_fire: 'Сопр. огню',
  res_ice: 'Сопр. холоду',
  res_electricity: 'Сопр. молнии',
  res_catting: 'Сопр. режущему',
  res_crushing: 'Сопр. дробящему',
  res_piercing: 'Сопр. колющему',
  res_watering: 'Сопр. воде',
  res_sainting: 'Сопр. святости',
  res_wind: 'Сопр. ветру',
  res_damning: 'Сопр. проклятию',
};

const MAIN_STATS = ['strength', 'agility', 'endurance', 'intelligence', 'wisdom', 'luck'];

/* ── Section that "bleeds through" with staggered delay ── */
const Section = ({ title, children, delay = 0 }: { title: string; children: React.ReactNode; delay?: number }) => (
  <motion.div
    className="mb-5"
    initial={{ opacity: 0, filter: 'blur(4px)' }}
    animate={{ opacity: 1, filter: 'blur(0px)' }}
    transition={{ duration: 0.4, delay, ease: 'easeOut' }}
  >
    <h3
      className="text-sm sm:text-base tracking-wider mb-2 text-center"
      style={{ fontFamily: scriptFont, color: '#4a3018' }}
    >
      <span style={{ color: inkFaded, marginRight: '6px' }}>&mdash;</span>
      {title}
      <span style={{ color: inkFaded, marginLeft: '6px' }}>&mdash;</span>
    </h3>
    {children}
  </motion.div>
);

/* ── Arcane sealed / hidden content ── */
const LockedContent = ({ tier }: { tier: string }) => {
  const message = tier === 'normal'
    ? 'Убейте этого монстра, чтобы узнать его секреты'
    : 'Этот противник окутан тайной. Победите его, чтобы раскрыть информацию';

  return (
    <div className="flex flex-col items-center gap-2 py-3">
      <ArcaneSeal size={40} />
      <span
        className="text-xs sm:text-sm text-center"
        style={{ fontFamily: scriptFont, color: inkFaded }}
      >
        {message}
      </span>
    </div>
  );
};

/* ═══════════════════════════════════════════════
   Mob detail page inside the scroll
   ═══════════════════════════════════════════════ */
const ScrollMobDetail = ({ entry }: { entry: BestiaryEntry }) => {
  const tier = TIER_STYLE[entry.tier] ?? TIER_STYLE.normal;
  const hasDescription = entry.description !== null;
  const hasAttributes = entry.base_attributes !== null;
  const hasSkills = entry.skills !== null;
  const hasLoot = entry.loot_entries !== null;
  const hasSpawns = entry.spawn_locations !== null;

  return (
    <div>
      {/* ── Header: Avatar + Name ── */}
      <div className="flex flex-col items-center mb-6">
        {/* Avatar with arcane circle behind */}
        <div className="relative mb-4">
          {/* Faint arcane circle */}
          <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 opacity-[0.08]">
            <ArcaneCircle size={220} />
          </div>

          {/* Avatar frame */}
          <motion.div
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            transition={{ duration: 0.4, delay: 0.1 }}
            className="relative w-36 h-36 sm:w-44 sm:h-44"
          >
            <div
              className="absolute inset-0 rounded-sm"
              style={{
                border: `2px solid ${tier.color}40`,
                boxShadow: `inset 0 0 4px rgba(100,70,30,0.2), 0 2px 8px rgba(100,70,30,0.15)`,
              }}
            />
            <div className="absolute inset-[4px] rounded-[1px] overflow-hidden"
              style={{ background: 'rgba(180,160,120,0.2)' }}
            >
              {entry.avatar ? (
                <img
                  src={entry.avatar}
                  alt={entry.name}
                  className="w-full h-full object-cover"
                  style={{ filter: 'sepia(0.15) contrast(1.05)' }}
                />
              ) : (
                <div className="w-full h-full flex items-center justify-center">
                  <span style={{ fontFamily: titleFont, color: 'rgba(120,90,40,0.2)', fontSize: '48px' }}>?</span>
                </div>
              )}
              <div
                className="absolute inset-0 pointer-events-none"
                style={{ boxShadow: 'inset 0 0 15px rgba(100,70,30,0.2)' }}
              />
            </div>
            {/* Corner accents */}
            <div className="absolute -top-1 -left-1 w-3 h-3 border-t-2 border-l-2" style={{ borderColor: `${tier.color}50` }} />
            <div className="absolute -top-1 -right-1 w-3 h-3 border-t-2 border-r-2" style={{ borderColor: `${tier.color}50` }} />
            <div className="absolute -bottom-1 -left-1 w-3 h-3 border-b-2 border-l-2" style={{ borderColor: `${tier.color}50` }} />
            <div className="absolute -bottom-1 -right-1 w-3 h-3 border-b-2 border-r-2" style={{ borderColor: `${tier.color}50` }} />
          </motion.div>
        </div>

        {/* Name */}
        <motion.h2
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, delay: 0.2 }}
          className="text-2xl sm:text-3xl text-center mb-1"
          style={{ fontFamily: titleFont, color: '#3a2810' }}
        >
          {entry.name}
        </motion.h2>

        {/* Tier + Level */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
          className="flex items-center gap-2"
        >
          <span
            className="text-xs uppercase tracking-wider px-2 py-0.5 rounded-sm"
            style={{
              fontFamily: statFont,
              color: tier.color,
              background: `${tier.color}10`,
              border: `1px solid ${tier.color}25`,
            }}
          >
            {tier.label}
          </span>
          <span className="text-xs" style={{ fontFamily: scriptFont, color: '#6a5030' }}>
            Уровень {entry.level}
          </span>
        </motion.div>

        {/* Kill status */}
        {entry.killed && (
          <motion.span
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.4 }}
            className="mt-2 text-xs flex items-center gap-1"
            style={{ fontFamily: scriptFont, color: '#4a8a3a' }}
          >
            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
            </svg>
            Изучено
          </motion.span>
        )}
      </div>

      {/* Divider */}
      <div className="flex items-center gap-2 mb-5">
        <div className="flex-1 h-px" style={{ background: 'linear-gradient(to right, transparent, rgba(139,105,20,0.25))' }} />
        <div className="w-1.5 h-1.5 rotate-45" style={{ border: '1px solid rgba(139,105,20,0.3)' }} />
        <div className="flex-1 h-px" style={{ background: 'linear-gradient(to right, rgba(139,105,20,0.25), transparent)' }} />
      </div>

      {/* ── Description ── */}
      {hasDescription ? (
        entry.description && (
          <Section title="Описание" delay={0.15}>
            <p className="text-sm sm:text-base leading-relaxed" style={{ fontFamily: scriptFont, color: inkColor }}>
              {entry.description}
            </p>
          </Section>
        )
      ) : (
        <Section title="Описание" delay={0.15}><LockedContent tier={entry.tier} /></Section>
      )}

      {/* ── Attributes ── */}
      {hasAttributes ? (
        entry.base_attributes && Object.keys(entry.base_attributes).length > 0 && (
          <Section title="Характеристики" delay={0.3}>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1.5 mb-3">
              {MAIN_STATS.map((key) => {
                const value = entry.base_attributes?.[key];
                if (value === undefined) return null;
                return (
                  <div key={key} className="flex items-center justify-between gap-1">
                    <span className="text-xs sm:text-sm" style={{ fontFamily: statFont, color: inkLight, fontStyle: 'italic' }}>
                      {STAT_LABELS[key] ?? key}
                    </span>
                    <span className="text-xs sm:text-sm font-semibold"
                      style={{ fontFamily: statFont, color: inkColor, fontVariantNumeric: 'tabular-nums' }}>
                      {value}
                    </span>
                  </div>
                );
              })}
            </div>
            {(() => {
              const resKeys = Object.keys(entry.base_attributes ?? {}).filter((k) => k.startsWith('res_'));
              if (resKeys.length === 0) return null;
              return (
                <>
                  <div className="flex items-center gap-2 my-2">
                    <div className="flex-1 h-px" style={{ background: `linear-gradient(to right, transparent, ${inkFaded}30)` }} />
                    <span className="text-[10px] uppercase tracking-[0.2em]" style={{ fontFamily: statFont, color: inkFaded }}>
                      Сопротивления
                    </span>
                    <div className="flex-1 h-px" style={{ background: `linear-gradient(to right, ${inkFaded}30, transparent)` }} />
                  </div>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                    {resKeys.map((key) => {
                      const value = entry.base_attributes?.[key];
                      if (value === undefined) return null;
                      return (
                        <div key={key} className="flex items-center justify-between gap-1">
                          <span className="text-[10px] sm:text-xs" style={{ fontFamily: statFont, color: inkFaded, fontStyle: 'italic' }}>
                            {STAT_LABELS[key] ?? key}
                          </span>
                          <span className="text-[10px] sm:text-xs font-medium"
                            style={{ fontFamily: statFont, color: inkLight, fontVariantNumeric: 'tabular-nums' }}>
                            {value}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </>
              );
            })()}
          </Section>
        )
      ) : (
        <Section title="Характеристики" delay={0.3}><LockedContent tier={entry.tier} /></Section>
      )}

      {/* ── Skills ── */}
      {hasSkills ? (
        entry.skills && entry.skills.length > 0 && (
          <Section title="Навыки" delay={0.45}>
            <div className="flex flex-wrap gap-2">
              {entry.skills.map((skill) => (
                <span key={skill.skill_rank_id} className="px-2.5 py-1 rounded-sm text-xs sm:text-sm"
                  style={{ fontFamily: scriptFont, color: '#4a2868', background: 'rgba(106,58,138,0.08)', border: '1px solid rgba(106,58,138,0.15)' }}>
                  {skill.skill_name ?? `Навык #${skill.skill_rank_id}`}
                </span>
              ))}
            </div>
          </Section>
        )
      ) : (
        <Section title="Навыки"><LockedContent tier={entry.tier} /></Section>
      )}

      {/* ── Loot ── */}
      {hasLoot ? (
        entry.loot_entries && entry.loot_entries.length > 0 && (
          <Section title="Добыча" delay={0.6}>
            <div className="flex flex-col gap-1.5">
              {entry.loot_entries.map((loot) => (
                <div key={loot.item_id} className="flex items-center justify-between rounded-sm px-3 py-1.5"
                  style={{ background: 'rgba(139,105,20,0.06)', border: '1px solid rgba(139,105,20,0.1)' }}>
                  <span className="text-xs sm:text-sm" style={{ fontFamily: scriptFont, color: inkColor }}>
                    {loot.item_name ?? `Предмет #${loot.item_id}`}
                  </span>
                  <div className="flex items-center gap-2 sm:gap-3 text-xs sm:text-sm">
                    <span style={{ fontFamily: statFont, color: '#8b6914', fontVariantNumeric: 'tabular-nums' }}>
                      {loot.drop_chance}%
                    </span>
                    <span style={{ fontFamily: statFont, color: inkFaded, fontVariantNumeric: 'tabular-nums' }}>
                      x{loot.min_quantity}{loot.max_quantity > loot.min_quantity && `-${loot.max_quantity}`}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </Section>
        )
      ) : (
        <Section title="Добыча" delay={0.6}><LockedContent tier={entry.tier} /></Section>
      )}

      {/* ── Locations ── */}
      {hasSpawns ? (
        entry.spawn_locations && entry.spawn_locations.length > 0 && (
          <Section title="Места обитания" delay={0.75}>
            <div className="flex flex-wrap gap-2">
              {entry.spawn_locations.map((spawn) => (
                <span key={spawn.location_id} className="px-2.5 py-1 rounded-sm text-xs sm:text-sm"
                  style={{ fontFamily: scriptFont, color: inkLight, background: 'rgba(139,105,20,0.06)', border: '1px solid rgba(139,105,20,0.12)' }}>
                  {spawn.location_name ?? `Локация #${spawn.location_id}`}
                </span>
              ))}
            </div>
          </Section>
        )
      ) : (
        <Section title="Места обитания" delay={0.75}><LockedContent tier={entry.tier} /></Section>
      )}
    </div>
  );
};

export default ScrollMobDetail;
