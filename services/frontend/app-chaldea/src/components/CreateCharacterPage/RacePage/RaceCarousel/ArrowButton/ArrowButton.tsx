interface ArrowButtonProps {
  text: string;
  onClick: (e: React.MouseEvent<HTMLButtonElement>) => void;
}

export default function ArrowButton({ text, onClick }: ArrowButtonProps) {
  const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation();
    onClick(e);
  };

  return (
    <button
      data-text={text}
      onClick={handleClick}
      className="relative inline-block font-bold text-[40px] sm:text-[64px] tracking-[-0.03em] text-center cursor-pointer bg-clip-text [-webkit-background-clip:text] [-webkit-text-fill-color:transparent] group"
      style={{
        fontVariant: 'small-caps',
        background: '#ffffff15',
        WebkitBackgroundClip: 'text',
        backgroundClip: 'text',
      }}
    >
      <span
        className="absolute inset-0 bg-gradient-to-b from-gold-light to-gold-dark bg-clip-text [-webkit-background-clip:text] [-webkit-text-fill-color:transparent] opacity-0 group-hover:opacity-100 transition-opacity duration-200 ease-site z-[1]"
        aria-hidden="true"
      >
        {text}
      </span>
      {text}
    </button>
  );
}
