import { useAppSelector } from '../../redux/store';
import { selectFramesCatalog } from '../../redux/slices/cosmeticsSlice';

interface AvatarWithFrameProps {
  avatarUrl: string | null;
  frameSlug: string | null;
  size?: 'sm' | 'md' | 'lg';
  /** Override size with exact pixel value (takes priority over `size` preset) */
  pixelSize?: number;
  username?: string;
  className?: string;
  rounded?: 'full' | 'rounded';
}

const SIZE_MAP = {
  sm: 40,
  md: 60,
  lg: 80,
} as const;

const BORDER_RADIUS_MAP = {
  full: '9999px',
  rounded: '10px',
} as const;

const AvatarWithFrame = ({
  avatarUrl,
  frameSlug,
  size = 'md',
  pixelSize,
  username,
  className = '',
  rounded = 'full',
}: AvatarWithFrameProps) => {
  const frames = useAppSelector(selectFramesCatalog);
  const frame = frameSlug ? frames.find((f) => f.slug === frameSlug) : null;

  const px = pixelSize ?? SIZE_MAP[size];
  const borderRadius = BORDER_RADIUS_MAP[rounded];

  // Determine CSS class from frame
  // If catalog loaded: use css_class from DB. If catalog empty: fallback to "frame-{slug}"
  let frameCssClass = '';
  if (frame && (frame.type === 'css' || frame.type === 'combo')) {
    frameCssClass = frame.css_class ?? '';
  } else if (frameSlug && !frame && frames.length === 0) {
    // Catalog not loaded yet — use convention: "frame-{slug}"
    frameCssClass = `frame-${frameSlug}`;
  }

  // Determine image overlay from frame
  const frameImageUrl =
    frame && (frame.type === 'image' || frame.type === 'combo')
      ? frame.image_url
      : null;

  return (
    <div
      className={`relative flex-shrink-0 ${frameCssClass} ${className}`}
      style={{ width: px, height: px, borderRadius }}
    >
      {/* Avatar image or fallback initial */}
      <div
        className="w-full h-full overflow-hidden bg-white/10"
        style={{ borderRadius }}
      >
        {avatarUrl ? (
          <img
            src={avatarUrl}
            alt={username ?? ''}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-white/40 font-medium"
            style={{ fontSize: px * 0.35 }}
          >
            {username ? username.charAt(0).toUpperCase() : '?'}
          </div>
        )}
      </div>

      {/* Image-type frame overlay */}
      {frameImageUrl && (
        <img
          src={frameImageUrl}
          alt=""
          className="absolute inset-0 w-full h-full pointer-events-none"
          style={{ borderRadius }}
        />
      )}
    </div>
  );
};

export default AvatarWithFrame;
