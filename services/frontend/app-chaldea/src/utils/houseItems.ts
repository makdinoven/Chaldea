/*
  FEAT-180 stage 6b — item flags that belong to houses: elite trophies hang in
  a trophy hall, a home teleport scroll carries its reader to a return circle.
*/

export interface HouseItemFields {
  item_type?: string;
  is_elite_trophy?: boolean;
  is_home_teleport?: boolean;
}

export const ELITE_TROPHY_SUMMARY = 'Элитный трофей: +1 % к опыту за бои в трофейном зале';
export const HOME_TELEPORT_SUMMARY = 'Свиток возвращения: переносит в ваш дом с кругом возвращения';

export const isEliteTrophy = (item: HouseItemFields): boolean =>
  item.item_type === 'resource' && Boolean(item.is_elite_trophy);

export const isHomeTeleportScroll = (item: HouseItemFields): boolean =>
  item.item_type === 'scroll' && Boolean(item.is_home_teleport);

/** One line for the item tooltip / detail; null for ordinary items. */
export const houseItemSummary = (item: HouseItemFields): string | null => {
  if (isEliteTrophy(item)) return ELITE_TROPHY_SUMMARY;
  if (isHomeTeleportScroll(item)) return HOME_TELEPORT_SUMMARY;
  return null;
};
