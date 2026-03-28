import { useState, useEffect, useCallback } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { motion } from 'motion/react';
import {
  fetchArticles,
  fetchCategories,
  fetchFeaturedArticles,
  type ArchiveArticleListItem,
  type ArchiveCategoryWithCount,
} from '../../../api/archive';

const titleFont = "'MedievalSharp', 'Georgia', serif";
const bodyFont = "'Cormorant Garamond', 'Georgia', serif";

const PER_PAGE = 12;

/* ---------- Hex to RGBA helper ---------- */

const hexToRgba = (hex: string, alpha: number): string => {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
};

/* ---------- Greek letter decorative effects (inspired by Bestiary runes) ---------- */

const GREEK_LETTERS = 'ΑΒΓΔΕΖΗΘΙΚΛΜΝΞΟΠΡΣΤΥΦΧΨΩαβγδεζηθικλμνξοπρστυφχψω';

const greekWatermarks = [
  /* Row 1 */ { char: GREEK_LETTERS[0], x: '6%', y: '4%', size: '22px', rotate: -12, delay: '0s' },
  { char: GREEK_LETTERS[7], x: '24%', y: '6%', size: '18px', rotate: 20, delay: '1.5s' },
  { char: GREEK_LETTERS[14], x: '44%', y: '3%', size: '26px', rotate: -5, delay: '3s' },
  { char: GREEK_LETTERS[20], x: '67%', y: '5%', size: '20px', rotate: 15, delay: '0.8s' },
  { char: GREEK_LETTERS[23], x: '87%', y: '4%', size: '24px', rotate: -18, delay: '2.2s' },
  /* Row 2 */ { char: GREEK_LETTERS[3], x: '10%', y: '16%', size: '28px', rotate: 8, delay: '1s' },
  { char: GREEK_LETTERS[11], x: '32%', y: '18%', size: '16px', rotate: -22, delay: '2.8s' },
  { char: GREEK_LETTERS[18], x: '55%', y: '15%', size: '24px', rotate: 10, delay: '0.4s' },
  { char: GREEK_LETTERS[22], x: '78%', y: '17%', size: '20px', rotate: -15, delay: '1.7s' },
  { char: GREEK_LETTERS[5], x: '93%', y: '14%', size: '22px', rotate: 25, delay: '3.5s' },
  /* Row 3 */ { char: GREEK_LETTERS[30], x: '4%', y: '30%', size: '20px', rotate: -8, delay: '2s' },
  { char: GREEK_LETTERS[35], x: '18%', y: '32%', size: '26px', rotate: 14, delay: '0.6s' },
  { char: GREEK_LETTERS[40], x: '48%', y: '28%', size: '18px', rotate: -20, delay: '3.2s' },
  { char: GREEK_LETTERS[45], x: '72%', y: '31%', size: '24px', rotate: 6, delay: '1.3s' },
  { char: GREEK_LETTERS[2], x: '90%', y: '29%', size: '22px', rotate: -10, delay: '2.6s' },
  /* Row 4 */ { char: GREEK_LETTERS[9], x: '7%', y: '45%', size: '24px', rotate: 18, delay: '0.9s' },
  { char: GREEK_LETTERS[15], x: '28%', y: '43%', size: '20px', rotate: -14, delay: '2.4s' },
  { char: GREEK_LETTERS[21], x: '52%', y: '46%', size: '26px', rotate: 7, delay: '1.1s' },
  { char: GREEK_LETTERS[6], x: '75%', y: '44%', size: '18px', rotate: -22, delay: '3.8s' },
  { char: GREEK_LETTERS[12], x: '92%', y: '47%', size: '22px', rotate: 12, delay: '0.2s' },
  /* Row 5 */ { char: GREEK_LETTERS[36], x: '5%', y: '58%', size: '18px', rotate: -16, delay: '1.6s' },
  { char: GREEK_LETTERS[42], x: '22%', y: '60%', size: '24px', rotate: 10, delay: '2.9s' },
  { char: GREEK_LETTERS[47], x: '45%', y: '57%', size: '20px', rotate: -6, delay: '0.5s' },
  { char: GREEK_LETTERS[25], x: '68%', y: '59%', size: '26px', rotate: 20, delay: '1.9s' },
  { char: GREEK_LETTERS[31], x: '88%', y: '56%', size: '22px', rotate: -12, delay: '3.3s' },
  /* Row 6 */ { char: GREEK_LETTERS[4], x: '8%', y: '72%', size: '26px', rotate: 15, delay: '0.7s' },
  { char: GREEK_LETTERS[10], x: '30%', y: '74%', size: '18px', rotate: -18, delay: '2.1s' },
  { char: GREEK_LETTERS[16], x: '50%', y: '71%', size: '22px', rotate: 8, delay: '3.6s' },
  { char: GREEK_LETTERS[19], x: '73%', y: '73%', size: '24px', rotate: -10, delay: '1.4s' },
  { char: GREEK_LETTERS[1], x: '91%', y: '70%', size: '20px', rotate: 22, delay: '2.7s' },
  /* Row 7 */ { char: GREEK_LETTERS[37], x: '6%', y: '86%', size: '20px', rotate: -14, delay: '1.2s' },
  { char: GREEK_LETTERS[43], x: '26%', y: '88%', size: '24px', rotate: 6, delay: '0.3s' },
  { char: GREEK_LETTERS[8], x: '46%', y: '85%', size: '18px', rotate: -20, delay: '2.5s' },
  { char: GREEK_LETTERS[13], x: '70%', y: '87%', size: '26px', rotate: 16, delay: '3.1s' },
  { char: GREEK_LETTERS[17], x: '89%', y: '84%', size: '22px', rotate: -8, delay: '1.8s' },
];

