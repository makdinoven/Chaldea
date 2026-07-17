import { useAppDispatch, useAppSelector } from '../../../redux/store';
import { setSelectedCategory, selectSelectedCategory } from '../../../redux/slices/profileSlice';
import { CATEGORY_LIST } from '../constants';

/**
 * FEAT-149: category filter as a horizontally scrollable row of icon-only
 * round chips (no text labels next to icons — user decision). The Russian
 * label survives as a `title` tooltip / aria-label for accessibility.
 * Category keys/icons are unchanged (shield stays a distinct item category).
 */
const CategorySidebar = () => {
  const dispatch = useAppDispatch();
  const selectedCategory = useAppSelector(selectSelectedCategory);

  return (
    <div className="flex items-center gap-2 overflow-x-auto gold-scrollbar [&::-webkit-scrollbar]:h-[3px] pb-1.5">
      {CATEGORY_LIST.map((cat) => {
        const isActive = selectedCategory === cat.key;
        return (
          <button
            key={cat.key}
            type="button"
            onClick={() => dispatch(setSelectedCategory(cat.key))}
            title={cat.label}
            aria-label={cat.label}
            aria-pressed={isActive}
            className={`shrink-0 flex items-center justify-center w-9 h-9 rounded-full border transition-all duration-200 ease-site ${
              isActive
                ? 'border-gold/50 bg-gold/10'
                : 'border-white/10 bg-white/[0.04] hover:border-white/30'
            }`}
          >
            <img
              src={cat.icon}
              alt=""
              draggable={false}
              className={`w-[18px] h-[18px] transition-opacity duration-200 ease-site ${
                isActive ? 'opacity-100' : 'opacity-60'
              }`}
            />
          </button>
        );
      })}
    </div>
  );
};

export default CategorySidebar;
