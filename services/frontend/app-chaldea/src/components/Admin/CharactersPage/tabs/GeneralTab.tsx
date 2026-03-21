import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { motion, AnimatePresence } from 'motion/react';
import { useAppDispatch, useAppSelector } from '../../../../redux/store';
import axios from 'axios';
import toast from 'react-hot-toast';
import {
  updateAdminCharacter,
  unlinkAdminCharacter,
  deleteAdminCharacter,
  setSelectedCharacter,
} from '../../../../redux/slices/adminCharactersSlice';
import { CLASS_NAMES } from '../../../ProfilePage/constants';
import { selectRaceNamesMap } from '../../../../redux/slices/profileSlice';
import type { AdminCharacterListItem } from '../types';

interface GeneralTabProps {
  character: AdminCharacterListItem;
}

const GeneralTab = ({ character }: GeneralTabProps) => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const raceNamesMap = useAppSelector(selectRaceNamesMap);

  const [level, setLevel] = useState(character.level);
  const [statPoints, setStatPoints] = useState(character.stat_points);
  const [currencyBalance, setCurrencyBalance] = useState(character.currency_balance);
  const [saving, setSaving] = useState(false);

  // Modal state
  const [showUnlinkModal, setShowUnlinkModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showResetTreeModal, setShowResetTreeModal] = useState(false);
  const [resettingTree, setResettingTree] = useState(false);

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
            <p className="text-white text-base">
              {character.current_location_id != null
                ? `#${character.current_location_id}`
                : 'Нет'}
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
