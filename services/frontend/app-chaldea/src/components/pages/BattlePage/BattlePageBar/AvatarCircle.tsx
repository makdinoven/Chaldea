import type { ReactNode } from "react";

// Round avatar used by the turn queue and history circles.
interface AvatarCircleProps {
  avatar?: string | null;
  name?: string;
  size?: number;
  badge?: ReactNode;
  active?: boolean;
  side?: "ally" | "enemy";
  dim?: boolean;
  onClick?: () => void;
  title?: string;
}

const AvatarCircle = ({
  avatar,
  name,
  size = 40,
  badge,
  active,
  side,
  dim,
  onClick,
  title,
}: AvatarCircleProps) => {
  const ring = active
    ? "ring-2 ring-gold shadow-[0_0_10px_rgba(240,217,92,0.55)]"
    : side === "enemy"
      ? "ring-1 ring-site-red/50"
      : "ring-1 ring-white/25";
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      style={{ width: size, height: size }}
      className={`relative shrink-0 transition-transform duration-200 ease-site ${
        onClick ? "cursor-pointer hover:scale-105" : "cursor-default"
      } ${dim ? "opacity-45" : ""} ${active ? "scale-105" : ""}`}
    >
      <span
        className={`flex w-full h-full items-center justify-center rounded-full bg-center bg-cover bg-site-bg overflow-hidden ${ring}`}
        style={avatar ? { backgroundImage: `url("${avatar}")` } : undefined}
      >
        {!avatar && (
          <span className="text-xs font-medium text-white/70">
            {name?.trim()?.[0]?.toUpperCase() ?? "?"}
          </span>
        )}
      </span>
      {badge != null && (
        <span className="absolute -bottom-1 -right-1 min-w-[16px] h-4 px-1 flex items-center justify-center rounded-full bg-site-bg text-[10px] font-medium leading-none text-white ring-1 ring-white/30">
          {badge}
        </span>
      )}
    </button>
  );
};

export default AvatarCircle;