const greekMarginSymbols = [
  { char: 'Α', y: '8%', side: 'left' as const, delay: '0s' },
  { char: 'Ω', y: '22%', side: 'right' as const, delay: '1.2s' },
  { char: 'Θ', y: '38%', side: 'left' as const, delay: '2.5s' },
  { char: 'Σ', y: '52%', side: 'right' as const, delay: '0.6s' },
  { char: 'Φ', y: '66%', side: 'left' as const, delay: '1.8s' },
  { char: 'Ψ', y: '78%', side: 'right' as const, delay: '3s' },
  { char: 'Δ', y: '90%', side: 'left' as const, delay: '0.3s' },
];

const GreekWatermarks = () => (
  <div className="absolute inset-0 pointer-events-none z-[2] overflow-hidden">
    {greekWatermarks.map((m, i) => (
      <span
        key={i}
        className="absolute select-none"
        style={{
          left: m.x,
          top: m.y,
          fontSize: m.size,
          fontFamily: "'Cormorant Garamond', serif",
          color: 'rgba(139,105,20,0.18)',
          transform: `rotate(${m.rotate}deg)`,
          animation: 'greek-watermark-breathe 6s ease-in-out infinite',
          animationDelay: m.delay,
        }}
      >
        {m.char}
      </span>
    ))}
    <style>{`
      @keyframes greek-watermark-breathe {
        0%, 100% { opacity: 0.3; }
        50% { opacity: 0.8; }
      }
    `}</style>
  </div>
);

const GreekMarginSymbols = () => (
  <div className="absolute inset-0 pointer-events-none z-[5] overflow-hidden">
    {greekMarginSymbols.map((r, i) => (
      <span
        key={i}
        className="absolute text-xs sm:text-sm select-none"
        style={{
          top: r.y,
          [r.side]: '8px',
          fontFamily: "'Cormorant Garamond', serif",
          color: 'rgba(139,105,20,0.1)',
          textShadow: '0 0 6px rgba(180,150,60,0.15), 0 0 12px rgba(180,150,60,0.08)',
          animation: 'greek-margin-pulse 5s ease-in-out infinite',
          animationDelay: r.delay,
        }}
      >
        {r.char}
      </span>
    ))}
    <style>{`
      @keyframes greek-margin-pulse {
        0%, 100% {
          opacity: 0.2;
          text-shadow: 0 0 3px rgba(180,150,60,0.1);
        }
        50% {
          opacity: 0.85;
          text-shadow: 0 0 10px rgba(180,150,60,0.3), 0 0 20px rgba(160,140,80,0.15);
        }
      }
    `}</style>
  </div>
);

