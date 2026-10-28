import { Armchair } from 'lucide-react';
import type { FurnitureGroup, RoomFurniture } from '../../../api/houses';
import { furnitureBonusText } from '../../../utils/furniture';

/*
  FEAT-180 stage 3 — a placed piece of furniture as a round item picture with
  its rarity rim, and a row of them for room cards and the room page.
*/

const SIZE = {
  sm: '!w-8 !h-8',
  md: '!w-11 !h-11',
  lg: '!w-14 !h-14',
} as const;

const ICON_SIZE = { sm: 14, md: 18, lg: 22 } as const;

interface FurnitureIconProps {
  name: string;
  image: string | null;
  rarity: string | null;
  size?: keyof typeof SIZE;
  title?: string;
}

/** Round picture of a furniture item (or an armchair when it has none). */
export const FurnitureIcon = ({ name, image, rarity, size = 'md', title }: FurnitureIconProps) => (
  <div className={`item-cell ${rarity && rarity !== 'common' ? `rarity-${rarity}` : ''} ${SIZE[size]} shrink-0`}
    title={title ?? name}>
    {image ? (
      <img src={image} alt={name} className="w-full h-full object-cover" draggable={false} />
    ) : (
      <Armchair size={ICON_SIZE[size]} className="text-white/50" />
    )}
  </div>
);

/** «Тестовая кровать — Сон +0,5» for a title. */
export const furnitureTitle = (group: FurnitureGroup | null, piece: RoomFurniture) =>
  `${piece.name} — ${furnitureBonusText(group, piece)}`;

interface FurnitureThumbsProps {
  /** The room's furniture group (decides how bonuses read). */
  group: FurnitureGroup | null;
  furniture: RoomFurniture[];
  size?: keyof typeof SIZE;
  className?: string;
}

/** A row of placed pieces; the name and bonus show on hover. */
const FurnitureThumbs = ({ group, furniture, size = 'sm', className = '' }: FurnitureThumbsProps) => {
  if (furniture.length === 0) return null;
  return (
    <div className={`flex items-center gap-1.5 flex-wrap ${className}`}>
      {furniture.map((piece) => (
        <FurnitureIcon key={piece.id} name={piece.name} image={piece.image} rarity={piece.rarity} size={size}
          title={furnitureTitle(group, piece)} />
      ))}
    </div>
  );
};

export default FurnitureThumbs;
