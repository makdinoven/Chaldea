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
  /**
   * FEAT-154 (task #19, rule 33) — the furthest step that may be opened right
   * now. Steps beyond it are unreachable both through «Вперёд» and through the
   * dots, which is what closes the old hole: the dots used to jump straight to
   * the contract past every empty field.
   */
  maxReachableIndex: number;
  /** Why the way forward is closed — shown, and announced on a blocked click. */
  blockedMessage: string | null;
  /** Called when the player tries to move past `maxReachableIndex`. */
  onBlocked: (message: string) => void;
}

const Pagination = ({
  pages,
  currentIndex,
  onIndexChange,
  maxReachableIndex,
  blockedMessage,
  onBlocked,
}: PaginationProps) => {
  const isLast = currentIndex === pages.length - 1;
  // Going back is always allowed; only the way forward is ever gated.
  const canGoForward = !isLast && currentIndex < maxReachableIndex;

  const handlePrev = () => {
    if (currentIndex === 0) return;
    onIndexChange(currentIndex - 1);
  };

  const handleNext = () => {
    if (isLast) return;
    if (currentIndex >= maxReachableIndex) {
      if (blockedMessage) onBlocked(blockedMessage);
      return;
    }
    onIndexChange(currentIndex + 1);
  };

  const handleCircleClick = (index: number) => {
    if (index > maxReachableIndex) {
      if (blockedMessage) onBlocked(blockedMessage);
      return;
    }
    onIndexChange(index);
  };

  return (
    <div className="flex flex-col items-center gap-3 w-full px-4">
      <div className="flex justify-between w-full sm:w-1/2 items-center gap-3">
        <PaginationButton isDisabled={currentIndex === 0} text="Назад" onClick={handlePrev} />

        <div className="flex gap-[10px] items-center">
          {pages.map((page, index) => {
            const locked = index > maxReachableIndex;
            return (
              <span
                key={page.pageId}
                className={locked ? 'opacity-40 cursor-not-allowed' : ''}
                title={locked && blockedMessage ? blockedMessage : page.pageTitle}
              >
                <CircleButton
                  isActive={index === currentIndex}
                  onClick={() => handleCircleClick(index)}
                />
              </span>
            );
          })}
        </div>

        <PaginationButton
          isDisabled={!canGoForward}
          text="Вперёд"
          onClick={handleNext}
        />
      </div>

      {/* Says what is missing and on which step — never a silent dead button. */}
      {blockedMessage && !isLast && currentIndex >= maxReachableIndex && (
        <p role="status" className="text-white/50 text-[13px] sm:text-sm text-center max-w-[520px]">
          {blockedMessage}
        </p>
      )}
    </div>
  );
};

export default Pagination;
