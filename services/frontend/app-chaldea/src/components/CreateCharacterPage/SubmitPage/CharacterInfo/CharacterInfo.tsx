interface CharacterInfoProps {
  title: string;
  text: string;
}

export default function CharacterInfo({ title, text }: CharacterInfoProps) {
  return (
    <div className="relative text-white before:content-[''] before:absolute before:top-[-8px] before:left-1/2 before:-translate-x-1/2 before:w-full before:h-px before:bg-gradient-to-r before:from-transparent before:via-[#999] before:to-transparent before:z-[1]">
      <h3 className="font-semibold text-xl tracking-[-0.03em] text-center mb-5">
        {title}
      </h3>
      <p className="font-normal text-base tracking-[-0.03em]">{text}</p>
    </div>
  );
}
