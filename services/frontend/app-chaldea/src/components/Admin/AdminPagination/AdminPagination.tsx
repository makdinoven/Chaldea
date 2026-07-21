import { useEffect, useId, useState } from 'react';

interface AdminPaginationProps {
  /** Current page, 1-based */
  page: number;
  /** Total number of pages */
  totalPages: number;
  onPageChange: (page: number) => void;
  /** Total item count — enables the "Показано X–Y из N" label */
  total?: number;
  /** Items per page — required together with `total` for the range label */
  pageSize?: number;
  className?: string;
}

/**
 * Pagination controls for admin list pages.
 * Adds a direct page-number input so long lists don't require clicking
 * through every page to reach the middle.
 */
const AdminPagination = ({
  page,
  totalPages,
  onPageChange,
  total,
  pageSize,
  className = '',
}: AdminPaginationProps) => {
  const inputId = useId();
  const [inputValue, setInputValue] = useState(String(page));

  // Keep the input in sync when the page changes from the outside
  // (Назад/Вперёд buttons, filter reset, etc.)
  useEffect(() => {
    setInputValue(String(page));
  }, [page]);

  if (totalPages <= 1) return null;

  const goTo = (target: number) => {
    const clamped = Math.min(Math.max(target, 1), totalPages);
    if (clamped !== page) onPageChange(clamped);
    setInputValue(String(clamped));
  };

  const commitInput = () => {
    const parsed = parseInt(inputValue, 10);
    if (Number.isNaN(parsed)) {
      setInputValue(String(page));
      return;
    }
    goTo(parsed);
  };

  const showRange = typeof total === 'number' && typeof pageSize === 'number';

  return (
    <div
      className={`flex flex-col sm:flex-row items-center justify-center gap-3 sm:gap-4 ${className}`}
    >
      {showRange && (
        <span className="text-white/50 text-sm sm:mr-auto">
          Показано {Math.min((page - 1) * pageSize! + 1, total!)}–
          {Math.min(page * pageSize!, total!)} из {total}
        </span>
      )}

      <div className="flex items-center gap-3">
        <button
          type="button"
          disabled={page <= 1}
          onClick={() => goTo(page - 1)}
          className="text-sm text-white hover:text-site-blue transition-colors duration-200 disabled:text-white/20 disabled:cursor-not-allowed"
        >
          Назад
        </button>

        <span className="text-sm text-white/60 whitespace-nowrap">
          {page} / {totalPages}
        </span>

        <button
          type="button"
          disabled={page >= totalPages}
          onClick={() => goTo(page + 1)}
          className="text-sm text-white hover:text-site-blue transition-colors duration-200 disabled:text-white/20 disabled:cursor-not-allowed"
        >
          Вперёд
        </button>
      </div>

      <div className="flex items-center gap-2">
        <label
          htmlFor={inputId}
          className="text-sm text-white/50 whitespace-nowrap"
        >
          Стр.
        </label>
        <input
          id={inputId}
          type="number"
          inputMode="numeric"
          min={1}
          max={totalPages}
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          onBlur={commitInput}
          onKeyDown={(e) => {
            if (e.key === 'Enter') {
              e.preventDefault();
              commitInput();
            }
          }}
          aria-label={`Перейти к странице, всего страниц: ${totalPages}`}
          className="input-underline !w-16 !py-1 !text-sm text-center [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
        />
      </div>
    </div>
  );
};

export default AdminPagination;
