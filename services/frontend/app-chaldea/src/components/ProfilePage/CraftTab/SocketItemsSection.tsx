// FEAT-166 — socket extraction section for the Craft tab. Merges the former
// separate jeweler (variant="gem") and enchanter (variant="rune") sections:
// same filtering, socket counting and modal, parametrised by the config below.
import { useState, useMemo } from 'react';
import { motion } from 'motion/react';
import { useAppSelector } from '../../../redux/store';
import { selectInventory, selectEquipmentSlots } from '../../../redux/slices/profileSlice';
import SectionHeader from '../shared/SectionHeader';
import { MotionProfileCard } from '../shared/ProfileCard';
import GemSocketModal from './GemSocketModal';
import type { JewelryItemRef } from './GemSocketModal';
import { JEWELRY_SOCKET_TYPES, RUNE_SOCKET_TYPES } from '../../../constants/professions';

// Legacy belts may still hold runes: they are listed for extraction only
const RUNE_EXTRACT_TYPES = new Set([...RUNE_SOCKET_TYPES, 'belt']);

export type SocketItemsVariant = 'gem' | 'rune';

interface VariantConfig {
  itemTypes: Set<string>;
  /**
   * gem: only items whose template has sockets, socket count = template count.
   * rune: any item of the type, socket count = max(template count, stored gems)
   * (legacy belts have no template sockets but may still hold runes).
   */
  legacySocketCount: boolean;
  title: string;
  description: string;
  hint: string;
  emptyText: string;
  countLabel: string;
  filledDotClass: string;
}

const VARIANTS: Record<SocketItemsVariant, VariantConfig> = {
  gem: {
    itemTypes: JEWELRY_SOCKET_TYPES,
    legacySocketCount: false,
    title: 'Извлечение огранок',
    description: 'Вы можете извлекать огранки из украшений.',
    hint: 'Вставить огранку может любой игрок через меню предмета «Гнёзда».',
    emptyText: 'Нет украшений со вставленными огранками',
    countLabel: 'огранок',
    filledDotClass: 'bg-gold border-gold-dark',
  },
  rune: {
    itemTypes: RUNE_EXTRACT_TYPES,
    legacySocketCount: true,
    title: 'Извлечение рун',
    description: 'Вы можете извлекать руны из предметов.',
    hint: 'Вставить руну может любой игрок через меню предмета «Гнёзда».',
    emptyText: 'Нет предметов со вставленными рунами',
    countLabel: 'рун',
    filledDotClass: 'bg-rarity-epic border-rarity-epic',
  },
};

function parseSocketedGems(raw: string | null | undefined): (number | null)[] {
  if (!raw) return [];
  try {
    return JSON.parse(raw);
  } catch {
    return [];
  }
}

// `!` so the rarity colour wins over ProfileCard's base `border-white/10`
const rarityBorder = (rarity: string) => {
  switch (rarity) {
    case 'rare': return '!border-rarity-rare';
    case 'epic': return '!border-rarity-epic';
    case 'mythical': return '!border-rarity-mythical';
    case 'legendary': return '!border-rarity-legendary';
    default: return '!border-white/20';
  }
};

const filledCount = (gems: (number | null)[]) => gems.filter((g) => g !== null).length;

interface SocketItemsSectionProps {
  characterId: number;
  variant: SocketItemsVariant;
}

