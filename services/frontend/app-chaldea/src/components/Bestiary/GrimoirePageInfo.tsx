import type { BestiaryEntry } from '../../api/bestiary';

const serifFont = "'Georgia', 'Palatino Linotype', 'Palatino', 'Times New Roman', serif";

interface GrimoirePageInfoProps {
  entry: BestiaryEntry;
}

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

const LockIcon = () => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    className="w-4 h-4 sm:w-5 sm:h-5 opacity-40"
    fill="none"
    viewBox="0 0 24 24"
    stroke="currentColor"
    strokeWidth={1.5}
  >
    <path
      strokeLinecap="round"
      strokeLinejoin="round"
      d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
    />
  </svg>
);

const LockedSection = ({ tier }: { tier: string }) => {
  const message =
    tier === 'normal'
      ? 'Убейте этого монстра, чтобы узнать его секреты'
      : 'Этот противник окутан тайной. Победите его, чтобы раскрыть информацию';

  return (
    <div className="flex items-center gap-2 text-amber-200/25 py-3">
      <LockIcon />
      <span
        className="text-sm italic tracking-wide"
        style={{ fontFamily: serifFont }}
      >
        ???
      </span>
      <span
        className="text-[10px] sm:text-xs italic ml-1 hidden sm:inline text-amber-200/20"
        style={{ fontFamily: serifFont }}
      >
        {message}
      </span>
    </div>
  );
};

const SectionTitle = ({ children }: { children: React.ReactNode }) => (
  <h3
    className="text-sm sm:text-base font-medium uppercase tracking-widest mb-2 sm:mb-3"
    style={{
      fontFamily: serifFont,
      color: '#c9a84c',
      textShadow: '0 0 6px rgba(201,168,76,0.15)',
    }}
  >
    {/* Decorative dash before title */}
    <span className="text-gold/30 mr-2">&#x2014;</span>
    {children}
    <span className="text-gold/30 ml-2">&#x2014;</span>
  </h3>
);

