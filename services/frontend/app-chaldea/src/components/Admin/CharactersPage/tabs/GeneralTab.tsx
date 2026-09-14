import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import { useAppDispatch, useAppSelector } from '../../../../redux/store';
import axios from 'axios';
import toast from 'react-hot-toast';
import {
  updateAdminCharacter,
  unlinkAdminCharacter,
  deleteAdminCharacter,
  moveAdminCharacter,
  setSelectedCharacter,
} from '../../../../redux/slices/adminCharactersSlice';
import { lookupLocations } from '../../../../api/adminCharacters';
import { CLASS_NAMES } from '../../../ProfilePage/constants';
import { selectRaceNamesMap } from '../../../../redux/slices/profileSlice';
import { selectPermissions } from '../../../../redux/slices/userSlice';
import { hasPermission } from '../../../../utils/permissions';
import useDebounce from '../../../../hooks/useDebounce';
import type { AdminCharacterListItem, LocationOption } from '../types';

interface GeneralTabProps {
  character: AdminCharacterListItem;
}

const GeneralTab = ({ character }: GeneralTabProps) => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const raceNamesMap = useAppSelector(selectRaceNamesMap);
  const permissions = useAppSelector(selectPermissions);
  const canTeleport = hasPermission(permissions, 'characters:teleport');

  const [level, setLevel] = useState(character.level);
  const [statPoints, setStatPoints] = useState(character.stat_points);
  const [currencyBalance, setCurrencyBalance] = useState(character.currency_balance);
  const [saving, setSaving] = useState(false);

  // Modal state
  const [showUnlinkModal, setShowUnlinkModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showResetTreeModal, setShowResetTreeModal] = useState(false);
  const [resettingTree, setResettingTree] = useState(false);

  // --- Перенос персонажа ---
  const [currentLocationName, setCurrentLocationName] = useState<string | null>(null);
  const [locationQuery, setLocationQuery] = useState('');
  const debouncedLocationQuery = useDebounce(locationQuery, 300) as string;
  const [locationResults, setLocationResults] = useState<LocationOption[]>([]);
  const [locationSearchLoading, setLocationSearchLoading] = useState(false);
  const [locationSearchError, setLocationSearchError] = useState<string | null>(null);
  const [destination, setDestination] = useState<LocationOption | null>(null);
  const [showMoveModal, setShowMoveModal] = useState(false);
  const [moving, setMoving] = useState(false);

  const currentLocationId = character.current_location_id;
  const isSameLocation = destination != null && destination.id === currentLocationId;

  // Название текущей локации — точечный запрос по ID (локаций более двух тысяч,
  // выгружать весь список ради одного имени незачем).
  useEffect(() => {
    if (currentLocationId == null) {
      setCurrentLocationName(null);
      return;
    }
    let cancelled = false;
    setCurrentLocationName(null);
    lookupLocations(String(currentLocationId))
      .then((list) => {
        if (cancelled) return;
        setCurrentLocationName(list.find((l) => l.id === currentLocationId)?.name ?? null);
      })
      .catch(() => {
        if (cancelled) return;
        toast.error('Не удалось загрузить название текущей локации');
      });
    return () => {
      cancelled = true;
    };
  }, [currentLocationId]);

  // Поиск локации назначения
  useEffect(() => {
    const q = debouncedLocationQuery.trim();
    if (!q) {
      setLocationResults([]);
      setLocationSearchError(null);
      setLocationSearchLoading(false);
      return;
    }
    let cancelled = false;
    setLocationSearchLoading(true);
    setLocationSearchError(null);
    lookupLocations(q)
      .then((list) => {
        if (cancelled) return;
        setLocationResults(list.slice(0, 50));
      })
      .catch(() => {
        if (cancelled) return;
        setLocationResults([]);
        setLocationSearchError('Не удалось загрузить список локаций. Попробуйте ещё раз.');
      })
      .finally(() => {
        if (!cancelled) setLocationSearchLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [debouncedLocationQuery]);

  const handleMove = async () => {
    if (!destination) return;
    setMoving(true);
    // Ошибки показывает сам thunk (toast с русским сообщением сервера),
    // поэтому здесь достаточно разобрать результат.
    const action = await dispatch(
      moveAdminCharacter({ characterId: character.id, newLocationId: destination.id }),
    );
    setMoving(false);
    if (!moveAdminCharacter.fulfilled.match(action)) {
      return; // модалку не закрываем — админ видит ошибку и может повторить
    }
    setShowMoveModal(false);
    const result = action.payload;
    if (!result.moved) {
      return; // no-op: ничего не изменилось, сообщение уже показано
    }
    dispatch(setSelectedCharacter({ ...character, current_location_id: result.to_location_id }));
    setCurrentLocationName(result.to_location_name ?? destination.name);
    setDestination(null);
    setLocationQuery('');
    setLocationResults([]);
    if (result.gathering_cancelled) {
      toast('Активная сессия сбора ресурсов отменена');
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await dispatch(
        updateAdminCharacter({
          characterId: character.id,
          update: {
            level,
            stat_points: statPoints,
            currency_balance: currencyBalance,
          },
        }),
      ).unwrap();
      // Update selected character in store with new values
      dispatch(
        setSelectedCharacter({
          ...character,
          level,
          stat_points: statPoints,
          currency_balance: currencyBalance,
        }),
      );
    } finally {
      setSaving(false);
    }
  };

  const handleUnlink = async () => {
    setShowUnlinkModal(false);
    await dispatch(unlinkAdminCharacter(character.id)).unwrap();
    dispatch(setSelectedCharacter({ ...character, user_id: null }));
  };

  const handleDelete = async () => {
    setShowDeleteModal(false);
    await dispatch(deleteAdminCharacter(character.id)).unwrap();
    navigate('/admin/characters');
  };

  const handleResetTree = async () => {
    setResettingTree(true);
    try {
      const res = await axios.post('/skills/admin/class_trees/reset_full', {
        character_id: character.id,
      });
      const data = res.data;
      toast.success(
        `Прогресс сброшен: ${data.nodes_reset} узлов, ${data.skills_removed} навыков удалено`
      );
      setShowResetTreeModal(false);
    } catch {
      toast.error('Ошибка при сбросе прогресса');
    } finally {
      setResettingTree(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="space-y-8"
    >
      {/* Read-only info */}
      <div className="gray-bg p-6">
        <h3 className="gold-text text-xl font-medium uppercase mb-4">Информация</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <span className="text-white/60 text-xs uppercase tracking-[0.06em]">Имя</span>
            <p className="text-white text-base">{character.name}</p>
          </div>
          <div>
            <span className="text-white/60 text-xs uppercase tracking-[0.06em]">Раса</span>
            <p className="text-white text-base">
              {raceNamesMap[character.id_race] ?? `#${character.id_race}`}
            </p>
          </div>
          <div>
            <span className="text-white/60 text-xs uppercase tracking-[0.06em]">Класс</span>
            <p className="text-white text-base">
              {CLASS_NAMES[character.id_class] ?? `#${character.id_class}`}
            </p>
          </div>
          <div>
            <span className="text-white/60 text-xs uppercase tracking-[0.06em]">Подраса</span>
            <p className="text-white text-base">#{character.id_subrace}</p>
          </div>
          <div>
            <span className="text-white/60 text-xs uppercase tracking-[0.06em]">Владелец</span>
            <p className="text-white text-base">
              {character.user_id != null ? `User #${character.user_id}` : 'Не привязан'}
            </p>
          </div>
          <div>
            <span className="text-white/60 text-xs uppercase tracking-[0.06em]">Локация</span>
            <p className="text-white text-base break-words">
              {currentLocationId == null
                ? 'Нет'
                : currentLocationName
                  ? `${currentLocationName} (#${currentLocationId})`
                  : `#${currentLocationId}`}
            </p>
          </div>
          {character.avatar && (
            <div className="sm:col-span-2">
              <span className="text-white/60 text-xs uppercase tracking-[0.06em]">Аватар</span>
              <div className="mt-1">
                <img
                  src={character.avatar}
                  alt={character.name}
                  className="w-20 h-20 rounded-full object-cover border border-white/20"
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Editable fields */}
      <div className="gray-bg p-6">
        <h3 className="gold-text text-xl font-medium uppercase mb-4">Редактирование</h3>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
          <div className="flex flex-col gap-1">
            <label className="text-white/60 text-xs uppercase tracking-[0.06em]">Уровень</label>
            <input
              type="number"
              className="input-underline"
              min={1}
              value={level}
              onChange={(e) => setLevel(Math.max(1, Number(e.target.value)))}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-white/60 text-xs uppercase tracking-[0.06em]">
              Очки характеристик
            </label>
            <input
              type="number"
              className="input-underline"
              min={0}
              value={statPoints}
              onChange={(e) => setStatPoints(Math.max(0, Number(e.target.value)))}
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-white/60 text-xs uppercase tracking-[0.06em]">Баланс</label>
            <input
              type="number"
              className="input-underline"
              min={0}
              value={currencyBalance}
              onChange={(e) => setCurrencyBalance(Math.max(0, Number(e.target.value)))}
            />
          </div>
        </div>

        <div className="mt-6">
          <button className="btn-blue" onClick={handleSave} disabled={saving}>
            {saving ? 'Сохранение...' : 'Сохранить'}
          </button>
        </div>
      </div>

      {/* Перенос персонажа — только для обладателей characters:teleport (админ) */}
      {canTeleport && (
        <div className="gray-bg p-6">
          <h3 className="gold-text text-xl font-medium uppercase mb-4">Перенос персонажа</h3>
          <p className="text-white/60 text-sm mb-4">
            Телепорт в обход обычных правил: соседство локаций, выносливость и кулдаун перехода
            не учитываются.
          </p>

          <div className="flex flex-col gap-4 sm:flex-row sm:items-end">
            <div className="flex flex-col gap-1 w-full sm:max-w-[320px]">
              <label
                className="text-white/60 text-xs uppercase tracking-[0.06em]"
                htmlFor="admin-move-location-search"
              >
                Локация назначения
              </label>
              <input
                id="admin-move-location-search"
                type="text"
                className="input-underline w-full"
                placeholder="Название или ID локации..."
                value={locationQuery}
                onChange={(e) => setLocationQuery(e.target.value)}
              />
            </div>
            <button
              className="btn-blue w-full sm:w-auto"
              onClick={() => setShowMoveModal(true)}
              disabled={!destination || isSameLocation || moving}
            >
              {moving ? 'Перенос...' : 'Перенести'}
            </button>
          </div>

          <div className="mt-3 min-h-[1.25rem]">
            {destination ? (
              <p className="text-white text-sm break-words">
                Выбрано:{' '}
                <span className="text-gold font-medium">{destination.name}</span>{' '}
                <span className="text-white/50">#{destination.id}</span>
              </p>
            ) : (
              <p className="text-white/40 text-sm">Локация назначения не выбрана</p>
            )}
            {isSameLocation && (
              <p className="text-site-red text-sm mt-1">
                Персонаж уже находится в этой локации.
              </p>
            )}
          </div>

          {locationSearchLoading && (
            <div className="flex items-center gap-2 text-white/50 text-sm mt-3">
              <div className="w-4 h-4 border-2 border-white/30 border-t-gold rounded-full animate-spin" />
              Поиск...
            </div>
          )}

          {locationSearchError && (
            <p className="text-site-red text-sm mt-3">{locationSearchError}</p>
          )}

          {!locationSearchLoading && !locationSearchError
            && debouncedLocationQuery.trim() !== '' && locationResults.length === 0 && (
            <p className="text-white/40 text-sm mt-3">Локации не найдены</p>
          )}

          {!locationSearchLoading && locationResults.length > 0 && (
            <div className="dropdown-menu w-full mt-3 max-h-60 overflow-y-auto gold-scrollbar">
              {locationResults.map((loc) => (
                <button
                  key={loc.id}
                  type="button"
                  onClick={() => setDestination(loc)}
                  className={`dropdown-item w-full text-left break-words ${
                    destination?.id === loc.id ? 'bg-white/[0.12]' : ''
                  }`}
                >
                  {loc.name} <span className="text-white/40">#{loc.id}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Danger zone */}
      <div className="gray-bg p-6">
        <h3 className="gold-text text-xl font-medium uppercase mb-4">Опасная зона</h3>
        <div className="flex flex-wrap gap-4">
          {character.user_id != null && (
            <button className="btn-line" onClick={() => setShowUnlinkModal(true)}>
              Отвязать от аккаунта
            </button>
          )}
          <button className="btn-line" onClick={() => setShowResetTreeModal(true)}>
            Сбросить дерево навыков
          </button>
          <button
            className="text-site-red text-sm uppercase tracking-[0.06em] font-medium hover:opacity-80 transition-opacity duration-200"
            onClick={() => setShowDeleteModal(true)}
          >
            Удалить персонажа
          </button>
        </div>
      </div>

      {/* Move confirmation modal */}
      <AnimatePresence>
        {showMoveModal && destination && (
          <div className="modal-overlay" onClick={() => !moving && setShowMoveModal(false)}>
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="modal-content gold-outline gold-outline-thick"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 className="gold-text text-2xl uppercase mb-4">Перенос персонажа</h2>
              <p className="text-white mb-4 break-words">
                Перенести персонажа <span className="text-gold font-medium">{character.name}</span>{' '}
                из{' '}
                <span className="text-gold font-medium">
                  {currentLocationId == null
                    ? '— (без локации)'
                    : currentLocationName ?? `#${currentLocationId}`}
                </span>{' '}
                в <span className="text-gold font-medium">{destination.name}</span>?
              </p>
              <p className="text-white/60 text-sm mb-2">Вместе с переносом произойдёт:</p>
              <ul className="text-white/60 text-sm mb-6 list-disc pl-5 space-y-1">
                <li>открытые намерения и заявки в старой локации будут погашены;</li>
                <li>активная сессия сбора ресурсов будет отменена (половина выносливости вернётся);</li>
                <li>кулдаун перехода будет сброшен.</li>
              </ul>
              <p className="text-white/60 text-sm mb-6">
                Персонажа в бою или в подземелье перенести нельзя — сервер откажет.
              </p>
              <div className="flex flex-col gap-4 sm:flex-row">
                <button className="btn-blue" onClick={handleMove} disabled={moving}>
                  {moving ? 'Перенос...' : 'Перенести'}
                </button>
                <button
                  className="btn-line"
                  onClick={() => setShowMoveModal(false)}
                  disabled={moving}
                >
                  Отмена
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Unlink confirmation modal */}
      <AnimatePresence>
        {showUnlinkModal && (
          <div className="modal-overlay" onClick={() => setShowUnlinkModal(false)}>
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="modal-content gold-outline gold-outline-thick"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 className="gold-text text-2xl uppercase mb-4">Подтверждение</h2>
              <p className="text-white mb-6">
                Отвязать персонажа <span className="text-gold font-medium">{character.name}</span>{' '}
                от аккаунта пользователя #{character.user_id}?
              </p>
              <div className="flex gap-4">
                <button className="btn-blue" onClick={handleUnlink}>
                  Отвязать
                </button>
                <button className="btn-line" onClick={() => setShowUnlinkModal(false)}>
                  Отмена
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Reset tree confirmation modal */}
      <AnimatePresence>
        {showResetTreeModal && (
          <div className="modal-overlay" onClick={() => setShowResetTreeModal(false)}>
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="modal-content gold-outline gold-outline-thick"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 className="gold-text text-2xl uppercase mb-4">Сброс дерева навыков</h2>
              <p className="text-white mb-2">
                Сбросить весь прогресс дерева навыков персонажа{' '}
                <span className="text-gold font-medium">{character.name}</span>?
              </p>
              <p className="text-site-red text-sm mb-6">
                Будут удалены все выбранные узлы (включая подкласс), все купленные навыки из дерева.
                Опыт не возвращается.
              </p>
              <div className="flex gap-4">
                <button
                  className="btn-blue"
                  onClick={handleResetTree}
                  disabled={resettingTree}
                >
                  {resettingTree ? 'Сброс...' : 'Подтвердить сброс'}
                </button>
                <button className="btn-line" onClick={() => setShowResetTreeModal(false)}>
                  Отмена
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      {/* Delete confirmation modal */}
      <AnimatePresence>
        {showDeleteModal && (
          <div className="modal-overlay" onClick={() => setShowDeleteModal(false)}>
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              transition={{ duration: 0.2, ease: 'easeOut' }}
              className="modal-content gold-outline gold-outline-thick"
              onClick={(e) => e.stopPropagation()}
            >
              <h2 className="gold-text text-2xl uppercase mb-4">Удаление персонажа</h2>
              <p className="text-white mb-6">
                Вы уверены, что хотите удалить персонажа{' '}
                <span className="text-gold font-medium">{character.name}</span>? Это действие
                необратимо. Будут удалены инвентарь, навыки, атрибуты и связь с аккаунтом.
              </p>
              <div className="flex gap-4">
                <button
                  className="btn-blue"
                  onClick={handleDelete}
                >
                  Удалить
                </button>
                <button className="btn-line" onClick={() => setShowDeleteModal(false)}>
                  Отмена
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default GeneralTab;
