import { useAppSelector } from '../../../redux/store';
import { selectInventory } from '../../../redux/slices/profileSlice';
import PanelShell, { PANEL_DESKTOP_HEIGHT_CLASS } from '../PanelShell';
import CategorySidebar from '../InventoryTab/CategorySidebar';
import ItemGrid from '../InventoryTab/ItemGrid';
import bagIcon from '../../../assets/icons/equipment/bag.svg';

/**
 * Panel 3 (1fr) — «Инвентарь» (FEAT-149 Task 5):
 * header with item-count-only counter (user decision — no capacity limit),
 * horizontally scrollable icon-only category chips pinned under the header,
 * and the circular auto-fill item grid scrolling on its own
 * (the `drop-inventory-grid` droppable lives on the grid's scroll container).
 */
const InventoryPanel = () => {
  const inventory = useAppSelector(selectInventory);

  return (
    <PanelShell
      title="Инвентарь"
      icon={<img src={bagIcon} alt="" className="w-[18px] h-[18px] shrink-0" draggable={false} />}
      headerExtra={
        <span className="text-white/50 text-xs font-medium font-mono">{inventory.length}</span>
      }
      className={PANEL_DESKTOP_HEIGHT_CLASS}
      bodyClassName="flex-1 min-h-0 flex flex-col"
    >
      {/* Category chips — fixed strip, horizontal scroll */}
      <div className="shrink-0 px-4 lg:px-5 pt-3.5 pb-1">
        <CategorySidebar />
      </div>

      {/* Item grid — scrolls internally on desktop */}
      <div className="flex-1 min-h-0 px-4 lg:px-5 pb-4 pt-2 flex flex-col">
        <ItemGrid />
      </div>
    </PanelShell>
  );
};

export default InventoryPanel;
