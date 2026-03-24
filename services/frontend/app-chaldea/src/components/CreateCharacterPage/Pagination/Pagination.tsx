import CircleButton from '../../HomePage/Slider/CircleButton/CircleButton';
import PaginationButton from './PaginationButton/PaginationButton';

interface PageData {
  pageId: number;
  pageTitle: string;
}

interface PaginationProps {
  pages: PageData[];
  currentIndex: number;
  onIndexChange: (index: number) => void;
}

const Pagination = ({ pages, currentIndex, onIndexChange }: PaginationProps) => {
  const handlePrev = () => {
    onIndexChange(currentIndex === 0 ? 0 : currentIndex - 1);
  };

  const handleNext = () => {
    onIndexChange(
      currentIndex === pages.length - 1 ? currentIndex : currentIndex + 1
    );
  };

  const handleCircleClick = (index: number) => {
    onIndexChange(index);
  };

  return (
    <div className="flex justify-between w-full sm:w-1/2 items-center">
      <PaginationButton
        isDisabled={currentIndex === 0}
        text="Назад"
        onClick={handlePrev}
      />

      <div className="flex gap-[10px] items-center">
        {pages.map((_, index) => (
          <CircleButton
            key={index}
            isActive={index === currentIndex}
            onClick={() => handleCircleClick(index)}
          />
        ))}
      </div>

      <PaginationButton
        isDisabled={currentIndex === pages.length - 1}
        text="Вперед"
        onClick={handleNext}
      />
    </div>
  );
};

export default Pagination;