const GrimoirePageInfo = ({ entry }: GrimoirePageInfoProps) => {
  const hasDescription = entry.description !== null;
  const hasAttributes = entry.base_attributes !== null;
  const hasSkills = entry.skills !== null;
  const hasLoot = entry.loot_entries !== null;
  const hasSpawns = entry.spawn_locations !== null;

  return (
    <div
      className="flex flex-col gap-4 sm:gap-5 p-4 sm:p-6 h-full overflow-y-auto gold-scrollbar"
      style={{ fontFamily: serifFont }}
    >
      {/* Description */}
      {hasDescription ? (
        entry.description && (
          <div>
            <SectionTitle>Описание</SectionTitle>
            <p className="text-amber-100/70 text-sm sm:text-base leading-relaxed italic">
              {entry.description}
            </p>
          </div>
        )
      ) : (
        <div>
          <SectionTitle>Описание</SectionTitle>
          <LockedSection tier={entry.tier} />
        </div>
      )}

      {/* Base Attributes */}
      {hasAttributes ? (
        entry.base_attributes && Object.keys(entry.base_attributes).length > 0 && (
          <div>
            <SectionTitle>Характеристики</SectionTitle>
            {/* Main stats */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-1.5 mb-3">
              {MAIN_STATS.map((key) => {
                const value = entry.base_attributes?.[key];
                if (value === undefined) return null;
                return (
                  <div key={key} className="flex items-center justify-between gap-1">
                    <span className="text-amber-200/50 text-xs sm:text-sm">
                      {STAT_LABELS[key] ?? key}
                    </span>
                    <span
                      className="text-amber-100 text-xs sm:text-sm font-medium"
                      style={{ fontVariantNumeric: 'tabular-nums' }}
                    >
                      {value}
                    </span>
                  </div>
                );
              })}
            </div>
            {/* Resistances */}
            {(() => {
              const resistanceKeys = Object.keys(entry.base_attributes ?? {}).filter(
                (k) => k.startsWith('res_'),
              );
              if (resistanceKeys.length === 0) return null;
              return (
                <>
                  <div className="flex items-center gap-2 my-2">
                    <div className="flex-1 h-px bg-gradient-to-r from-transparent to-gold/15" />
                    <span className="text-gold/40 text-[10px] uppercase tracking-[0.2em]">
                      Сопротивления
                    </span>
                    <div className="flex-1 h-px bg-gradient-to-r from-gold/15 to-transparent" />
                  </div>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1">
                    {resistanceKeys.map((key) => {
                      const value = entry.base_attributes?.[key];
                      if (value === undefined || value === 0) return null;
                      return (
                        <div
                          key={key}
                          className="flex items-center justify-between gap-1"
                        >
                          <span className="text-amber-200/40 text-[10px] sm:text-xs">
                            {STAT_LABELS[key] ?? key}
                          </span>
                          <span
                            className="text-amber-100/70 text-[10px] sm:text-xs font-medium"
                            style={{ fontVariantNumeric: 'tabular-nums' }}
                          >
                            {value}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </>
              );
            })()}
          </div>
        )
      ) : (
        <div>
          <SectionTitle>Характеристики</SectionTitle>
          <LockedSection tier={entry.tier} />
        </div>
      )}

      {/* Skills */}
      {hasSkills ? (
        entry.skills && entry.skills.length > 0 && (
          <div>
            <SectionTitle>Навыки</SectionTitle>
            <div className="flex flex-wrap gap-2">
              {entry.skills.map((skill) => (
                <span
                  key={skill.skill_rank_id}
                  className="px-2.5 py-1 rounded-sm bg-purple-900/30 text-purple-200/80 text-xs sm:text-sm
                             border border-purple-400/15"
                >
                  {skill.skill_name ?? `Навык #${skill.skill_rank_id}`}
                </span>
              ))}
            </div>
          </div>
        )
      ) : (
        <div>
          <SectionTitle>Навыки</SectionTitle>
          <LockedSection tier={entry.tier} />
        </div>
      )}

      {/* Loot Table */}
      {hasLoot ? (
        entry.loot_entries && entry.loot_entries.length > 0 && (
          <div>
            <SectionTitle>Добыча</SectionTitle>
            <div className="flex flex-col gap-1.5">
              {entry.loot_entries.map((loot) => (
                <div
                  key={loot.item_id}
                  className="flex items-center justify-between bg-amber-900/10 border border-gold/5
                             rounded-sm px-3 py-1.5"
                >
                  <span className="text-amber-100/70 text-xs sm:text-sm">
                    {loot.item_name ?? `Предмет #${loot.item_id}`}
                  </span>
                  <div className="flex items-center gap-2 sm:gap-3 text-xs sm:text-sm">
                    <span className="text-gold/70" style={{ fontVariantNumeric: 'tabular-nums' }}>
                      {loot.drop_chance}%
                    </span>
                    <span className="text-amber-200/40" style={{ fontVariantNumeric: 'tabular-nums' }}>
                      x{loot.min_quantity}
                      {loot.max_quantity > loot.min_quantity &&
                        `-${loot.max_quantity}`}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )
      ) : (
        <div>
          <SectionTitle>Добыча</SectionTitle>
          <LockedSection tier={entry.tier} />
        </div>
      )}

      {/* Spawn Locations */}
      {hasSpawns ? (
        entry.spawn_locations && entry.spawn_locations.length > 0 && (
          <div>
            <SectionTitle>Места обитания</SectionTitle>
            <div className="flex flex-wrap gap-2">
              {entry.spawn_locations.map((spawn) => (
                <span
                  key={spawn.location_id}
                  className="px-2.5 py-1 rounded-sm bg-amber-900/15 border border-gold/10
                             text-amber-100/60 text-xs sm:text-sm"
                >
                  {spawn.location_name ?? `Локация #${spawn.location_id}`}
                </span>
              ))}
            </div>
          </div>
        )
      ) : (
        <div>
          <SectionTitle>Места обитания</SectionTitle>
          <LockedSection tier={entry.tier} />
        </div>
      )}
    </div>
  );
};

export default GrimoirePageInfo;
