import statsUserImg from '../../../assets/stats_user_img.png';

export const formatValue = (value: number) => value.toLocaleString('ru-RU');

interface LeaderAvatarProps {
  src: string | null | undefined;
  alt: string;
  className?: string;
}

/** Character avatar with a placeholder fallback (broken URL or no avatar). */
export const LeaderAvatar = ({ src, alt, className }: LeaderAvatarProps) => (
  <img
    src={src || statsUserImg}
    onError={(e) => {
      (e.currentTarget as HTMLImageElement).src = statsUserImg;
    }}
    alt={alt}
    className={className}
  />
);
