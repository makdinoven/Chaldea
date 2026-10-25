import { useState } from 'react';
import toast from 'react-hot-toast';
import { useAppDispatch } from '../../../redux/store';
import { fetchFastSlots, fetchInventory } from '../../../redux/slices/profileSlice';
import { consumeFromBackpack, unpackFromBackpack, type BackpackEntry } from '../../../api/backpack';
import { apiErrorMessage } from '../../../api/errors';
import ItemSlot from '../../CommonComponents/ItemSlot/ItemSlot';
import PopoverMenu, { type MenuEntry } from '../../CommonComponents/ItemSlot/PopoverMenu';
import useBackpack from '../../CommonComponents/ItemSlot/useBackpack';
import { useInventoryCharacterId } from '../InventoryTab/dnd/InventoryDndContext';
import { recoveryLine } from '../../DungeonPage/dungeonItems';

/*
  FEAT-178: the camp backpack under the inventory — its slots with what is
  packed. A consumable goes in from its own menu («В рюкзак»); a click on a
  packed stack uses it or takes it back out (not during a dungeon run).
*/

const BackpackStrip = () => {
  const characterId = useInventoryCharacterId();
  const dispatch = useAppDispatch();
  const { state, error } = useBackpack(characterId);
  const [menu, setMenu] = useState<{ entry: BackpackEntry; x: number; y: number } | null>(null);

  if (error) return <p className="px-4 lg:px-5 pb-3 text-xs text-site-red">{error}</p>;
  if (!state?.backpack || !characterId) return null;

  const refresh = () => {
    dispatch(fetchInventory(characterId));
    dispatch(fetchFastSlots(characterId));
  };
  const run = async (job: () => Promise<unknown>, done: string, failed: string) => {
    try {
      await job();
      toast.success(done);
      refresh();
    } catch (e) {
      toast.error(apiErrorMessage(e, failed));
    }
  };

  const entries = (entry: BackpackEntry): MenuEntry[] => {
    const shut = state.in_dungeon ? 'В подземелье рюкзак не разбирают' : undefined;
    const list: MenuEntry[] = [
      {
        label: entry.is_food ? 'Съесть' : 'Использовать',
        onSelect: () => void run(() => consumeFromBackpack(characterId, entry.id), `Использовано: ${entry.name}`,
          'Не удалось использовать предмет'),
      },
      {
        label: 'Выложить',
        disabled: state.in_dungeon,
        hint: shut,
        onSelect: () => void run(() => unpackFromBackpack(characterId, entry.id, 1), `${entry.name} — в инвентаре`,
          'Не удалось выложить предмет'),
      },
    ];
    if (entry.quantity > 1) {
      list.push({
        label: `Выложить все (${entry.quantity})`,
        disabled: state.in_dungeon,
        hint: shut,
        onSelect: () => void run(() => unpackFromBackpack(characterId, entry.id, entry.quantity),
          `${entry.name} ×${entry.quantity} — в инвентаре`, 'Не удалось выложить предмет'),
      });
    }
    return list;
  };

  const free = Math.max(0, state.capacity - state.items.length);
  return (
    <div className="shrink-0 px-4 lg:px-5 pb-4 pt-3 border-t border-white/10">
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="gold-text text-xs font-medium uppercase tracking-[0.06em] truncate">
          Походный рюкзак
        </span>
        <span className="text-white/50 text-xs font-mono shrink-0">
          {state.items.length}/{state.capacity}
        </span>
      </div>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(44px,1fr))] gap-2.5">
        {state.items.map((entry) => (
          <ItemSlot
            key={entry.id}
            name={entry.name}
            image={entry.image_url}
            rarity={entry.rarity}
            quantity={entry.quantity}
            selected={menu?.entry.id === entry.id}
            onClick={(e) => setMenu({ entry, x: e.clientX, y: e.clientY })}
          />
        ))}
        {Array.from({ length: free }, (_, i) => (
          <ItemSlot key={`free-${i}`} empty title="Свободный слот" />
        ))}
      </div>
      {state.items.length === 0 && (
        <p className="text-white/40 text-[11px] mt-2">
          Расходники кладутся в рюкзак из их меню — «В рюкзак». В подземелье из своих вещей доступно только то, что в
          рюкзаке.
        </p>
      )}
      {menu && (
        <PopoverMenu
          at={{ x: menu.x, y: menu.y }}
          title={menu.entry.name}
          details={recoveryLine(menu.entry) || menu.entry.description}
          entries={entries(menu.entry)}
          onClose={() => setMenu(null)}
        />
      )}
    </div>
  );
};

export default BackpackStrip;
