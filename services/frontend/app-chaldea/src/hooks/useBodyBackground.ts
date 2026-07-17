import { useEffect } from 'react';

/**
 * Soft dark overlay composed over page-specific background images.
 * Mirrors the site-wide `body` rule in index.css (FEAT-151: intentionally
 * softer than the design mock's heavy darkening — user asked for a
 * non-aggressive overlay). Kept in sync manually with index.css.
 */
const SOFT_OVERLAY =
  'linear-gradient(180deg, rgba(5, 6, 10, 0.35), rgba(5, 6, 10, 0.55))';

/**
 * Swaps the global body background image for the given URL while the
 * consuming page is mounted, restoring the previous value on unmount.
 *
 * Because the inline style replaces the CSS default (which already carries
 * the soft overlay), the overlay is re-composed here so pages with a custom
 * background keep the same gentle darkening as the rest of the site
 * (FEAT-152 B14).
 */
export function useBodyBackground(imageUrl?: string | null): void {
  useEffect(() => {
    if (!imageUrl) return;
    const originalBackground = document.body.style.backgroundImage;
    document.body.style.backgroundImage = `${SOFT_OVERLAY}, url(${imageUrl})`;
    return () => {
      document.body.style.backgroundImage = originalBackground;
    };
  }, [imageUrl]);
}
