import { Fragment } from 'react';
import {
  ARMOR_SUBCLASS_LABELS,
  ARMOR_SUBCLASS_TYPES,
  ITEM_TYPE_LABELS,
  RARITY_LABELS,
  RARITY_TEXT_COLORS,
  WEAPON_KIND_CATEGORY,
  WEAPON_SUBCLASS_GROUPS,
  WEAPON_SUBCLASS_LABELS,
} from '../../constants/items';

interface ItemTypeLineProps {
  item: {
    item_type: string;
    item_rarity: string;
    item_level: number;
    weapon_subclass?: string | null;
    armor_subclass?: string | null;
  };
}

interface Segment {
  text: string;
  className: string;
}

/** "Одноручное оружие ◆ Меч ◆ Обычный ◆ Ур. 1" under an item's name */
const ItemTypeLine = ({ item }: ItemTypeLineProps) => {
  const segments: Segment[] = [];
  const kind = item.weapon_subclass;

  if (item.item_type === 'weapon' && kind && WEAPON_SUBCLASS_LABELS[kind]) {
    const category = WEAPON_SUBCLASS_GROUPS.find((g) => g.key === WEAPON_KIND_CATEGORY[kind]);
    if (category) segments.push({ text: category.label, className: 'text-white/55' });
    segments.push({ text: WEAPON_SUBCLASS_LABELS[kind], className: 'text-white' });
  } else {
    segments.push({ text: ITEM_TYPE_LABELS[item.item_type] ?? item.item_type, className: 'text-white/80' });
    if (ARMOR_SUBCLASS_TYPES.includes(item.item_type) && item.armor_subclass) {
      segments.push({ text: ARMOR_SUBCLASS_LABELS[item.armor_subclass] ?? item.armor_subclass, className: 'text-white' });
    }
  }

  segments.push({
    text: RARITY_LABELS[item.item_rarity] ?? item.item_rarity,
    className: `font-medium ${RARITY_TEXT_COLORS[item.item_rarity] ?? 'text-white'}`,
  });
  segments.push({ text: `Ур. ${item.item_level}`, className: 'text-gold' });

  return (
    <div className="flex flex-wrap items-center justify-center gap-x-2.5 gap-y-1 text-[11px] sm:text-xs uppercase tracking-[0.08em]">
      {segments.map((segment, index) => (
        <Fragment key={`${segment.text}-${index}`}>
          {index > 0 && (
            <span aria-hidden className="w-1 h-1 rotate-45 bg-gold/50 shrink-0" />
          )}
          <span className={`whitespace-nowrap ${segment.className}`}>{segment.text}</span>
        </Fragment>
      ))}
    </div>
  );
};

export default ItemTypeLine;
