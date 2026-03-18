interface CharacterInfoSmallProps {
  text: string;
}

export default function CharacterInfoSmall({ text }: CharacterInfoSmallProps) {
  return (
    <div className="relative text-white py-[15px] flex items-center justify-center before:content-[''] before:absolute before:bottom-0 before:left-1/2 before:-translate-x-1/2 before:w-full before:h-px before:bg-gradient-to-r before:from-transparent before:via-[#999] before:to-transparent before:z-[1]">
      <p className="font-normal text-base tracking-[-0.03em] text-center">
        {text}
      </p>
    </div>
  );
}
