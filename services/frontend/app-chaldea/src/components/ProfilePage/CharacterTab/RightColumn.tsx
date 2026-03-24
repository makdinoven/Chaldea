import CategorySidebar from '../InventoryTab/CategorySidebar';
import ItemGrid from '../InventoryTab/ItemGrid';

const RightColumn = () => {
  return (
    <div className="w-full flex gap-2 order-3 lg:h-[calc(100vh-120px)] lg:justify-end">
      <CategorySidebar />
      <div className="flex-1 min-w-0 lg:min-w-[340px] lg:h-full flex flex-col">
        <ItemGrid />
      </div>
    </div>
  );
};

export default RightColumn;