const ArchivePage = () => {
  const [searchParams, setSearchParams] = useSearchParams();

  const [articles, setArticles] = useState<ArchiveArticleListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [categories, setCategories] = useState<ArchiveCategoryWithCount[]>([]);
  const [featured, setFeatured] = useState<ArchiveArticleListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const currentPage = Number(searchParams.get('page') || '1');
  const activeCategory = searchParams.get('category') || '';
  const searchQuery = searchParams.get('search') || '';

  const [searchInput, setSearchInput] = useState(searchQuery);

  // Load categories and featured articles once
  useEffect(() => {
    const loadInitial = async () => {
      try {
        const [cats, feat] = await Promise.all([
          fetchCategories(),
          fetchFeaturedArticles(),
        ]);
        setCategories(cats);
        setFeatured(feat);
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Неизвестная ошибка';
        setError(`Не удалось загрузить данные архива: ${message}`);
      }
    };
    loadInitial();
  }, []);

  // Load articles on filter/page change
  useEffect(() => {
    const loadArticles = async () => {
      setLoading(true);
      setError(null);
      try {
        const result = await fetchArticles({
          category_slug: activeCategory || undefined,
          search: searchQuery || undefined,
          page: currentPage,
          per_page: PER_PAGE,
        });
        setArticles(result.articles);
        setTotal(result.total);
      } catch (err) {
        const message = err instanceof Error ? err.message : 'Неизвестная ошибка';
        setError(`Не удалось загрузить статьи: ${message}`);
      } finally {
        setLoading(false);
      }
    };
    loadArticles();
  }, [activeCategory, searchQuery, currentPage]);

  const totalPages = Math.ceil(total / PER_PAGE);

  const updateParams = useCallback(
    (updates: Record<string, string>) => {
      const next = new URLSearchParams(searchParams);
      Object.entries(updates).forEach(([key, value]) => {
        if (value) {
          next.set(key, value);
        } else {
          next.delete(key);
        }
      });
      // Reset page when filters change
      if ('category' in updates || 'search' in updates) {
        next.delete('page');
      }
      setSearchParams(next);
    },
    [searchParams, setSearchParams],
  );

  const handleCategoryClick = (slug: string) => {
    updateParams({ category: slug === activeCategory ? '' : slug });
  };

  const handleSearch = () => {
    updateParams({ search: searchInput.trim() });
  };

  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      handleSearch();
    }
  };

  const handleClearSearch = () => {
    setSearchInput('');
    updateParams({ search: '' });
  };

  const formatDate = (dateStr: string) => {
    try {
      return new Date(dateStr).toLocaleDateString('ru-RU', {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      });
    } catch {
      return dateStr;
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="max-w-6xl mx-auto w-full"
    >
      {/* Full parchment wrapper */}
      <div className="relative rounded-card overflow-hidden">
        {/* Parchment background */}
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            background:
              'linear-gradient(170deg, #f5e6c8 0%, #e8d5a8 30%, #f0e0c0 60%, #e8d5a8 100%)',
          }}
        />
        <div
          className="absolute inset-0 pointer-events-none opacity-10 mix-blend-multiply"
          style={{
            backgroundImage: 'url(/textures/paper.png)',
            backgroundRepeat: 'repeat',
          }}
        />
        <div
          className="absolute inset-0 pointer-events-none"
          style={{
            boxShadow:
              'inset 0 0 40px rgba(140,110,60,0.2), inset 0 0 80px rgba(120,90,40,0.08)',
          }}
        />

        {/* Greek letter decorative effects */}
        <GreekWatermarks />
        <GreekMarginSymbols />

        <div className="relative z-[1] px-4 sm:px-8 py-8 sm:py-12">
          {/* Header */}
          <h1
            className="text-3xl sm:text-4xl md:text-5xl tracking-wide text-center mb-3"
            style={{
              fontFamily: titleFont,
              color: '#8b6914',
              textShadow: '0 1px 2px rgba(0,0,0,0.15)',
            }}
          >
            Архив
          </h1>
          <p
            className="text-center text-sm sm:text-base max-w-xl mx-auto mb-6"
            style={{
              fontFamily: bodyFont,
              color: '#5a4a2a',
              fontSize: '1.1rem',
            }}
          >
            Хранилище знаний о мире, его истории и обитателях
          </p>

          {/* Search */}
          <div className="max-w-md mx-auto flex gap-2 items-center mb-8">
            <input
              type="text"
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              onKeyDown={handleSearchKeyDown}
              placeholder="Поиск по статьям..."
              className="flex-1 bg-white/30 border border-amber-800/20 rounded-card px-4 py-2
                         text-amber-900 placeholder:text-amber-700/50 outline-none
                         focus:border-amber-700/50 transition-colors text-sm sm:text-base"
              style={{ fontFamily: bodyFont }}
            />
            {searchInput && (
              <button
                onClick={handleClearSearch}
                className="text-amber-800/60 hover:text-amber-900 transition-colors text-lg px-1"
                title="Очистить поиск"
              >
                &times;
              </button>
            )}
            <button
              onClick={handleSearch}
              className="px-4 py-2 rounded-card text-sm font-medium transition-colors
                         bg-amber-800/20 text-amber-900 hover:bg-amber-800/30"
              style={{ fontFamily: bodyFont }}
            >
              Найти
            </button>
          </div>

          {/* Categories */}
          {categories.length > 0 && (
            <div className="mb-8">
              <div className="flex flex-wrap gap-2 justify-center">
                <button
                  onClick={() => handleCategoryClick('')}
                  className={`px-3 py-1.5 rounded-full text-xs sm:text-sm font-medium transition-all duration-200
                    ${
                      !activeCategory
                        ? 'bg-amber-800/80 text-amber-100 shadow-card'
                        : 'bg-amber-800/10 text-amber-900/70 hover:bg-amber-800/20 hover:text-amber-900'
                    }`}
                >
                  Все
                </button>
                {categories.map((cat) => (
                  <button
                    key={cat.id}
                    onClick={() => handleCategoryClick(cat.slug)}
                    className={`px-3 py-1.5 rounded-full text-xs sm:text-sm font-medium transition-all duration-200
                      ${
                        activeCategory === cat.slug
                          ? 'bg-amber-800/80 text-amber-100 shadow-card'
                          : 'bg-amber-800/10 text-amber-900/70 hover:bg-amber-800/20 hover:text-amber-900'
                      }`}
                  >
                    {cat.name}
                    <span className="ml-1 opacity-60">({cat.article_count})</span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Divider */}
          <div className="border-t border-amber-800/15 mb-8" />

          {/* Error */}
          {error && (
            <div className="text-center py-8">
              <p className="text-red-800 text-sm">{error}</p>
            </div>
          )}

          {/* Featured Articles */}
          {!activeCategory && !searchQuery && featured.length > 0 && (
            <section className="mb-10">
              <h2
                className="text-xl sm:text-2xl mb-5 text-center"
                style={{
                  fontFamily: titleFont,
                  color: '#6b4f1d',
                  textShadow: '0 1px 2px rgba(0,0,0,0.1)',
                }}
              >
                Избранные статьи
              </h2>
              <motion.div
                initial="hidden"
                animate="visible"
                variants={{
                  hidden: {},
                  visible: { transition: { staggerChildren: 0.07 } },
                }}
                className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-5"
              >
                {featured.map((article) => (
                  <motion.div
                    key={article.id}
                    variants={{
                      hidden: { opacity: 0, y: 10 },
                      visible: { opacity: 1, y: 0 },
                    }}
                  >
                    <Link
                      to={`/archive/${article.slug}`}
                      className="block group relative rounded-card overflow-hidden shadow-card
                                 hover:shadow-hover transition-shadow duration-200"
                      style={{ minHeight: '220px' }}
                    >
                      {/* Background image or darker parchment fallback */}
                      {article.cover_image_url ? (
                        <img
                          src={article.cover_image_url}
                          alt={article.title}
                          className="absolute inset-0 w-full h-full object-cover"
                        />
                      ) : (
                        <div
                          className="absolute inset-0"
                          style={{
                            background:
                              'linear-gradient(150deg, #c4a870 0%, #a8905a 50%, #8a7548 100%)',
                          }}
                        />
                      )}
                      {/* Dark overlay */}
                      <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/30 to-transparent" />
                      {/* Hover overlay */}
                      <div className="absolute inset-0 bg-amber-700/0 group-hover:bg-amber-700/10 transition-colors duration-200" />

                      <div className="relative z-[1] h-full flex flex-col justify-end p-4 sm:p-5">
                        <h3
                          className="text-lg sm:text-xl font-medium mb-1 line-clamp-2"
                          style={{ fontFamily: titleFont, color: article.cover_text_color || '#FFFFFF' }}
                        >
                          {article.title}
                        </h3>
                        {article.summary && (
                          <p
                            className="text-xs sm:text-sm line-clamp-2"
                            style={{ fontFamily: bodyFont, color: hexToRgba(article.cover_text_color || '#FFFFFF', 0.7) }}
                          >
                            {article.summary}
                          </p>
                        )}
                        {article.categories.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-2">
                            {article.categories.map((cat) => (
                              <span
                                key={cat.id}
                                className="text-[10px] sm:text-xs px-2 py-0.5 rounded-full bg-white/10"
                                style={{ color: hexToRgba(article.cover_text_color || '#FFFFFF', 0.6) }}
                              >
                                {cat.name}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    </Link>
                  </motion.div>
                ))}
              </motion.div>
            </section>
          )}

          {/* Article List */}
          <section>
            {(activeCategory || searchQuery) && (
              <div className="mb-4 flex items-center gap-2 text-sm text-amber-900/50">
                {searchQuery && (
                  <span>
                    Результаты поиска: &laquo;{searchQuery}&raquo;
                  </span>
                )}
                {activeCategory && (
                  <span>
                    Категория: {categories.find((c) => c.slug === activeCategory)?.name || activeCategory}
                  </span>
                )}
                <span className="text-amber-800/30">({total})</span>
              </div>
            )}

            {loading ? (
              <div className="flex justify-center py-16">
                <div className="w-8 h-8 border-2 border-amber-700/30 border-t-amber-600 rounded-full animate-spin" />
              </div>
            ) : articles.length === 0 ? (
              <div className="text-center py-16">
                <p
                  className="text-amber-800/40 text-lg"
                  style={{ fontFamily: bodyFont }}
                >
                  Статьи не найдены
                </p>
              </div>
            ) : (
              <>
                <motion.div
                  initial="hidden"
                  animate="visible"
                  variants={{
                    hidden: {},
                    visible: { transition: { staggerChildren: 0.04 } },
                  }}
                  className="grid grid-cols-1 md:grid-cols-2 gap-3 sm:gap-4"
                >
                  {articles.map((article) => (
                    <motion.div
                      key={article.id}
                      variants={{
                        hidden: { opacity: 0, y: 8 },
                        visible: { opacity: 1, y: 0 },
                      }}
                    >
                      <Link
                        to={`/archive/${article.slug}`}
                        className="flex gap-3 sm:gap-4 p-3 sm:p-4 rounded-card
                                   bg-amber-800/[0.06] hover:bg-amber-800/[0.12]
                                   transition-colors duration-200 group"
                      >
                        {/* Thumbnail */}
                        {article.cover_image_url && (
                          <div className="w-20 h-20 sm:w-24 sm:h-24 flex-shrink-0 rounded-lg overflow-hidden">
                            <img
                              src={article.cover_image_url}
                              alt=""
                              className="w-full h-full object-cover"
                            />
                          </div>
                        )}

                        <div className="flex-1 min-w-0">
                          <h3
                            className="text-base sm:text-lg text-amber-900 group-hover:text-amber-950 transition-colors
                                       duration-200 font-medium line-clamp-1 mb-1"
                            style={{ fontFamily: titleFont }}
                          >
                            {article.title}
                          </h3>
                          {article.summary && (
                            <p
                              className="text-amber-800/60 text-xs sm:text-sm line-clamp-2 mb-2"
                              style={{ fontFamily: bodyFont }}
                            >
                              {article.summary}
                            </p>
                          )}
                          <div className="flex flex-wrap items-center gap-2">
                            {article.categories.map((cat) => (
                              <span
                                key={cat.id}
                                className="text-[10px] sm:text-xs px-2 py-0.5 rounded-full bg-amber-800/10 text-amber-800/60"
                              >
                                {cat.name}
                              </span>
                            ))}
                            <span className="text-[10px] sm:text-xs text-amber-800/30 ml-auto">
                              {formatDate(article.created_at)}
                            </span>
                          </div>
                        </div>
                      </Link>
                    </motion.div>
                  ))}
                </motion.div>

                {/* Pagination */}
                {totalPages > 1 && (
                  <div className="flex justify-center items-center gap-2 mt-8">
                    <button
                      disabled={currentPage <= 1}
                      onClick={() => updateParams({ page: String(currentPage - 1) })}
                      className="px-3 py-1.5 rounded-card text-sm text-amber-800/60
                                 hover:text-amber-900 hover:bg-amber-800/10 transition-colors
                                 disabled:opacity-30 disabled:pointer-events-none"
                    >
                      &larr; Назад
                    </button>
                    <span className="text-sm text-amber-800/40 mx-2">
                      {currentPage} / {totalPages}
                    </span>
                    <button
                      disabled={currentPage >= totalPages}
                      onClick={() => updateParams({ page: String(currentPage + 1) })}
                      className="px-3 py-1.5 rounded-card text-sm text-amber-800/60
                                 hover:text-amber-900 hover:bg-amber-800/10 transition-colors
                                 disabled:opacity-30 disabled:pointer-events-none"
                    >
                      Вперёд &rarr;
                    </button>
                  </div>
                )}
              </>
            )}
          </section>
        </div>
      </div>
    </motion.div>
  );
};

export default ArchivePage;
