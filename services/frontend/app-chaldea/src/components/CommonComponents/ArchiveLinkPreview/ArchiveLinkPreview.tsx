import { useEffect, useRef, useState, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { fetchArticlePreview, ArchiveArticlePreview } from '../../../api/archive';

interface TooltipState {
  visible: boolean;
  x: number;
  y: number;
  above: boolean;
  slug: string;
}

interface PreviewCacheEntry {
  data: ArchiveArticlePreview | null;
  notFound: boolean;
  loading: boolean;
}

const HOVER_DELAY_MS = 200;
const HIDE_DELAY_MS = 150;
const TOOLTIP_MAX_WIDTH = 300;
const VIEWPORT_PADDING = 12;

const previewCache = new Map<string, PreviewCacheEntry>();

const ArchiveLinkPreviewTooltip = ({
  state,
  onMouseEnter,
  onMouseLeave,
}: {
  state: TooltipState;
  onMouseEnter: () => void;
  onMouseLeave: () => void;
}) => {
  const entry = previewCache.get(state.slug);
  const tooltipRef = useRef<HTMLDivElement>(null);

  // Adjust horizontal position to stay within viewport
  const adjustedX = (() => {
    const halfWidth = TOOLTIP_MAX_WIDTH / 2;
    const vw = window.innerWidth;
    let x = state.x;
    if (x - halfWidth < VIEWPORT_PADDING) x = halfWidth + VIEWPORT_PADDING;
    if (x + halfWidth > vw - VIEWPORT_PADDING) x = vw - halfWidth - VIEWPORT_PADDING;
    return x;
  })();

  return createPortal(
    <div
      ref={tooltipRef}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      className="fixed z-[9999] pointer-events-auto"
      style={{
        left: `${adjustedX}px`,
        top: `${state.y}px`,
        transform: `translate(-50%, ${state.above ? '-100%' : '0'})`,
        maxWidth: `${TOOLTIP_MAX_WIDTH}px`,
      }}
    >
      <div className="bg-[#f5e6c8] border border-gold-dark/50 rounded-card shadow-card p-3 text-sm">
        {entry?.loading && (
          <div className="flex items-center gap-2 text-black/60">
            <div className="w-4 h-4 border-2 border-gold-dark/30 border-t-gold-dark rounded-full animate-spin" />
            <span>Загрузка...</span>
          </div>
        )}

        {entry?.notFound && (
          <p className="text-black/50 italic text-xs">Статья не найдена</p>
        )}

        {entry?.data && !entry.loading && (
          <div className="flex gap-2.5">
            {entry.data.cover_image_url && (
              <img
                src={entry.data.cover_image_url}
                alt=""
                className="w-[60px] h-[60px] rounded object-cover shrink-0"
              />
            )}
            <div className="min-w-0 flex-1">
              <h4
                className="font-semibold text-sm leading-tight mb-1 text-black/90"
                style={{ fontFamily: "'MedievalSharp', cursive" }}
              >
                {entry.data.title}
              </h4>
              {entry.data.summary && (
                <p className="text-xs text-black/70 line-clamp-3 leading-relaxed">
                  {entry.data.summary}
                </p>
              )}
            </div>
          </div>
        )}
      </div>
    </div>,
    document.body,
  );
};

interface ArchiveLinkPreviewProps {
  children: React.ReactNode;
}

const ArchiveLinkPreview = ({ children }: ArchiveLinkPreviewProps) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);
  const hoverTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const hideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isTooltipHoveredRef = useRef(false);
  const isTouchDeviceRef = useRef(false);

  const clearTimers = useCallback(() => {
    if (hoverTimerRef.current) {
      clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = null;
    }
    if (hideTimerRef.current) {
      clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
  }, []);

  const hideTooltip = useCallback(() => {
    hideTimerRef.current = setTimeout(() => {
      if (!isTooltipHoveredRef.current) {
        setTooltip(null);
      }
    }, HIDE_DELAY_MS);
  }, []);

  const showTooltipForLink = useCallback(
    async (link: HTMLAnchorElement, slug: string) => {
      const rect = link.getBoundingClientRect();
      const spaceBelow = window.innerHeight - rect.bottom;
      const above = spaceBelow < 160;

      const x = rect.left + rect.width / 2;
      const y = above ? rect.top - 8 : rect.bottom + 8;

      setTooltip({ visible: true, x, y, above, slug });

      // Fetch if not cached
      if (!previewCache.has(slug) || previewCache.get(slug)!.loading) {
        previewCache.set(slug, { data: null, notFound: false, loading: true });
        // Force re-render with loading state
        setTooltip((prev) => (prev ? { ...prev } : null));

        try {
          const data = await fetchArticlePreview(slug);
          previewCache.set(slug, { data, notFound: false, loading: false });
        } catch {
          previewCache.set(slug, { data: null, notFound: true, loading: false });
        }
        // Force re-render with result
        setTooltip((prev) => (prev ? { ...prev } : null));
      }
    },
    [],
  );

  const handleTooltipMouseEnter = useCallback(() => {
    isTooltipHoveredRef.current = true;
    if (hideTimerRef.current) {
      clearTimeout(hideTimerRef.current);
      hideTimerRef.current = null;
    }
  }, []);

  const handleTooltipMouseLeave = useCallback(() => {
    isTooltipHoveredRef.current = false;
    hideTooltip();
  }, [hideTooltip]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const handleMouseEnter = (e: Event) => {
      if (isTouchDeviceRef.current) return;
      const link = (e.target as HTMLElement).closest('a[data-archive-slug]') as HTMLAnchorElement | null;
      if (!link) return;

      const slug = link.getAttribute('data-archive-slug');
      if (!slug) return;

      clearTimers();
      hoverTimerRef.current = setTimeout(() => {
        showTooltipForLink(link, slug);
      }, HOVER_DELAY_MS);
    };

    const handleMouseLeave = (e: Event) => {
      if (isTouchDeviceRef.current) return;
      const link = (e.target as HTMLElement).closest('a[data-archive-slug]');
      if (!link) return;

      if (hoverTimerRef.current) {
        clearTimeout(hoverTimerRef.current);
        hoverTimerRef.current = null;
      }
      hideTooltip();
    };

    const handleClick = (e: Event) => {
      const link = (e.target as HTMLElement).closest('a[data-archive-slug]') as HTMLAnchorElement | null;
      if (!link) return;

      const slug = link.getAttribute('data-archive-slug');
      if (!slug) return;

      e.preventDefault();
      e.stopPropagation();

      // On touch device, first tap shows tooltip, second tap navigates
      if (isTouchDeviceRef.current) {
        if (tooltip?.slug === slug && tooltip.visible) {
          // Second tap — navigate
          setTooltip(null);
          navigate(`/archive/${slug}`);
        } else {
          // First tap — show tooltip
          showTooltipForLink(link, slug);
        }
        return;
      }

      // Desktop click — navigate
      setTooltip(null);
      navigate(`/archive/${slug}`);
    };

    const handleTouchStart = () => {
      isTouchDeviceRef.current = true;
    };

    // Close tooltip on outside tap (mobile)
    const handleDocumentTouch = (e: Event) => {
      if (!tooltip) return;
      const target = e.target as HTMLElement;
      if (target.closest('a[data-archive-slug]')) return;
      if (target.closest('[data-archive-tooltip]')) return;
      setTooltip(null);
    };

    container.addEventListener('touchstart', handleTouchStart, { passive: true });
    container.addEventListener('mouseenter', handleMouseEnter, true);
    container.addEventListener('mouseleave', handleMouseLeave, true);
    container.addEventListener('click', handleClick, true);
    document.addEventListener('touchstart', handleDocumentTouch, { passive: true });

    return () => {
      container.removeEventListener('touchstart', handleTouchStart);
      container.removeEventListener('mouseenter', handleMouseEnter, true);
      container.removeEventListener('mouseleave', handleMouseLeave, true);
      container.removeEventListener('click', handleClick, true);
      document.removeEventListener('touchstart', handleDocumentTouch);
      clearTimers();
    };
  }, [clearTimers, hideTooltip, showTooltipForLink, tooltip, navigate]);

  // Style archive links within the container
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const styleLinks = () => {
      const links = container.querySelectorAll<HTMLAnchorElement>('a[data-archive-slug]');
      links.forEach((link) => {
        link.style.textDecorationStyle = 'dashed';
        link.style.textDecorationColor = '#8b1a1a';
        link.style.color = '#8b1a1a';
        link.style.fontWeight = '700';
        link.style.cursor = 'pointer';
      });
    };

    styleLinks();

    // Observe DOM mutations in case content changes dynamically
    const observer = new MutationObserver(styleLinks);
    observer.observe(container, { childList: true, subtree: true });

    return () => observer.disconnect();
  }, []);

  return (
    <div ref={containerRef} data-archive-tooltip>
      {children}
      {tooltip?.visible && (
        <ArchiveLinkPreviewTooltip
          state={tooltip}
          onMouseEnter={handleTooltipMouseEnter}
          onMouseLeave={handleTooltipMouseLeave}
        />
      )}
    </div>
  );
};

export default ArchiveLinkPreview;
