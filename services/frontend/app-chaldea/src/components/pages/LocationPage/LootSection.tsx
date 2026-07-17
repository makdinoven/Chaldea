import { LocationLootItem } from './types';
import { ITEM_TYPE_ICONS } from '../../ProfilePage/constants';

interface LootSectionProps {
  loot: LocationLootItem[];
  currentCharacterId: number | null;
  locationId: number;
  onPickup: (lootId: number) => void;
}

/** Rarity → item name color (mock: common items stay white). */
const getRarityTextClass = (rarity?: string | null): string => {
  switch (rarity) {
    case 'rare': return 'text-rarity-rare';
    case 'epic': return 'text-rarity-epic';
    case 'mythical': return 'text-rarity-mythical';
    case 'legendary': return 'text-rarity-legendary';
    default: return 'text-white';
  }
};

/**
 * «На земле» — sidebar loot list (FEAT-152 §3.5, B11): real item images in
 * rarity frames, quantity badge, «Подобрать». Hidden entirely when empty.
 */
const LootSection = ({ loot, currentCharacterId, onPickup }: LootSectionProps) => {
  if (loot.length === 0) return null;

  return (
    <section className="bg-site-bg backdrop-blur-sm rounded-card border border-gold-dark/20 shadow-card overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-2.5 px-4 sm:px-5 py-3.5 border-b border-white/[0.07]">
        <svg xmlns="http://www.w3.org/2000/svg" className="w-[18px] h-[18px] text-gold shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M20 12v10H4V12" />
          <rect x="2" y="7" width="20" height="5" strokeLinecap="round" strokeLinejoin="round" />
          <line x1="12" y1="22" x2="12" y2="7" strokeLinecap="round" strokeLinejoin="round" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 7H7.5a2.5 2.5 0 010-5C11 2 12 7 12 7z" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 7h4.5a2.5 2.5 0 000-5C13 2 12 7 12 7z" />
        </svg>
        <h2 className="gold-text text-[13px] font-medium uppercase tracking-[0.08em]">
          На земле
        </h2>
        <span className="bg-white/10 text-white/60 text-[10px] font-bold px-2 py-0.5 rounded-full min-w-[20px] text-center">
          {loot.length}
        </span>
      </div>

      {/* Loot rows */}
      <div className="flex flex-col gap-2 p-3.5 sm:p-4">
        {loot.map((lootItem) => {
          const rarityClass =
            lootItem.item_rarity && lootItem.item_rarity !== 'common'
              ? `rarity-${lootItem.item_rarity}`
              : '';
          const placeholderIcon =
            lootItem.item_type ? ITEM_TYPE_ICONS[lootItem.item_type] : undefined;

          return (
            <div
              key={lootItem.id}
              className="flex items-center gap-3 p-2.5 rounded-card bg-white/[0.03] border border-white/[0.06]"
            >
              {/* Item icon in a rarity frame */}
              <div className="relative shrink-0">
                <div className={`item-cell ${rarityClass} !w-11 !h-11`}>
                  {lootItem.item_image ? (
                    <img
                      src={lootItem.item_image}
                      alt={lootItem.item_name ?? 'Предмет'}
                      className="w-full h-full object-cover"
                      draggable={false}
                    />
                  ) : placeholderIcon ? (
                    <img
                      src={placeholderIcon}
                      alt={lootItem.item_name ?? 'Предмет'}
                      className="w-6 h-6 opacity-70"
                      draggable={false}
                    />
                  ) : (
                    <svg
                      xmlns="http://www.w3.org/2000/svg"
                      className="w-5 h-5 text-white/40"
                      fill="none"
                      viewBox="0 0 24 24"
                      stroke="currentColor"
                      strokeWidth={1.5}
                    >
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        d="M20 7l-8-4-8 4m16 0l-8 4m8-4v10l-8 4m0-10L4 7m8 4v10M4 7v10l8 4"
                      />
                    </svg>
                  )}
                </div>

                {/* Quantity badge */}
                {lootItem.quantity > 1 && (
                  <span
                    className="
                      absolute -bottom-1 -right-1 z-10 min-w-[18px] h-[18px]
                      flex items-center justify-center
                      text-[10px] font-medium text-white
                      bg-site-bg rounded-full
                      border border-white/30 px-1
                    "
                  >
                    {lootItem.quantity}
                  </span>
                )}
              </div>

              {/* Name + quantity */}
              <div className="flex flex-col gap-0.5 min-w-0 flex-1">
                <span className={`text-[13px] font-medium truncate ${getRarityTextClass(lootItem.item_rarity)}`}>
                  {lootItem.item_name ?? 'Неизвестный предмет'}
                </span>
                {lootItem.quantity > 1 && (
                  <span className="text-white/45 text-[10.5px]">
                    ×{lootItem.quantity}
                  </span>
                )}
              </div>

              {/* Pickup button (mock: gold outline) */}
              {currentCharacterId !== null && (
                <button
                  onClick={() => onPickup(lootItem.id)}
                  className="shrink-0 px-3.5 py-1.5 rounded-[9px] border border-gold/40 text-gold text-[11px] font-medium
                             hover:bg-gold/15 transition-colors duration-200 ease-site whitespace-nowrap"
                >
                  Подобрать
                </button>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
};

export default LootSection;
