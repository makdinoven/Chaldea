// Cosmetics types — based on API contracts in FEAT-103 Section 3.2

export type CosmeticFrameType = 'css' | 'image' | 'combo';
export type CosmeticBackgroundType = 'css' | 'image';
export type CosmeticRarity = 'common' | 'rare' | 'epic' | 'legendary';
export type CosmeticSource = 'default' | 'battlepass' | 'admin';

export interface CosmeticFrame {
  id: number;
  name: string;
  slug: string;
  type: CosmeticFrameType;
  css_class: string | null;
  image_url: string | null;
  rarity: CosmeticRarity;
  is_default: boolean;
  is_seasonal: boolean;
}

export interface CosmeticBackground {
  id: number;
  name: string;
  slug: string;
  type: CosmeticBackgroundType;
  css_class: string | null;
  image_url: string | null;
  rarity: CosmeticRarity;
  is_default: boolean;
}

export interface UserCosmeticItem extends CosmeticFrame {
  source: CosmeticSource;
  unlocked_at: string | null;
}

export interface UserCosmeticBackgroundItem extends CosmeticBackground {
  source: CosmeticSource;
  unlocked_at: string | null;
}

export interface CosmeticsCatalogResponse<T> {
  items: T[];
}

export interface UserFramesResponse {
  items: UserCosmeticItem[];
  active_slug: string | null;
}

export interface UserBackgroundsResponse {
  items: UserCosmeticBackgroundItem[];
  active_slug: string | null;
}

export interface EquipFrameResponse {
  active_frame: string | null;
}

export interface EquipBackgroundResponse {
  active_background: string | null;
}

// Admin types

export interface CosmeticFrameCreatePayload {
  name: string;
  slug: string;
  type: CosmeticFrameType;
  css_class?: string | null;
  image_url?: string | null;
  rarity: CosmeticRarity;
  is_default?: boolean;
  is_seasonal?: boolean;
}

export interface CosmeticFrameUpdatePayload {
  name?: string;
  slug?: string;
  type?: CosmeticFrameType;
  css_class?: string | null;
  image_url?: string | null;
  rarity?: CosmeticRarity;
  is_default?: boolean;
  is_seasonal?: boolean;
}

export interface CosmeticBackgroundCreatePayload {
  name: string;
  slug: string;
  type: CosmeticBackgroundType;
  css_class?: string | null;
  image_url?: string | null;
  rarity: CosmeticRarity;
  is_default?: boolean;
}

export interface CosmeticBackgroundUpdatePayload {
  name?: string;
  slug?: string;
  type?: CosmeticBackgroundType;
  css_class?: string | null;
  image_url?: string | null;
  rarity?: CosmeticRarity;
  is_default?: boolean;
}

export interface CosmeticGrantPayload {
  user_id: number;
  cosmetic_type: 'frame' | 'background';
  cosmetic_slug: string;
}

export interface CosmeticGrantResponse {
  granted: boolean;
}

export interface CosmeticDeleteResponse {
  deleted: boolean;
}

export interface CosmeticImageUploadResponse {
  url: string;
}
