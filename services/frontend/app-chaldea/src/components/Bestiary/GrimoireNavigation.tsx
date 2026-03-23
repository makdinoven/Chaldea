import { useEffect, useCallback } from 'react';

const titleFont = "'MedievalSharp', 'Georgia', serif";
const statFont = "'Cormorant Garamond', 'Georgia', serif";

interface GrimoireNavigationProps {
  currentIndex: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
  mobilePageLabel?: string;
}

const GrimoireNavigation = ({
  currentIndex,
  total,
  onPrev,
  onNext,
  mobilePageLabel,
}: GrimoireNavigationProps) => {
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'ArrowLeft') onPrev();
      else if (e.key === 'ArrowRight') onNext();
    },
    [onPrev, onNext],
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  const isFirst = currentIndex <= 0;
  const isLast = currentIndex >= total - 1;

  /* Roman numeral page counter for that old-book feel */
  const toRoman = (n: number): string => {
    if (n <= 0 || n > 50) return String(n);
    const vals = [50, 40, 10, 9, 5, 4, 1];
    const syms = ['L', 'XL', 'X', 'IX', 'V', 'IV', 'I'];
    let result = '';
    let num = n;
    for (let i = 0; i < vals.length; i++) {
      while (num >= vals[i]) {
        result += syms[i];
        num -= vals[i];
      }
    }
    return result;
  };

  return (
    <div className="flex items-center justify-center gap-4 sm:gap-8 mt-5 sm:mt-7">
      {/* Left arrow — bookmark tab style */}
      <button
        onClick={onPrev}
        disabled={isFirst}
        aria-label="Предыдущая страница"
        className="group w-11 h-11 sm:w-12 sm:h-12 flex items-center justify-center
                   disabled:opacity-15 disabled:cursor-not-allowed
                   transition-all duration-300 relative"
      >
        {/* Button background */}
        <div
          className="absolute inset-0 rounded-full transition-all duration-300
                     group-hover:scale-110 group-disabled:group-hover:scale-100"
          style={{
            background:
              'radial-gradient(circle, rgba(90,60,25,0.7) 0%, rgba(60,35,15,0.9) 100%)',
            border: '1px solid rgba(139,105,20,0.3)',
            boxShadow:
              'inset 0 1px 3px rgba(0,0,0,0.3), 0 2px 6px rgba(60,30,10,0.2)',
          }}
        />
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="w-4 h-4 sm:w-5 sm:h-5 relative z-10 transition-colors"
          style={{ color: '#c9a84c' }}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
        </svg>
      </button>

      {/* Page counter — Roman numeral style */}
      <div className="flex flex-col items-center gap-0.5 min-w-[90px]">
        <span
          className="text-base sm:text-lg tracking-[0.2em]"
          style={{ fontFamily: titleFont, color: 'rgba(201,168,76,0.5)' }}
        >
          {mobilePageLabel ?? toRoman(currentIndex + 1)}
        </span>
        <div className="flex items-center gap-1.5">
          <div className="w-4 h-px" style={{ background: 'rgba(139,105,20,0.25)' }} />
          <span
            className="text-[9px] tracking-widest uppercase"
            style={{ fontFamily: statFont, color: 'rgba(201,168,76,0.3)' }}
          >
            из {total}
          </span>
          <div className="w-4 h-px" style={{ background: 'rgba(139,105,20,0.25)' }} />
        </div>
      </div>

      {/* Right arrow */}
      <button
        onClick={onNext}
        disabled={isLast}
        aria-label="Следующая страница"
        className="group w-11 h-11 sm:w-12 sm:h-12 flex items-center justify-center
                   disabled:opacity-15 disabled:cursor-not-allowed
                   transition-all duration-300 relative"
      >
        <div
          className="absolute inset-0 rounded-full transition-all duration-300
                     group-hover:scale-110 group-disabled:group-hover:scale-100"
          style={{
            background:
              'radial-gradient(circle, rgba(90,60,25,0.7) 0%, rgba(60,35,15,0.9) 100%)',
            border: '1px solid rgba(139,105,20,0.3)',
            boxShadow:
              'inset 0 1px 3px rgba(0,0,0,0.3), 0 2px 6px rgba(60,30,10,0.2)',
          }}
        />
        <svg
          xmlns="http://www.w3.org/2000/svg"
          className="w-4 h-4 sm:w-5 sm:h-5 relative z-10 transition-colors"
          style={{ color: '#c9a84c' }}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
        </svg>
      </button>
    </div>
  );
};

export default GrimoireNavigation;
