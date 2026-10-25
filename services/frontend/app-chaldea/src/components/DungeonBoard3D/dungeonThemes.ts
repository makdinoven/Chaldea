/*
  How a dungeon's miniature looks (FEAT-176): walls, floor and the light in it.
  The textures are painted on canvases (themePaint.ts); this is the list and the
  material and light settings that go with each look. Kept free of three.js so
  the admin form can read it without pulling the 3D bundle in.
*/

export const DUNGEON_THEMES = ['stone', 'temple', 'cave', 'ice', 'volcano', 'catacombs', 'mine', 'sewer'] as const;
export type DungeonTheme = (typeof DUNGEON_THEMES)[number];

export const THEME_INFO: Record<DungeonTheme, { name: string; about: string }> = {
  stone: { name: 'Каменная кладка', about: 'Серые плиты и грубые блоки' },
  temple: { name: 'Древний храм', about: 'Песчаник, резные плиты, тёплый свет' },
  cave: { name: 'Пещера', about: 'Природный камень, земля и щебень' },
  ice: { name: 'Ледяной склеп', about: 'Лёд и иней, холодный свет' },
  volcano: { name: 'Вулканические недра', about: 'Базальт и тлеющая лава' },
  catacombs: { name: 'Катакомбы', about: 'Тёмный кирпич, мох и черепа' },
  mine: { name: 'Заброшенная шахта', about: 'Деревянная крепь, утоптанная земля' },
  sewer: { name: 'Канализация', about: 'Мокрый кирпич, слизь и лужи' },
};

export interface ThemeLook {
  floorRough: number;
  wallRough: number;
  floorMetal: number;
  wallMetal: number;
  /** Glow painted into the floor and walls (lava): its colour and strength. */
  glow?: string;
  glowIntensity?: number;
  /** The halo round the wall torches. */
  torch: string;
  /** The party's lantern. */
  lantern: string;
  /** The rock the dungeon is cut into. */
  rock: string;
}

export const THEME_LOOK: Record<DungeonTheme, ThemeLook> = {
  stone: { floorRough: 0.9, wallRough: 0.92, floorMetal: 0, wallMetal: 0, torch: '#ffb35c', lantern: '#ffcf8a', rock: '#6a645c' },
  temple: { floorRough: 0.8, wallRough: 0.85, floorMetal: 0, wallMetal: 0, torch: '#ffd27a', lantern: '#ffd9a0', rock: '#8c7656' },
  cave: { floorRough: 0.97, wallRough: 0.97, floorMetal: 0, wallMetal: 0, torch: '#ffb35c', lantern: '#ffcf8a', rock: '#5e564c' },
  ice: { floorRough: 0.3, wallRough: 0.4, floorMetal: 0.1, wallMetal: 0.05, torch: '#9fd8ff', lantern: '#dcefff', rock: '#9aaebd' },
  volcano: {
    floorRough: 0.85,
    wallRough: 0.9,
    floorMetal: 0,
    wallMetal: 0,
    glow: '#ff5a1a',
    glowIntensity: 1.6,
    torch: '#ff7a2a',
    lantern: '#ffb88a',
    rock: '#2e2828',
  },
  catacombs: { floorRough: 0.92, wallRough: 0.95, floorMetal: 0, wallMetal: 0, torch: '#a8ff7a', lantern: '#e4f5c8', rock: '#48443c' },
  mine: { floorRough: 0.97, wallRough: 0.9, floorMetal: 0, wallMetal: 0, torch: '#ffb35c', lantern: '#ffcf8a', rock: '#6a5442' },
  sewer: { floorRough: 0.45, wallRough: 0.7, floorMetal: 0.05, wallMetal: 0, torch: '#d6e08a', lantern: '#f0ecc0', rock: '#4c5048' },
};

export const isTheme = (v: unknown): v is DungeonTheme => DUNGEON_THEMES.includes(v as DungeonTheme);

/** The look of one floor: its own if it has one, the dungeon's otherwise. */
export const floorTheme = (
  theme: string | null | undefined,
  floorThemes: Record<string, string> | null | undefined,
  floor: number,
): DungeonTheme => {
  const own = floorThemes?.[String(floor)];
  if (isTheme(own)) return own;
  return isTheme(theme) ? theme : 'stone';
};
