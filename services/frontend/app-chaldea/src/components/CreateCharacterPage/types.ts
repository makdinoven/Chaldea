export interface StatPreset {
  strength: number;
  agility: number;
  intelligence: number;
  endurance: number;
  health: number;
  energy: number;
  mana: number;
  stamina: number;
  charisma: number;
  luck: number;
}

export interface SubraceData {
  id_subrace: number;
  name: string;
  description: string | null;
  stat_preset: StatPreset | null;
  image: string | null;
}

export interface RaceData {
  id_race: number;
  name: string;
  description: string | null;
  image: string | null;
  subraces: SubraceData[];
}

export interface Biography {
  biography: string;
  personality: string;
  appearance: string;
  name: string;
  age: string;
  height: string;
  weight: string;
  background: string;
  sex: string;
}

export interface ClassInventoryItem {
  name: string;
  link: string;
  img: string;
}

export interface ClassSkillItem {
  name: string;
  link: string;
  img: string;
}

export interface ClassData {
  id: number;
  name: string;
  img: string;
  features: string;
  inventory: ClassInventoryItem[];
  skills: ClassSkillItem[];
}

export interface PageData {
  pageId: number;
  pageTitle: string;
  races?: RaceData[];
  classes?: ClassData[];
}
