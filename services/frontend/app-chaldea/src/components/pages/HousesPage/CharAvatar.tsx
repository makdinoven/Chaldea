interface CharAvatarProps {
  src: string | null | undefined;
  /** Tailwind size classes, e.g. `w-9 h-9`. */
  size?: string;
}

/** A character's round avatar (blank circle without a picture). */
const CharAvatar = ({ src, size = 'w-9 h-9' }: CharAvatarProps) => (
  <span className={`${size} rounded-full overflow-hidden bg-black/40 border border-gold-dark/30 shrink-0 block`}>
    {src && <img src={src} alt="" className="w-full h-full object-cover" />}
  </span>
);

export default CharAvatar;
