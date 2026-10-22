import { useEffect } from 'react';

interface LocationArtViewProps {
  onClose: () => void;
}

/**
 * Stands in for the location page while its interface is put away: the page
 * background — the location art, undimmed meanwhile (see LocationPage) — shows
 * under the site header with nothing over it. It takes a full screen's height
 * so the footer stays out of view. A tap anywhere, the button or Esc brings the
 * interface back.
 */
const LocationArtView = ({ onClose }: LocationArtViewProps) => {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  return (
    <div className="min-h-[100dvh] cursor-pointer animate-fade-in" onClick={onClose}>
      <button
        type="button"
        onClick={onClose}
        className="fixed bottom-5 left-1/2 -translate-x-1/2 z-10 flex items-center gap-2 whitespace-nowrap px-4 py-2 rounded-card bg-black/40 backdrop-blur-sm border border-white/10 text-white/70 hover:text-white hover:border-gold-dark/60 text-sm transition-all duration-200 ease-site"
      >
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="w-4 h-4 shrink-0"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
        Показать интерфейс
      </button>
    </div>
  );
};

export default LocationArtView;
