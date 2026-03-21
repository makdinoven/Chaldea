import { LocationLootItem } from './types';
import { ITEM_TYPE_ICONS } from '../../ProfilePage/constants';

interface LootSectionProps {
  loot: LocationLootItem[];
  currentCharacterId: number | null;
  locationId: number;
  onPickup: (lootId: number) => void;
}

const LootSection = ({ loot, currentCharacterId, onPickup }: LootSectionProps) => {
  if (loot.length === 0) return null;

  return (
    <section className="gold-outline relative rounded-card bg-black/50 p-4 sm:p-6 flex flex-col gap-4">
      <h2 className="gold-text text-lg sm:text-xl font-medium uppercase">
        Лут на локации
      </h2>

      {(
        <div className="grid grid-cols-3 sm:grid-cols-4 lg:grid-cols-6 gap-3 sm:gap-4">
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
                className="flex flex-col items-center gap-2"
              >
                {/* Item icon */}
                <div className="relative">
                  <div
                    className={`item-cell ${rarityClass}`}
                  >
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
                        className="w-10 h-10 opacity-70"
                        draggable={false}
                      />
                    ) : (
                      <svg
                        xmlns="http://www.w3.org/2000/svg"
                        className="w-8 h-8 text-white/40"
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
                        absolute -bottom-1 -right-1 z-10 min-w-[20px] h-[20px]
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

                {/* Item name */}
                <span className="text-white/80 text-xs text-center leading-tight line-clamp-2 max-w-[80px]">
                  {lootItem.item_name ?? 'Неизвестный предмет'}
                </span>

                {/* Pickup button */}
                {currentCharacterId !== null && (
                  <button
                    onClick={() => onPickup(lootItem.id)}
                    className="btn-blue text-[10px] sm:text-xs px-2 sm:px-3 py-1 whitespace-nowrap"
                  >
                    Подобрать
                  </button>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
};

export default LootSection;
