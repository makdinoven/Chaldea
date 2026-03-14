import { Search } from 'react-feather';

const SearchInput = () => {
  return (
    <div className="flex items-center gap-2 border-b border-white w-[252px] pb-1">
      <Search size={18} className="text-white flex-shrink-0" strokeWidth={2} />
      <input
        type="text"
        placeholder="ПОИСК"
        className="bg-transparent font-montserrat font-medium text-sm uppercase tracking-[0.06em] text-white placeholder-white/50 outline-none w-full"
      />
    </div>
  );
};

export default SearchInput;
