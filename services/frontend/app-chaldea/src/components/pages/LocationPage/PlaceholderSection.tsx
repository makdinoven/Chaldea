interface PlaceholderSectionProps {
  title: string;
  message: string;
}

const PlaceholderSection = ({ title, message }: PlaceholderSectionProps) => {
  return (
    <section className="gold-outline relative rounded-card bg-black/70 p-5 sm:p-6 flex flex-col items-center gap-3 text-center">
      <h2 className="gold-text text-lg sm:text-xl font-medium uppercase">
        {title}
      </h2>
      <p className="text-white/50 text-sm">
        {message}
      </p>
    </section>
  );
};

export default PlaceholderSection;
