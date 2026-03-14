import { useAppDispatch, useAppSelector } from '../../../redux/store';
import { setSelectedCategory, selectSelectedCategory } from '../../../redux/slices/profileSlice';
import { CATEGORY_LIST } from '../constants';

const CategorySidebar = () => {
  const dispatch = useAppDispatch();
  const selectedCategory = useAppSelector(selectSelectedCategory);

  return (
    <div className="flex flex-col items-center gap-1 py-2">
      {CATEGORY_LIST.map((cat) => {
        const isActive = selectedCategory === cat.key;
        return (
          <button
            key={cat.key}
            onClick={() => dispatch(setSelectedCategory(cat.key))}
            className={`hover-divider ${
              isActive ? 'category-icon category-icon-active' : 'category-icon'
            }`}
            title={cat.label}
          >
            <img src={cat.icon} alt={cat.label} draggable={false} />
          </button>
        );
      })}
    </div>
  );
};

export default CategorySidebar;
