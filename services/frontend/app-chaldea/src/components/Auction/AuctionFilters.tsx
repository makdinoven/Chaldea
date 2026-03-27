import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  setFilterItemType,
  setFilterRarity,
  setFilterSort,
  setFilterSearch,
  resetFilters,
  selectFilters,
} from '../../redux/slices/auctionSlice';

const ITEM_TYPE_OPTIONS: { value: string; label: string }[] = [
  { value: 'head', label: 'Голова' },
  { value: 'body', label: 'Тело' },
  { value: 'cloak', label: 'Плащ' },
  { value: 'belt', label: 'Пояс' },
  { value: 'ring', label: 'Кольцо' },
  { value: 'necklace', label: 'Ожерелье' },
  { value: 'bracelet', label: 'Браслет' },
  { value: 'main_weapon', label: 'Основное оружие' },
  { value: 'additional_weapons', label: 'Доп. оружие' },
  { value: 'shield', label: 'Щит' },
  { value: 'consumable', label: 'Расходуемое' },
  { value: 'resource', label: 'Ресурс' },
  { value: 'scroll', label: 'Свиток' },
  { value: 'misc', label: 'Разное' },
  { value: 'blueprint', label: 'Чертёж' },
  { value: 'recipe', label: 'Рецепт' },
  { value: 'gem', label: 'Камень' },
  { value: 'rune', label: 'Руна' },
];

const RARITY_OPTIONS: { value: string; label: string }[] = [
  { value: 'common', label: 'Обычное' },
  { value: 'rare', label: 'Редкое' },
  { value: 'epic', label: 'Эпическое' },
  { value: 'mythical', label: 'Мифическое' },
  { value: 'legendary', label: 'Легендарное' },
  { value: 'divine', label: 'Божественное' },
  { value: 'demonic', label: 'Демоническое' },
];

const SORT_OPTIONS: { value: string; label: string }[] = [
  { value: 'time_asc', label: 'Время: ближайшие' },
  { value: 'time_desc', label: 'Время: дальние' },
  { value: 'price_asc', label: 'Цена: по возрастанию' },
  { value: 'price_desc', label: 'Цена: по убыванию' },
  { value: 'name_asc', label: 'Имя: А-Я' },
  { value: 'name_desc', label: 'Имя: Я-А' },
];

const AuctionFilters = () => {
  const dispatch = useAppDispatch();
  const filters = useAppSelector(selectFilters);

  const selectClass =
    'bg-[#1a1a24] border border-white/20 rounded-card px-3 py-2 text-white text-sm ' +
    'focus:border-site-blue focus:outline-none transition-colors duration-200 ease-site ' +
    'cursor-pointer min-w-0 [&>option]:bg-[#1a1a24] [&>option]:text-white';

  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:gap-3">
      {/* Search */}
      <input
        type="text"
        value={filters.search}
        onChange={(e) => dispatch(setFilterSearch(e.target.value))}
        placeholder="Поиск по названию..."
        className="input-underline text-sm flex-1 min-w-[140px] sm:max-w-[240px]"
      />

      {/* Item type */}
      <select
        value={filters.itemType ?? ''}
        onChange={(e) =>
          dispatch(setFilterItemType(e.target.value || null))
        }
        className={selectClass}
      >
        <option value="">Все типы</option>
        {ITEM_TYPE_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>

      {/* Rarity */}
      <select
        value={filters.rarity ?? ''}
        onChange={(e) =>
          dispatch(setFilterRarity(e.target.value || null))
        }
        className={selectClass}
      >
        <option value="">Все редкости</option>
        {RARITY_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>

      {/* Sort */}
      <select
        value={filters.sort}
        onChange={(e) => dispatch(setFilterSort(e.target.value))}
        className={selectClass}
      >
        {SORT_OPTIONS.map((opt) => (
          <option key={opt.value} value={opt.value}>
            {opt.label}
          </option>
        ))}
      </select>

      {/* Reset */}
      <button
        onClick={() => dispatch(resetFilters())}
        className="text-site-blue text-sm hover:text-white transition-colors duration-200 ease-site whitespace-nowrap"
      >
        Сбросить
      </button>
    </div>
  );
};

export default AuctionFilters;
