import type { MouseEvent } from 'react';
import { useNavigate } from 'react-router-dom';

export interface ButtonLink {
  name: string;
  link: string;
}

export interface ButtonData {
  id: number;
  titleName: string;
  titleLink: string;
  img: string;
  links?: ButtonLink[];
  type: 'large' | 'small';
}

interface ButtonProps {
  data: ButtonData;
}

/**
 * Main-page navigation card. Two variants:
 * - "large" — image card with a gold title and a sublink row at the bottom;
 * - "small" — compact quick-link card with a centered gold label.
 */
export default function Button({ data }: ButtonProps) {
  const navigate = useNavigate();

  const bgStyle = { backgroundImage: `url(${data.img})` };

  if (data.type === 'small') {
    return (
      <button
        type="button"
        onClick={() => navigate(data.titleLink)}
        className="image-card hover-gold-overlay flex h-full w-full items-center justify-center rounded-card shadow-card"
        style={bgStyle}
      >
        <span className="gold-text relative z-10 px-3 text-center text-xl font-medium uppercase leading-tight sm:text-2xl">
          {data.titleName}
        </span>
      </button>
    );
  }

  const handleSublinkClick = (e: MouseEvent<HTMLButtonElement>, link: string) => {
    e.stopPropagation();
    navigate(link);
  };

  return (
    <div
      onClick={() => navigate(data.titleLink)}
      className="image-card relative h-full w-full cursor-pointer rounded-card shadow-card"
      style={bgStyle}
    >
      <div className="absolute inset-0 flex flex-col justify-end bg-gradient-to-b from-transparent from-30% to-[#181e20]">
        <h3 className="gold-text text-center text-2xl font-medium uppercase sm:text-3xl">
          {data.titleName}
        </h3>

        <div className="relative mt-2 flex justify-between">
          <span className="absolute left-1/2 top-0 h-px w-[73%] -translate-x-1/2 bg-white" />
          {data.links?.map((link, index) => (
            <button
              key={index}
              type="button"
              className="hover-gold-overlay min-w-0 flex-1 px-1 pb-3 pt-[9px] text-center text-[11px] font-light uppercase tracking-[0.02em] text-white transition-colors duration-200 ease-site hover:text-site-blue sm:text-[13px] sm:tracking-[0.06em]"
              onClick={(e) => handleSublinkClick(e, link.link)}
            >
              <span className="relative z-10 block truncate">{link.name}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
