interface SubraceButtonProps {
  text: string;
  index: number;
  isActive: boolean;
  setCurrentIndex: (index: number) => void;
}

export default function SubraceButton({
  text,
  index,
  isActive,
  setCurrentIndex,
}: SubraceButtonProps) {
  function handleClick() {
    setCurrentIndex(index);
  }

  return (
    <button
      onClick={handleClick}
      className={`font-medium text-lg sm:text-xl uppercase transition-all duration-200 ease-site ${
        isActive
          ? 'gold-text'
          : 'text-white relative after:content-[""] after:absolute after:bottom-[-3px] after:left-1/2 after:w-0 after:h-px after:bg-gradient-to-r after:from-transparent after:via-[#999] after:to-transparent after:z-[1] after:-translate-x-1/2 after:transition-[width] after:duration-200 after:ease-site hover:after:w-full'
      }`}
    >
      {text}
    </button>
  );
}
