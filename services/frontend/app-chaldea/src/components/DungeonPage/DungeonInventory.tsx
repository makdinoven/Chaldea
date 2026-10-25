import { useState } from 'react';
import toast from 'react-hot-toast';
import { giveFoundItem, itemLabel, type GroupInventoryItem, type SessionMember } from '../../api/dungeons';
import {
  beltFromBackpack,
  consumeFromBackpack,
  announceBackpackChange,
  takeOffBelt,
  type BackpackEntry,
  type BeltSlot,
} from '../../api/backpack';
import { apiErrorMessage } from '../../api/errors';
import ItemSlot from '../CommonComponents/ItemSlot/ItemSlot';
import PopoverMenu, { type MenuEntry } from '../CommonComponents/ItemSlot/PopoverMenu';
import useBackpack from '../CommonComponents/ItemSlot/useBackpack';
import DungeonKeys from './DungeonKeys';
import { recoveryLine, useItemCards } from './dungeonItems';

/*
  The run's things (FEAT-178), as cells with a menu on a click:
  - the keys found;
  - the party's finds — the leader hands a consumable to someone's backpack;
  - my camp backpack — use an item (out of battle) or put it on the belt;
  - my belt — what battle draws on; taken off, it goes back into the backpack.
  On a finished run (loot to share out) only the finds are shown.
*/

interface DungeonInventoryProps {
  items: GroupInventoryItem[];
  compact?: boolean;
  /** Keys found this run, shown above the items. */
  keys?: string[];
  sessionId?: number;
  /** The viewer's character: their backpack and belt are shown. */
  characterId?: number | null;
  isLeader?: boolean;
  members?: SessionMember[];
  /** The run goes on (finds can be handed out, the backpack used). */
  active?: boolean;
  /** A battle is on: things come off the belt only. */
  inBattle?: boolean;
  /** The group's finds changed (an item was handed out). */
  onChanged?: () => void;
}

type Menu =
  | { kind: 'find'; item: GroupInventoryItem; x: number; y: number }
  | { kind: 'pack'; entry: BackpackEntry; x: number; y: number }
  | { kind: 'belt'; slot: BeltSlot; x: number; y: number };

const BATTLE_HINT = 'В бою — только с пояса';
const word = (n: number) => (n === 1 ? 'предмет' : n > 1 && n < 5 ? 'предмета' : 'предметов');

const Heading = ({ title, note }: { title: string; note?: string }) => (
  <div className="flex items-center justify-between gap-2 mb-2">
    <h3 className="gold-text text-xs font-medium uppercase tracking-[0.06em]">{title}</h3>
    {note && <span className="text-white/40 text-[11px] font-mono">{note}</span>}
  </div>
);

const GRID = 'grid grid-cols-[repeat(auto-fill,minmax(46px,1fr))] gap-2.5';

