import type { MouseEvent } from 'react';

interface CircleButtonProps {
  isActive: boolean;
  onClick?: (e: MouseEvent<HTMLButtonElement>) => void;
}

/**
 * Round pagination dot (17px). Gray by default, gold gradient when active
 * or hovered. Used by the main-page slider and character-creation pagination.
 */
export default function CircleButton({ isActive, onClick }: CircleButtonProps) {
  const handleClick = (e: MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    onClick?.(e);
  };

  return (
    <button
      type="button"
      onClick={handleClick}
      aria-label={isActive ? 'Текущий слайд' : 'Перейти к слайду'}
      className={`relative h-[17px] w-[17px] overflow-hidden rounded-full transition-colors duration-200 ease-site before:absolute before:inset-0 before:bg-gradient-to-b before:from-gold-light before:to-gold-dark before:opacity-0 before:transition-opacity before:duration-200 before:content-[''] hover:before:opacity-100 ${
        isActive ? 'bg-transparent before:opacity-100' : 'bg-[#a4a4a4]/55'
      }`}
    />
  );
}
