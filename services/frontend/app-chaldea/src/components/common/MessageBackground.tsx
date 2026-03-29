import { useAppSelector } from '../../redux/store';
import { selectBackgroundsCatalog } from '../../redux/slices/cosmeticsSlice';

interface MessageBackgroundProps {
  backgroundSlug: string | null;
  children: React.ReactNode;
  className?: string;
}

const MessageBackground = ({
  backgroundSlug,
  children,
  className = '',
}: MessageBackgroundProps) => {
  const backgrounds = useAppSelector(selectBackgroundsCatalog);
  const bg = backgroundSlug
    ? backgrounds.find((b) => b.slug === backgroundSlug)
    : null;

  if (!bg) {
    // Fallback: render children with default styling (no custom background)
    return <div className={className}>{children}</div>;
  }

  const bgCssClass = bg.css_class ?? '';

  const style: React.CSSProperties = {};
  if (bg.image_url) {
    style.backgroundImage = `url(${bg.image_url})`;
    style.backgroundSize = 'cover';
    style.backgroundPosition = 'center';
  }

  return (
    <div
      className={`${bgCssClass} ${className}`}
      style={Object.keys(style).length > 0 ? style : undefined}
    >
      {children}
    </div>
  );
};

export default MessageBackground;
