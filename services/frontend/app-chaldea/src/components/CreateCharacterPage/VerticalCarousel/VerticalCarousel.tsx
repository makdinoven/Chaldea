import { useRef, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import type { VerticalCarouselProps } from '../types';

const VerticalCarousel = ({ items, selectedId, onSelect }: VerticalCarouselProps) => {
  const listRef = useRef<HTMLDivElement>(null);

  const selectedIndex = items.findIndex((item) => item.id === selectedId);

  const scrollToSelected = useCallback(() => {
    if (!listRef.current) return;
    const container = listRef.current;
    const selectedEl = container.children[selectedIndex] as HTMLElement | undefined;
    if (!selectedEl) return;

    const containerHeight = container.clientHeight;
    const elTop = selectedEl.offsetTop;
    const elHeight = selectedEl.offsetHeight;
    const scrollTarget = elTop - containerHeight / 2 + elHeight / 2;

    container.scrollTo({ top: scrollTarget, behavior: 'smooth' });
  }, [selectedIndex]);

  useEffect(() => {
    scrollToSelected();
  }, [scrollToSelected]);

  const handleNavigate = (direction: 'up' | 'down') => {
    const newIndex = direction === 'up' ? selectedIndex - 1 : selectedIndex + 1;
    if (newIndex >= 0 && newIndex < items.length) {
      onSelect(items[newIndex].id);
    }
  };

  return (
    <div className="flex flex-col items-center gap-2 h-full">
      {/* Up arrow */}
      <button
        onClick={() => handleNavigate('up')}
        disabled={selectedIndex <= 0}
        className="text-white/60 hover:text-white disabled:opacity-20 disabled:cursor-not-allowed
          transition-colors p-1 shrink-0"
        aria-label="Предыдущий"
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polyline points="18 15 12 9 6 15" />
        </svg>
      </button>

      {/* Scrollable item list */}
      <div
        ref={listRef}
        className="flex flex-col gap-2 overflow-y-auto gold-scrollbar flex-1 w-full
          md:max-h-[400px] max-h-[200px] px-1"
      >
        {items.map((item) => {
          const isSelected = item.id === selectedId;

          return (
            <motion.button
              key={item.id}
              onClick={() => onSelect(item.id)}
              layout
              animate={{
                opacity: isSelected ? 1 : 0.45,
                scale: isSelected ? 1 : 0.92,
              }}
              whileHover={!isSelected ? { opacity: 0.7, scale: 0.96 } : undefined}
              transition={{ duration: 0.25, ease: 'easeOut' }}
              className={`flex items-center gap-3 p-2 rounded-card cursor-pointer
                transition-colors shrink-0 w-full text-left
                ${isSelected ? 'gold-outline relative' : 'hover:bg-white/5'}`}
            >
              {/* Thumbnail */}
              <div className="w-16 h-16 md:w-20 md:h-20 rounded-full overflow-hidden shrink-0 bg-white/10">
                {item.image ? (
                  <img
                    src={item.image}
                    alt={item.name}
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center text-white/30 text-xs">
                    ?
                  </div>
                )}
              </div>

              {/* Name */}
              <span
                className={`font-medium uppercase text-sm md:text-base truncate
                  ${isSelected ? 'gold-text' : 'text-white'}`}
              >
                {item.name}
              </span>
            </motion.button>
          );
        })}
      </div>

      {/* Down arrow */}
      <button
        onClick={() => handleNavigate('down')}
        disabled={selectedIndex >= items.length - 1}
        className="text-white/60 hover:text-white disabled:opacity-20 disabled:cursor-not-allowed
          transition-colors p-1 shrink-0"
        aria-label="Следующий"
      >
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </button>
    </div>
  );
};

export default VerticalCarousel;
