import { useCallback, useState } from "react";
import Cropper, { type Area } from "react-easy-crop";

const MIN_ZOOM = 1;
const MAX_ZOOM = 5;
const ZOOM_STEP = 0.05;

interface ItemImageCropperProps {
  /** Picture to frame: an object URL of a fresh file or the stored original */
  src: string;
  /** Called with the chosen square in source-image pixels */
  onCropChange: (pixels: Area) => void;
}

/** Shows how the chosen area looks in a small icon slot. */
const IconPreview = ({ src, area, rounded }: { src: string; area: Area; rounded: string }) => (
  <div className={`relative w-16 h-16 overflow-hidden bg-white/5 ${rounded}`}>
    <img
      src={src}
      alt=""
      className="absolute max-w-none"
      style={{
        width: `${10000 / area.width}%`,
        left: `${(-area.x * 100) / area.width}%`,
        top: `${(-area.y * 100) / area.height}%`,
      }}
    />
  </div>
);

const ItemImageCropper = ({ src, onCropChange }: ItemImageCropperProps) => {
  const [crop, setCrop] = useState({ x: 0, y: 0 });
  const [zoom, setZoom] = useState(MIN_ZOOM);
  const [area, setArea] = useState<Area | null>(null);

  const handleCropComplete = useCallback(
    (croppedArea: Area, croppedAreaPixels: Area) => {
      setArea(croppedArea);
      onCropChange(croppedAreaPixels);
    },
    [onCropChange],
  );

  return (
    <div className="flex flex-col md:flex-row gap-4">
      <div className="flex-1 min-w-0 flex flex-col gap-3">
        <div className="relative w-full h-64 sm:h-80 rounded-card overflow-hidden bg-black/40 touch-none">
          <Cropper
            image={src}
            crop={crop}
            zoom={zoom}
            minZoom={MIN_ZOOM}
            maxZoom={MAX_ZOOM}
            aspect={1}
            showGrid
            onCropChange={setCrop}
            onZoomChange={setZoom}
            onCropComplete={handleCropComplete}
          />
        </div>
        <label className="flex items-center gap-3">
          <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em] shrink-0">
            Масштаб
          </span>
          <input
            type="range"
            min={MIN_ZOOM}
            max={MAX_ZOOM}
            step={ZOOM_STEP}
            value={zoom}
            onChange={(e) => setZoom(Number(e.target.value))}
            className="w-full accent-site-blue"
          />
        </label>
        <p className="text-white/40 text-xs">
          Перетащите картинку, чтобы выбрать область для иконки. В описании предмета будет видна вся картинка.
        </p>
      </div>

      <div className="flex md:flex-col items-center gap-3 md:w-28">
        <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
          Иконка
        </span>
        {area && (
          <>
            <IconPreview src={src} area={area} rounded="rounded-card" />
            <IconPreview src={src} area={area} rounded="rounded-full" />
          </>
        )}
      </div>
    </div>
  );
};

export default ItemImageCropper;
