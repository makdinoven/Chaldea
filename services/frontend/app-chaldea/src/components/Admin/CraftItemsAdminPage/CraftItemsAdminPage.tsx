import ItemsAdminPage, { CRAFT_ITEM_TYPES } from "../../ItemsAdminPage/ItemsAdminPage";

const CraftItemsAdminPage = () => (
  <ItemsAdminPage
    title="Крафтовые предметы"
    itemTypes={[...CRAFT_ITEM_TYPES]}
  />
);

export default CraftItemsAdminPage;