const DungeonInventory = ({
  items, compact = false, keys = [], sessionId, characterId, isLeader = false, members = [], active = false,
  inBattle = false, onChanged,
}: DungeonInventoryProps) => {
  const showMine = active && !!characterId;
  const { state: pack, error: packError } = useBackpack(showMine ? characterId : null);
  const cards = useItemCards(items.map((i) => i.item_id));
  const [menu, setMenu] = useState<Menu | null>(null);

  const run = async (job: () => Promise<unknown>, done: string, failed: string) => {
    try {
      await job();
      toast.success(done);
    } catch (e) {
      toast.error(apiErrorMessage(e, failed));
    }
  };

  const findEntries = (item: GroupInventoryItem): MenuEntry[] => {
    const card = cards.get(item.item_id);
    if (!active) return [];
    if (!isLeader) return [{ label: 'Передать', disabled: true, hint: 'Находки раздаёт лидер' }];
    if (card && card.type !== 'consumable') {
      return [{ label: 'Передать', disabled: true, hint: 'Во время забега передаются только расходники' }];
    }
    const give = (to: SessionMember, quantity: number) => () =>
      void run(async () => {
        await giveFoundItem(sessionId!, characterId!, to.character_id, item.item_id, quantity);
        announceBackpackChange();
        onChanged?.();
      }, `${to.name}: ${itemLabel(item)} — в рюкзаке`, 'Не удалось передать предмет');
    const alive = members.filter((m) => m.status === 'alive');
    const who = (quantity: number): MenuEntry[] =>
      alive.map((m) => ({
        label: m.character_id === characterId ? `${m.name} (себе)` : m.name,
        hint: 'В походный рюкзак',
        onSelect: give(m, quantity),
      }));
    const list: MenuEntry[] = [{ label: 'Передать', children: who(1) }];
    if (item.quantity > 1) list.push({ label: `Передать все (${item.quantity})`, children: who(item.quantity) });
    return list;
  };

  const freeBelt = pack?.belt.filter((b) => b.item_id === null).length ?? 0;
  const packEntries = (entry: BackpackEntry): MenuEntry[] => [
    {
      label: entry.is_food ? 'Съесть' : 'Использовать',
      disabled: inBattle,
      hint: inBattle ? BATTLE_HINT : undefined,
      onSelect: () => void run(() => consumeFromBackpack(characterId!, entry.id), `Использовано: ${entry.name}`,
        'Не удалось использовать предмет'),
    },
    {
      label: 'На пояс',
      disabled: inBattle || entry.is_food || !pack?.belt.length,
      hint: inBattle ? BATTLE_HINT
        : entry.is_food ? 'Еду на пояс не кладут'
          : !pack?.belt.length ? 'Нет пояса с быстрыми слотами'
            : freeBelt === 0 ? 'Пояс полон — заменит первый слот' : undefined,
      onSelect: () => void run(() => beltFromBackpack(characterId!, entry.item_id, entry.id), `${entry.name} — на поясе`,
        'Не удалось положить на пояс'),
    },
  ];

  const beltEntries = (slot: BeltSlot): MenuEntry[] => [
    {
      label: 'Снять в рюкзак',
      disabled: inBattle,
      hint: inBattle ? 'Во время боя пояс не трогают' : undefined,
      onSelect: () => void run(() => takeOffBelt(characterId!, slot.slot_type), `${slot.name ?? 'Предмет'} — в рюкзаке`,
        'Не удалось снять с пояса'),
    },
  ];

  const pad = compact ? 'p-3' : 'p-4';
  return (
    <div className={`bg-black/40 rounded-card backdrop-blur-sm ${pad} flex flex-col gap-4`}>
      {keys.length > 0 && (
        <div>
          <Heading title="Ключи" />
          <DungeonKeys keys={keys} />
        </div>
      )}

      <div>
        <Heading title="Находки отряда" note={items.length ? `${items.length} ${word(items.length)}` : undefined} />
        {items.length === 0 ? (
          <p className="text-white/40 text-xs italic">Пока ничего не найдено</p>
        ) : (
          <div className={GRID}>
            {items.map((item, idx) => {
              const card = cards.get(item.item_id);
              return (
                <ItemSlot
                  key={`${item.item_id}-${idx}`}
                  name={itemLabel(item)}
                  image={card?.image_url}
                  rarity={card?.rarity}
                  itemType={card?.type}
                  quantity={item.quantity}
                  onClick={(e) => setMenu({ kind: 'find', item, x: e.clientX, y: e.clientY })}
                />
              );
            })}
          </div>
        )}
        {active && isLeader && items.length > 0 && (
          <p className="text-white/35 text-[11px] mt-2">Расходники можно сразу отдать участнику — кликните по предмету.</p>
        )}
      </div>

      {showMine && (
        <div>
          <Heading title="Мой рюкзак" note={pack?.backpack ? `${pack.items.length}/${pack.capacity}` : undefined} />
          {packError && <p className="text-site-red text-xs">{packError}</p>}
          {pack && !pack.backpack && (
            <p className="text-white/40 text-xs">
              Нет походного рюкзака — свои вещи в забеге недоступны. Рюкзак надевается в слот плаща.
            </p>
          )}
          {pack?.backpack && (
            <div className={GRID}>
              {pack.items.map((entry) => (
                <ItemSlot
                  key={entry.id}
                  name={entry.name}
                  image={entry.image_url}
                  rarity={entry.rarity}
                  quantity={entry.quantity}
                  onClick={(e) => setMenu({ kind: 'pack', entry, x: e.clientX, y: e.clientY })}
                />
              ))}
              {Array.from({ length: Math.max(0, pack.capacity - pack.items.length) }, (_, i) => (
                <ItemSlot key={`free-${i}`} empty title="Свободный слот" />
              ))}
            </div>
          )}
        </div>
      )}

      {showMine && pack && pack.belt.length > 0 && (
        <div>
          <Heading title="Пояс" note={inBattle ? 'в бою' : undefined} />
          <div className={GRID}>
            {pack.belt.map((slot, i) =>
              slot.item_id ? (
                <ItemSlot
                  key={slot.slot_type}
                  name={slot.name}
                  image={slot.image_url}
                  badge={i + 1}
                  onClick={(e) => setMenu({ kind: 'belt', slot, x: e.clientX, y: e.clientY })}
                />
              ) : (
                <ItemSlot key={slot.slot_type} empty badge={i + 1} title="Пустой слот пояса" />
              ),
            )}
          </div>
        </div>
      )}

      {menu?.kind === 'find' && (
        <PopoverMenu
          at={menu}
          title={itemLabel(menu.item)}
          details={[menu.item.source_description, cards.get(menu.item.item_id)?.description].filter(Boolean).join(' · ')}
          entries={findEntries(menu.item)}
          onClose={() => setMenu(null)}
        />
      )}
      {menu?.kind === 'pack' && (
        <PopoverMenu
          at={menu}
          title={menu.entry.name}
          details={recoveryLine(menu.entry) || menu.entry.description}
          entries={packEntries(menu.entry)}
          onClose={() => setMenu(null)}
        />
      )}
      {menu?.kind === 'belt' && (
        <PopoverMenu at={menu} title={menu.slot.name} entries={beltEntries(menu.slot)} onClose={() => setMenu(null)} />
      )}
    </div>
  );
};

export default DungeonInventory;
