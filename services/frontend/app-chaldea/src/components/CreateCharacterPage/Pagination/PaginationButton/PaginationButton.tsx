interface PaginationButtonProps {
  text: string;
  isDisabled: boolean;
  onClick: () => void;
}

const PaginationButton = ({ text, isDisabled, onClick }: PaginationButtonProps) => {
  const baseClasses =
    'font-bold text-base tracking-[-0.03em] text-center bg-clip-text [-webkit-background-clip:text] [-webkit-text-fill-color:transparent]';

  const disabledClasses =
    'cursor-default bg-gradient-to-b from-[#3d3d3d] to-[#656565]';

  const activeClasses =
    'relative bg-gradient-to-b from-gold-light to-gold-dark cursor-pointer ' +
    'after:content-[""] after:absolute after:bottom-[-5px] after:left-1/2 after:w-0 after:h-px ' +
    'after:bg-[linear-gradient(90deg,rgba(204,204,204,0)_0%,#999_42.5%,rgba(255,255,255,0)_100%)] ' +
    'after:z-[1] after:-translate-x-1/2 after:transition-all after:duration-200 after:ease-[ease-in-out] ' +
    'hover:after:w-[140%]';

  return (
    <button
      className={`${baseClasses} ${isDisabled ? disabledClasses : activeClasses}`}
      onClick={onClick}
    >
      {text}
    </button>
  );
};

export default PaginationButton;
