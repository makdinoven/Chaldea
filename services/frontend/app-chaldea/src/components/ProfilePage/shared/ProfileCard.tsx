// FEAT-166 — shared profile-tab primitive: the inner card surface used inside a
// PanelShell (skill/recipe/title/member/log rows). Deliberately flat (no blur,
// no second gold ring) so a gold panel full of cards stays "airy".
import { createElement, forwardRef } from 'react';
import type { HTMLAttributes, ReactNode } from 'react';
import { motion } from 'motion/react';

export type ProfileCardVariant = 'default' | 'accent' | 'danger';

export interface ProfileCardProps extends HTMLAttributes<HTMLElement> {
  /** Rendered element (default `div`) */
  as?: 'div' | 'button' | 'li';
  variant?: ProfileCardVariant;
  /** Hover affordance (gold border + faint gold wash) */
  interactive?: boolean;
  /** Selected / equipped state */
  active?: boolean;
  /** Unavailable / not earned state (dimmed) */
  locked?: boolean;
  /** Forwarded to `<button>` only (defaults to `button`) */
  type?: 'button' | 'submit' | 'reset';
  /** Forwarded to `<button>` only */
  disabled?: boolean;
  className?: string;
  children?: ReactNode;
}

// Exactly one border colour and one background is emitted per state: Tailwind v3
// does not guarantee which of two same-property utilities wins, so the default
// surface is only applied when no state/variant overrides it.
// Priority: active > variant (accent / danger) > default.
const BASE_CLASSES = 'relative rounded-card border transition-colors duration-200 ease-site';

const SURFACE_CLASSES: Record<ProfileCardVariant | 'active', string> = {
  default: 'border-white/10 bg-white/[0.03]',
  accent: 'border-gold/30 bg-gradient-to-b from-gold/[0.08] to-transparent',
  danger: 'border-site-red/30 bg-site-red/[0.05]',
  active: 'border-gold/50 bg-gold/[0.06]',
};

const INTERACTIVE_CLASSES = 'cursor-pointer';
// Hover wash only for non-active cards (it would dim the selected state).
const HOVER_CLASSES = 'hover:border-gold/40 hover:bg-gold/[0.04]';
const LOCKED_CLASSES = 'opacity-60';

const ProfileCard = forwardRef<HTMLElement, ProfileCardProps>(
  (
    {
      as = 'div',
      variant = 'default',
      interactive = false,
      active = false,
      locked = false,
      type,
      disabled,
      className = '',
      children,
      ...rest
    },
    ref,
  ) => {
    const classes = [
      BASE_CLASSES,
      SURFACE_CLASSES[active ? 'active' : variant],
      interactive ? INTERACTIVE_CLASSES : '',
      interactive && !active ? HOVER_CLASSES : '',
      locked ? LOCKED_CLASSES : '',
      as === 'button' ? 'block w-full text-left' : '',
      className,
    ]
      .filter(Boolean)
      .join(' ');

    const buttonProps = as === 'button' ? { type: type ?? 'button', disabled } : {};

    return createElement(as, { ...rest, ...buttonProps, ref, className: classes }, children);
  },
);

ProfileCard.displayName = 'ProfileCard';

/** Motion-enabled ProfileCard for staggered grids (`variants`, `initial`, `animate`...). */
export const MotionProfileCard = motion.create(ProfileCard);

export default ProfileCard;