const SocketItemsSection = ({ characterId, variant }: SocketItemsSectionProps) => {
  const config = VARIANTS[variant];
  const inventory = useAppSelector(selectInventory);
  const equipment = useAppSelector(selectEquipmentSlots);
  const [selectedItem, setSelectedItem] = useState<JewelryItemRef | null>(null);

  const items = useMemo(() => {
    const result: JewelryItemRef[] = [];
    const { itemTypes, legacySocketCount } = config;

    const matches = (itemType: string, socketCount: number) =>
      itemTypes.has(itemType) && (legacySocketCount || socketCount > 0);
    const countSockets = (socketCount: number, gems: (number | null)[]) =>
      legacySocketCount ? Math.max(socketCount ?? 0, gems.length) : socketCount;

    for (const inv of inventory) {
      if (matches(inv.item.item_type, inv.item.socket_count)) {
        const gems = parseSocketedGems(inv.socketed_gems);
        // Extraction section: only items with something to extract
        if (!gems.some((g) => g !== null)) continue;
        result.push({
          rowId: inv.id,
          itemId: inv.item.id,
          name: inv.item.name,
          image: inv.item.image,
          itemType: inv.item.item_type,
          itemRarity: inv.item.item_rarity,
          socketCount: countSockets(inv.item.socket_count, gems),
          socketedGems: gems,
          enhancementPointsSpent: inv.enhancement_points_spent ?? 0,
          source: 'inventory',
        });
      }
    }

    for (const slot of equipment) {
      if (slot.item && matches(slot.item.item_type, slot.item.socket_count)) {
        const gems = parseSocketedGems(slot.socketed_gems);
        if (!gems.some((g) => g !== null)) continue;
        result.push({
          rowId: slot.id ?? 0,
          itemId: slot.item.id,
          name: slot.item.name,
          image: slot.item.image,
          itemType: slot.item.item_type,
          itemRarity: slot.item.item_rarity,
          socketCount: countSockets(slot.item.socket_count, gems),
          socketedGems: gems,
          enhancementPointsSpent: slot.enhancement_points_spent ?? 0,
          source: 'equipment',
        });
      }
    }

    return result;
  }, [inventory, equipment, config]);

  return (
    <div className="flex flex-col gap-3">
      <div className="space-y-1.5">
        <SectionHeader title={config.title} />
        <p className="text-xs text-white/50">{config.description}</p>
        <p className="text-xs text-white/40">{config.hint}</p>
      </div>

      {items.length === 0 ? (
        <p className="text-white/40 text-sm py-4 text-center">{config.emptyText}</p>
      ) : (
        <motion.div
          className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-2 gap-2.5"
          initial="hidden"
          animate="visible"
          variants={{ hidden: {}, visible: { transition: { staggerChildren: 0.04 } } }}
        >
          {items.map((item) => {
            const filled = filledCount(item.socketedGems);
            return (
              <MotionProfileCard
                key={`${item.source}-${item.rowId}`}
                as="button"
                interactive
                variants={{ hidden: { opacity: 0, y: 8 }, visible: { opacity: 1, y: 0 } }}
                onClick={() => setSelectedItem(item)}
                className={`!flex flex-col items-center gap-1.5 p-2.5 !text-center ${rarityBorder(item.itemRarity)}`}
              >
                <div className="w-14 h-14 sm:w-16 sm:h-16 rounded-full overflow-hidden bg-white/[0.05] flex items-center justify-center shrink-0">
                  {item.image ? (
                    <img src={item.image} alt={item.name} className="w-full h-full object-cover" />
                  ) : (
                    <span className="text-white/30 text-2xl">?</span>
                  )}
                </div>
                <span className="text-white text-xs leading-tight line-clamp-2 break-words">
                  {item.name}
                </span>

                {/* Socket indicators */}
                <div className="flex flex-wrap justify-center items-center gap-1">
                  {Array.from({ length: item.socketCount }, (_, i) => (
                    <span
                      key={i}
                      className={`w-3 h-3 rounded-full border ${
                        i < filled ? config.filledDotClass : 'bg-transparent border-white/30'
                      }`}
                    />
                  ))}
                </div>

                <span className="text-xs text-white/50">
                  {filled}/{item.socketCount} {config.countLabel}
                </span>

                {item.enhancementPointsSpent > 0 && (
                  <span className="text-[10px] text-gold">+{item.enhancementPointsSpent} заточка</span>
                )}
                {item.source === 'equipment' && (
                  <span className="text-[10px] text-site-blue">экипировано</span>
                )}
              </MotionProfileCard>
            );
          })}
        </motion.div>
      )}

      {selectedItem && (
        <GemSocketModal
          characterId={characterId}
          item={selectedItem}
          onClose={() => setSelectedItem(null)}
        />
      )}
    </div>
  );
};

export default SocketItemsSection;
