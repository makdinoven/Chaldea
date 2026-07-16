import { useState } from 'react';
import type { MouseEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import CircleButton from './CircleButton/CircleButton';

export interface SliderPage {
  index: number;
  title: string;
  description: string;
  link: string;
  img: string;
  tag: string;
}

interface SliderProps {
  pages: SliderPage[];
}

const ARROW_BUTTON_CLASS =
  'flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-black/40 text-white transition-colors duration-200 ease-site hover:text-gold';

/**
 * Hero slider for the main page. Layout per the redesign reference:
 * controls (arrows + dots) in the top-left bar, tag in the top-right,
 * title / description / "Читать" pinned to the bottom-left.
 * Clicking anywhere on the slide navigates to the slide link.
 */
export default function Slider({ pages }: SliderProps) {
  const [currentIndex, setCurrentIndex] = useState(0);
  const navigate = useNavigate();

  if (pages.length === 0) return null;

  const current = pages[currentIndex];

  const handlePrev = (e: MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    setCurrentIndex((prev) => (prev === 0 ? pages.length - 1 : prev - 1));
  };

  const handleNext = (e: MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    setCurrentIndex((prev) => (prev === pages.length - 1 ? 0 : prev + 1));
  };

  return (
    <div
      onClick={() => navigate(current.link)}
      className="image-card relative h-full w-full cursor-pointer rounded-card shadow-card"
      style={{ backgroundImage: `url(${current.img})` }}
    >
      {/* Readability gradient over the slide image */}
      <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-black/15 via-black/5 to-black/85" />

      {/* Top bar: arrows + dots on the left, tag on the right */}
      <div className="absolute inset-x-0 top-0 flex items-center justify-between gap-3 px-5 py-4 sm:px-[26px] sm:py-[22px]">
        <div className="flex items-center gap-3 sm:gap-3.5">
          <button
            type="button"
            aria-label="Предыдущий слайд"
            onClick={handlePrev}
            className={ARROW_BUTTON_CLASS}
          >
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>

          <div className="flex gap-[9px]">
            {pages.map((_, index) => (
              <CircleButton
                key={index}
                isActive={index === currentIndex}
                onClick={() => setCurrentIndex(index)}
              />
            ))}
          </div>

          <button
            type="button"
            aria-label="Следующий слайд"
            onClick={handleNext}
            className={ARROW_BUTTON_CLASS}
          >
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>
        </div>

        <span className="gold-text truncate text-[13px] font-bold italic uppercase tracking-[0.06em] sm:text-[15px]">
          {current.tag}
        </span>
      </div>

      {/* Bottom: title / description / "Читать" */}
      <div className="absolute inset-x-0 bottom-0 flex flex-col items-start px-5 pb-6 sm:px-10 sm:pb-[34px]">
        <h2 className="relative pb-[7px] text-2xl font-normal uppercase text-white [text-shadow:0_4px_4px_rgba(0,0,0,0.25)] after:absolute after:bottom-0 after:left-0 after:h-px after:w-[114%] after:max-w-full after:bg-gradient-to-r after:from-transparent after:via-[#999] after:to-transparent after:content-[''] sm:text-[32px]">
          {current.title}
        </h2>
        <p className="max-w-[560px] pt-3.5 text-sm font-light tracking-[0.06em] text-white sm:text-base">
          {current.description}
        </p>
        <span className="mt-3 inline-flex w-fit items-center gap-2 text-[13px] font-medium uppercase tracking-[0.08em] text-gold transition-colors duration-200 ease-site hover:text-gold-light">
          Читать
          <svg
            width="15"
            height="15"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <line x1="5" y1="12" x2="19" y2="12" />
            <polyline points="12 5 19 12 12 19" />
          </svg>
        </span>
      </div>
    </div>
  );
}
