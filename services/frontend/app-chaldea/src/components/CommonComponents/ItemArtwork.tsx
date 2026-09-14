interface ItemArtworkProps {
  name: string;
  /** Uncropped original picture */
  fullImage?: string | null;
  /** Square icon — used when the item has no stored original */
  image?: string | null;
}

/**
 * The whole item picture for detail windows: centered, uncropped,
 * straight on the card background (no frame, no circle).
 */
const ItemArtwork = ({ name, fullImage, image }: ItemArtworkProps) => {
  const src = fullImage || image;

  return (
    <div className="flex justify-center items-center min-h-[6rem]">
      {src ? (
        <img
          src={src}
          alt={name}
          className="block max-w-full max-h-52 sm:max-h-72 object-contain"
        />
      ) : (
        <span className="text-5xl text-white/30">?</span>
      )}
    </div>
  );
};

export default ItemArtwork;
