import wheelBackdrop from '../../assets/skillWheelBackdrop.png';

/**
 * The painted wheel behind the skill tree, registered onto the tree's own circle.
 *
 * The artwork's circle is neither centred in its file nor whole: measured on the
 * source, it is 1239px across but its centre sits 13px above the middle of the
 * 1254px square, and the top of the rim is clipped off by the file's edge, with
 * a band of black left over at the bottom. Fitting the file as-is therefore put
 * a dark crescent under the wheel and shaved the art at the top.
 *
 * So the image is placed by its circle rather than by its bounds: scaled until
 * that circle matches the frame, shifted so the two centres coincide, and
 * overscanned a little so the clipped top edge falls outside the round frame
 * instead of showing as a flat chord.
 */

/** Side of the source image, in its own pixels. */
const IMAGE_SIZE = 1254;
/** Centre of the painted circle within that image. */
const CIRCLE_CENTRE_X = 625;
const CIRCLE_CENTRE_Y = 606.5;
/** Diameter of the painted circle, taken from its widest row. */
const CIRCLE_DIAMETER = 1239;
/**
 * How far past the frame the art is pushed. The clipped top reaches 97.9% of the
 * circle's radius, so anything above ~1.022 hides it; 1.04 leaves margin.
 */
const OVERSCAN = 1.04;

/** Displayed size of the whole image, as a share of the frame. */
const SIZE_PERCENT = (IMAGE_SIZE / CIRCLE_DIAMETER) * OVERSCAN * 100;
const LEFT_PERCENT = 50 - (CIRCLE_CENTRE_X / IMAGE_SIZE) * SIZE_PERCENT;
const TOP_PERCENT = 50 - (CIRCLE_CENTRE_Y / IMAGE_SIZE) * SIZE_PERCENT;

interface WheelBackdropProps {
  /** Darkening laid over the art so the nodes stay legible, 0..1. */
  dim?: number;
}

const WheelBackdrop = ({ dim = 0.45 }: WheelBackdropProps) => (
  <div className="absolute inset-0 grid place-items-center overflow-hidden pointer-events-none">
    {/* A square that fits the frame whichever way round it is, so the art stays
        circular even on the admin's wide panel. */}
    <div className="relative w-full aspect-square max-h-full overflow-hidden">
      <img
        src={wheelBackdrop}
        alt=""
        aria-hidden
        className="absolute max-w-none select-none"
        style={{
          width: `${SIZE_PERCENT}%`,
          height: `${SIZE_PERCENT}%`,
          left: `${LEFT_PERCENT}%`,
          top: `${TOP_PERCENT}%`,
        }}
      />
      <div
        className="absolute inset-0"
        style={{ background: `rgba(10,10,18,${dim})` }}
      />
    </div>
  </div>
);

export default WheelBackdrop;
