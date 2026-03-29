import { useState, useEffect, useCallback } from 'react';
import toast from 'react-hot-toast';
import { motion, AnimatePresence } from 'motion/react';
import {
  getFramesCatalog,
  getBackgroundsCatalog,
  adminDeleteFrame,
  adminDeleteBackground,
  adminGrantCosmetic,
} from '../../../api/cosmetics';
import type {
  CosmeticFrame,
  CosmeticBackground,
  CosmeticRarity,
} from '../../../types/cosmetics';
import FrameEditor from './FrameEditor';
import BackgroundEditor from './BackgroundEditor';

/* ── Dictionaries ── */

const RARITY_LABELS: Record<CosmeticRarity, string> = {
  common: 'Обычная',
  rare: 'Редкая',
  epic: 'Эпическая',
  legendary: 'Легендарная',
};

const RARITY_COLOR: Record<CosmeticRarity, string> = {
  common: 'text-white',
  rare: 'text-rarity-rare',
  epic: 'text-rarity-epic',
  legendary: 'text-rarity-legendary',
};

const TYPE_LABELS: Record<string, string> = {
  css: 'CSS',
  image: 'Изображение',
  combo: 'Комбо',
};

type Tab = 'frames' | 'backgrounds';

/* ── Component ── */

const AdminCosmeticsPage = () => {
  /* ── List state ── */
  const [tab, setTab] = useState<Tab>('frames');
  const [frames, setFrames] = useState<CosmeticFrame[]>([]);
  const [backgrounds, setBackgrounds] = useState<CosmeticBackground[]>([]);
  const [loading, setLoading] = useState(false);

  /* ── Editor state ── */
  const [editingFrame, setEditingFrame] = useState<CosmeticFrame | null>(null);
  const [creatingFrame, setCreatingFrame] = useState(false);
  const [editingBg, setEditingBg] = useState<CosmeticBackground | null>(null);
  const [creatingBg, setCreatingBg] = useState(false);

  /* ── Grant state ── */
  const [grantOpen, setGrantOpen] = useState(false);
  const [grantUserId, setGrantUserId] = useState('');
  const [grantType, setGrantType] = useState<'frame' | 'background'>('frame');
  const [grantSlug, setGrantSlug] = useState('');
  const [granting, setGranting] = useState(false);

  /* ── Data loading ── */

  const loadFrames = useCallback(() => {
    setLoading(true);
    getFramesCatalog()
      .then((res) => setFrames(res.data.items))
      .catch(() => toast.error('Не удалось загрузить рамки'))
      .finally(() => setLoading(false));
  }, []);

  const loadBackgrounds = useCallback(() => {
    setLoading(true);
    getBackgroundsCatalog()
      .then((res) => setBackgrounds(res.data.items))
      .catch(() => toast.error('Не удалось загрузить подложки'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (tab === 'frames') loadFrames();
    else loadBackgrounds();
  }, [tab, loadFrames, loadBackgrounds]);

  /* ── Delete ── */

  const handleDeleteFrame = async (id: number) => {
    if (!confirm('Удалить рамку? У пользователей с этой рамкой она будет снята.')) return;
    try {
      await adminDeleteFrame(id);
      toast.success('Рамка удалена');
      loadFrames();
    } catch {
      toast.error('Ошибка при удалении рамки');
    }
  };

  const handleDeleteBg = async (id: number) => {
    if (!confirm('Удалить подложку? У пользователей с этой подложкой она будет снята.')) return;
    try {
      await adminDeleteBackground(id);
      toast.success('Подложка удалена');
      loadBackgrounds();
    } catch {
      toast.error('Ошибка при удалении подложки');
    }
  };

  /* ── Grant ── */

  const handleGrant = async () => {
    const userId = parseInt(grantUserId, 10);
    if (!userId || userId <= 0) {
      toast.error('Укажите корректный ID пользователя');
      return;
    }
    if (!grantSlug.trim()) {
      toast.error('Выберите косметику');
      return;
    }
    setGranting(true);
    try {
      await adminGrantCosmetic({
        user_id: userId,
        cosmetic_type: grantType,
        cosmetic_slug: grantSlug,
      });
      toast.success('Косметика выдана');
      setGrantOpen(false);
      setGrantUserId('');
      setGrantSlug('');
    } catch {
      toast.error('Ошибка при выдаче косметики');
    } finally {
      setGranting(false);
    }
  };

  /* ── Editor close handlers ── */

  const closeFrameEditor = () => {
    setEditingFrame(null);
    setCreatingFrame(false);
    loadFrames();
  };

  const closeBgEditor = () => {
    setEditingBg(null);
    setCreatingBg(false);
    loadBackgrounds();
  };

  /* ── Determine what to show ── */

  const showingFrameEditor = creatingFrame || editingFrame !== null;
  const showingBgEditor = creatingBg || editingBg !== null;
  const showingEditor = showingFrameEditor || showingBgEditor;

  /* ── Cosmetic options for grant dropdown ── */
  const grantOptions = grantType === 'frame' ? frames : backgrounds;

  /* ── Render ── */

  return (
    <div className="w-full max-w-[1240px] mx-auto flex flex-col gap-6">
      <h1 className="gold-text text-3xl font-semibold uppercase tracking-[0.06em]">
        Косметика
      </h1>

      {/* Editor views */}
      {showingFrameEditor && (
        <FrameEditor
          frame={editingFrame}
          onSuccess={closeFrameEditor}
          onCancel={closeFrameEditor}
        />
      )}

      {showingBgEditor && (
        <BackgroundEditor
          background={editingBg}
          onSuccess={closeBgEditor}
          onCancel={closeBgEditor}
        />
      )}

      {/* Main list view (hidden when editor is open) */}
      {!showingEditor && (
        <>
          {/* Tabs */}
          <div className="flex gap-4">
            <button
              onClick={() => setTab('frames')}
              className={`text-base font-medium uppercase tracking-[0.06em] pb-1 transition-colors duration-200 ${
                tab === 'frames'
                  ? 'text-white border-b-2 border-white'
                  : 'text-white/40 hover:text-site-blue'
              }`}
            >
              Рамки
            </button>
            <button
              onClick={() => setTab('backgrounds')}
              className={`text-base font-medium uppercase tracking-[0.06em] pb-1 transition-colors duration-200 ${
                tab === 'backgrounds'
                  ? 'text-white border-b-2 border-white'
                  : 'text-white/40 hover:text-site-blue'
              }`}
            >
              Подложки
            </button>
          </div>

          {/* Toolbar */}
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <span className="text-white/50 text-sm">
              {tab === 'frames'
                ? `Всего рамок: ${frames.length}`
                : `Всего подложек: ${backgrounds.length}`}
            </span>
            <div className="flex gap-3 flex-wrap">
              <button
                className="btn-blue !text-base !px-5 !py-2 whitespace-nowrap"
                onClick={() => setGrantOpen(true)}
              >
                Выдать косметику
              </button>
              <button
                className="btn-blue !text-base !px-5 !py-2 whitespace-nowrap"
                onClick={() =>
                  tab === 'frames' ? setCreatingFrame(true) : setCreatingBg(true)
                }
              >
                {tab === 'frames' ? 'Создать рамку' : 'Создать подложку'}
              </button>
            </div>
          </div>

          {/* Loading */}
          {loading && (
            <p className="text-white/50 text-sm py-4">Загрузка...</p>
          )}

          {/* Frames table */}
          {tab === 'frames' && !loading && (
            <div className="gray-bg overflow-x-auto">
              <table className="w-full min-w-[780px]">
                <thead>
                  <tr className="border-b border-white/10">
                    {['ID', 'Название', 'Slug', 'Тип', 'Редкость', 'Превью', 'По умолч.', 'Действия'].map(
                      (h, i) => (
                        <th
                          key={h}
                          className={`text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3 ${
                            i === 7 ? 'text-right' : 'text-left'
                          }`}
                        >
                          {h}
                        </th>
                      ),
                    )}
                  </tr>
                </thead>
                <motion.tbody
                  initial="hidden"
                  animate="visible"
                  variants={{
                    hidden: {},
                    visible: { transition: { staggerChildren: 0.03 } },
                  }}
                >
                  {frames.map((f) => (
                    <motion.tr
                      key={f.id}
                      variants={{
                        hidden: { opacity: 0, y: 6 },
                        visible: { opacity: 1, y: 0 },
                      }}
                      className="border-b border-white/5 hover:bg-white/[0.05] transition-colors duration-200"
                    >
                      <td className="px-4 py-3 text-sm text-white/70">{f.id}</td>
                      <td className={`px-4 py-3 text-sm ${RARITY_COLOR[f.rarity]}`}>
                        {f.name}
                      </td>
                      <td className="px-4 py-3 text-sm text-white/50 font-mono">
                        {f.slug}
                      </td>
                      <td className="px-4 py-3 text-sm text-white/70">
                        {TYPE_LABELS[f.type] ?? f.type}
                      </td>
                      <td className="px-4 py-3 text-sm text-white/70">
                        {RARITY_LABELS[f.rarity]}
                      </td>
                      <td className="px-4 py-3">
                        <div className={`relative w-10 h-10 rounded-full ${f.css_class || ''}`}>
                          <div className="w-full h-full rounded-full bg-white/10" />
                          {f.image_url && (
                            <img
                              src={f.image_url}
                              alt=""
                              className="absolute inset-0 w-full h-full object-contain pointer-events-none"
                            />
                          )}
                        </div>
                      </td>
                      <td className="px-4 py-3 text-sm">
                        {f.is_default ? (
                          <span className="text-green-400">Да</span>
                        ) : (
                          <span className="text-white/40">Нет</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-col items-end gap-1.5">
                          <button
                            onClick={() => setEditingFrame(f)}
                            className="text-sm text-white hover:text-site-blue transition-colors duration-200"
                          >
                            Редактировать
                          </button>
                          <button
                            onClick={() => handleDeleteFrame(f.id)}
                            className="text-sm text-site-red hover:text-white transition-colors duration-200"
                          >
                            Удалить
                          </button>
                        </div>
                      </td>
                    </motion.tr>
                  ))}
                </motion.tbody>
              </table>

              {frames.length === 0 && (
                <p className="text-center text-white/50 text-sm py-8">
                  Рамки не найдены
                </p>
              )}
            </div>
          )}

          {/* Backgrounds table */}
          {tab === 'backgrounds' && !loading && (
            <div className="gray-bg overflow-x-auto">
              <table className="w-full min-w-[700px]">
                <thead>
                  <tr className="border-b border-white/10">
                    {['ID', 'Название', 'Slug', 'Тип', 'Редкость', 'По умолч.', 'Действия'].map(
                      (h, i) => (
                        <th
                          key={h}
                          className={`text-xs font-medium uppercase tracking-[0.06em] text-white/50 px-4 py-3 ${
                            i === 6 ? 'text-right' : 'text-left'
                          }`}
                        >
                          {h}
                        </th>
                      ),
                    )}
                  </tr>
                </thead>
                <motion.tbody
                  initial="hidden"
                  animate="visible"
                  variants={{
                    hidden: {},
                    visible: { transition: { staggerChildren: 0.03 } },
                  }}
                >
                  {backgrounds.map((bg) => (
                    <motion.tr
                      key={bg.id}
                      variants={{
                        hidden: { opacity: 0, y: 6 },
                        visible: { opacity: 1, y: 0 },
                      }}
                      className="border-b border-white/5 hover:bg-white/[0.05] transition-colors duration-200"
                    >
                      <td className="px-4 py-3 text-sm text-white/70">{bg.id}</td>
                      <td className={`px-4 py-3 text-sm ${RARITY_COLOR[bg.rarity]}`}>
                        {bg.name}
                      </td>
                      <td className="px-4 py-3 text-sm text-white/50 font-mono">
                        {bg.slug}
                      </td>
                      <td className="px-4 py-3 text-sm text-white/70">
                        {TYPE_LABELS[bg.type] ?? bg.type}
                      </td>
                      <td className="px-4 py-3 text-sm text-white/70">
                        {RARITY_LABELS[bg.rarity]}
                      </td>
                      <td className="px-4 py-3 text-sm">
                        {bg.is_default ? (
                          <span className="text-green-400">Да</span>
                        ) : (
                          <span className="text-white/40">Нет</span>
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-col items-end gap-1.5">
                          <button
                            onClick={() => setEditingBg(bg)}
                            className="text-sm text-white hover:text-site-blue transition-colors duration-200"
                          >
                            Редактировать
                          </button>
                          <button
                            onClick={() => handleDeleteBg(bg.id)}
                            className="text-sm text-site-red hover:text-white transition-colors duration-200"
                          >
                            Удалить
                          </button>
                        </div>
                      </td>
                    </motion.tr>
                  ))}
                </motion.tbody>
              </table>

              {backgrounds.length === 0 && (
                <p className="text-center text-white/50 text-sm py-8">
                  Подложки не найдены
                </p>
              )}
            </div>
          )}
        </>
      )}

      {/* Grant Cosmetic Modal */}
      <AnimatePresence>
        {grantOpen && (
          <div className="modal-overlay" onClick={() => setGrantOpen(false)}>
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="modal-content gold-outline gold-outline-thick w-full max-w-[480px] flex flex-col gap-4 mx-4"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 className="gold-text text-2xl font-medium uppercase tracking-[0.06em]">
                Выдать косметику
              </h2>

              {/* User ID */}
              <label className="flex flex-col gap-1">
                <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                  ID пользователя
                </span>
                <input
                  type="number"
                  value={grantUserId}
                  onChange={(e) => setGrantUserId(e.target.value)}
                  className="input-underline"
                  placeholder="123"
                  min={1}
                />
              </label>

              {/* Cosmetic Type */}
              <label className="flex flex-col gap-1">
                <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                  Тип косметики
                </span>
                <select
                  value={grantType}
                  onChange={(e) => {
                    setGrantType(e.target.value as 'frame' | 'background');
                    setGrantSlug('');
                  }}
                  className="input-underline"
                >
                  <option value="frame" className="bg-site-dark text-white">
                    Рамка
                  </option>
                  <option value="background" className="bg-site-dark text-white">
                    Подложка
                  </option>
                </select>
              </label>

              {/* Cosmetic selector */}
              <label className="flex flex-col gap-1">
                <span className="text-white/50 text-xs font-medium uppercase tracking-[0.06em]">
                  Косметика
                </span>
                <select
                  value={grantSlug}
                  onChange={(e) => setGrantSlug(e.target.value)}
                  className="input-underline"
                >
                  <option value="" className="bg-site-dark text-white">
                    -- Выберите --
                  </option>
                  {grantOptions.map((c) => (
                    <option key={c.slug} value={c.slug} className="bg-site-dark text-white">
                      {c.name} ({c.slug})
                    </option>
                  ))}
                </select>
              </label>

              {/* Buttons */}
              <div className="flex justify-end gap-4 pt-2">
                <button
                  className="btn-blue !text-base !px-6 !py-2"
                  onClick={handleGrant}
                  disabled={granting || !grantUserId || !grantSlug}
                >
                  {granting ? 'Выдача...' : 'Выдать'}
                </button>
                <button
                  className="btn-line !w-auto !px-6"
                  onClick={() => setGrantOpen(false)}
                >
                  Отмена
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </div>
  );
};

export default AdminCosmeticsPage;
