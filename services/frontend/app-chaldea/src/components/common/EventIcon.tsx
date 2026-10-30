import {
  AlertTriangle,
  Beef,
  Biohazard,
  Bug,
  CloudRain,
  Coins,
  Flame,
  Fish,
  Gem,
  HeartPulse,
  PartyPopper,
  Pickaxe,
  ShieldAlert,
  Skull,
  Snowflake,
  Sparkles,
  Store,
  Sun,
  Swords,
  Waves,
  Wheat,
  Zap,
  type LucideIcon,
} from 'lucide-react';

/**
 * FEAT-187 — icons of region events. Keys mirror the backend whitelist `schemas.EVENT_ICONS`
 * (character-service); an unknown name falls back to `alert`.
 */
export const EVENT_ICON_COMPONENTS: Record<string, LucideIcon> = {
  sun: Sun,
  'cloud-rain': CloudRain,
  waves: Waves,
  skull: Skull,
  biohazard: Biohazard,
  zap: Zap,
  sparkles: Sparkles,
  pickaxe: Pickaxe,
  gem: Gem,
  beef: Beef,
  swords: Swords,
  flame: Flame,
  wheat: Wheat,
  fish: Fish,
  store: Store,
  'party-popper': PartyPopper,
  snowflake: Snowflake,
  bug: Bug,
  coins: Coins,
  'heart-pulse': HeartPulse,
  'shield-alert': ShieldAlert,
  alert: AlertTriangle,
};

/** Icon names in the order the admin picker shows them. */
export const EVENT_ICON_NAMES: string[] = Object.keys(EVENT_ICON_COMPONENTS);

const FALLBACK_ICON = 'alert';

interface EventIconProps {
  name: string | null | undefined;
  size?: number;
  className?: string;
  /** Accessible name; without it the icon is decorative. */
  title?: string;
}

const EventIcon = ({ name, size = 16, className = '', title }: EventIconProps) => {
  const Icon = (name && EVENT_ICON_COMPONENTS[name]) || EVENT_ICON_COMPONENTS[FALLBACK_ICON];
  return (
    <Icon
      size={size}
      className={className}
      aria-hidden={title ? undefined : true}
      aria-label={title}
      role={title ? 'img' : undefined}
    />
  );
};

export default EventIcon;
