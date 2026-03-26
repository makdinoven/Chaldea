import React, { useCallback, useEffect, useRef, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import toast from 'react-hot-toast';
import axios from 'axios';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  selectContextMenu,
  closeContextMenu,
  equipItem,
  unequipItem,
  useItem,
  useBuffItem,
  dropItem,
  learnRecipeFromItem,
  identifyItem,
  fetchInventory,
  openItemDetailModal,
  InventoryItem,
} from '../../../redux/slices/profileSlice';
import { BASE_URL } from '../../../api/api';
import { EQUIPMENT_TYPES } from '../constants';
import ConfirmationModal from '../../ui/ConfirmationModal';
import RepairModal from './RepairModal';

interface ItemContextMenuProps {
  characterId: number;
}

interface MenuAction {
  label: string;
  handler: () => void;
}

const ItemContextMenu = ({ characterId }: ItemContextMenuProps) => {
  const dispatch = useAppDispatch();
  const contextMenu = useAppSelector(selectContextMenu);
  const currentLocation = useAppSelector(state => state.user.character?.current_location);
  const menuRef = useRef<HTMLDivElement>(null);

  // Confirmation modal state for drop actions
  const [confirmModal, setConfirmModal] = useState<{
    isOpen: boolean;
    message: string;
    onConfirm: () => void;
  }>({ isOpen: false, message: '', onConfirm: () => {} });

  // Repair modal state
  const [repairModal, setRepairModal] = useState<{
    isOpen: boolean;
    inventoryItem: InventoryItem | null;
    source: string;
  }>({ isOpen: false, inventoryItem: null, source: 'inventory' });

  // Close on click outside
  useEffect(() => {
    if (!contextMenu.isOpen) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        dispatch(closeContextMenu());
      }
    };

    // Delay listener to avoid immediate close from the opening click
    const timer = setTimeout(() => {
      document.addEventListener('mousedown', handleClickOutside);
    }, 0);

    return () => {
      clearTimeout(timer);
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [contextMenu.isOpen, dispatch]);

  const handleAction = async (
    actionFn: () => Promise<unknown>,
    successMsg: string,
  ) => {
    dispatch(closeContextMenu());
    try {
      const result = await actionFn() as { meta?: { requestStatus?: string }; payload?: string };
      if (result?.meta?.requestStatus === 'rejected') {
        toast.error(result.payload ?? 'Произошла ошибка');
      } else {
        toast.success(successMsg);
      }
    } catch {
      toast.error('Произошла ошибка');
    }
  };

  const getActions = (inventoryItem: InventoryItem): MenuAction[] => {
    const { item } = inventoryItem;
    const itemType = item.item_type;
    const actions: MenuAction[] = [];

    // Описание — open item detail modal
    actions.push({
      label: 'Описание',
      handler: () => {
        dispatch(closeContextMenu());
        dispatch(openItemDetailModal({
          inventoryItem,
          slotType: contextMenu.slotType,
        }));
      },
    });

    // Опознать — only for unidentified items not in equipment
    if (!contextMenu.slotType && inventoryItem.is_identified === false) {
      actions.push({
        label: 'Опознать',
        handler: () => {
          dispatch(closeContextMenu());
          setConfirmModal({
            isOpen: true,
            message: `Опознать "${item.name}"? Будет израсходован подходящий свиток идентификации.`,
            onConfirm: () => {
              setConfirmModal((prev) => ({ ...prev, isOpen: false }));
              handleAction(
                () =>
                  dispatch(
                    identifyItem({
                      characterId,
                      inventoryItemId: inventoryItem.id,
                    }),
                  ),
                'Предмет опознан!',
              );
            },
          });
        },
      });
    }

    // Починить — for items with durability that need repair
    const maxDurability = item.max_durability ?? 0;
    const currentDurability = inventoryItem.current_durability;
    const effectiveDurability = currentDurability ?? maxDurability;
    if (maxDurability > 0 && effectiveDurability < maxDurability) {
      actions.push({
        label: 'Починить',
        handler: () => {
          dispatch(closeContextMenu());
          const source = contextMenu.slotType ? 'equipment' : 'inventory';
          setRepairModal({
            isOpen: true,
            inventoryItem,
            source,
          });
        },
      });
    }

    // Снять — only when opened from an equipment/fast slot
    if (contextMenu.slotType) {
      actions.push({
        label: 'Снять',
        handler: () =>
          handleAction(
            () => dispatch(unequipItem({ characterId, slotType: contextMenu.slotType! })),
            'Предмет снят',
          ),
      });
    }

    // Надеть — only for equipment types and only when NOT already equipped
    if (!contextMenu.slotType && EQUIPMENT_TYPES.has(itemType)) {
      actions.push({
        label: 'Надеть',
        handler: () =>
          handleAction(
            () => dispatch(equipItem({ characterId, itemId: item.id, inventoryItemId: inventoryItem.id })),
            'Предмет экипирован',
          ),
      });
    }

    // Использовать — for buff items (books etc.) or regular consumables
    if (itemType === 'consumable') {
      if (item.buff_type && item.buff_value != null && item.buff_duration_minutes != null) {
        // Buff item — use dedicated buff endpoint
        actions.push({
          label: 'Использовать',
          handler: () => {
            dispatch(closeContextMenu());
            (async () => {
              try {
                const result = await dispatch(
                  useBuffItem({ characterId, inventoryItemId: inventoryItem.id }),
                );
                if (result.meta.requestStatus === 'rejected') {
                  toast.error((result.payload as string) ?? 'Произошла ошибка');
                } else {
                  const data = result.payload as { message?: string };
                  toast.success(data?.message ?? 'Бафф активирован');
                }
              } catch {
                toast.error('Произошла ошибка');
              }
            })();
          },
        });
      } else {
        // Regular consumable
        actions.push({
          label: 'Использовать',
          handler: () =>
            handleAction(
              () =>
                dispatch(
                  useItem({ characterId, itemId: item.id, quantity: 1 }),
                ),
              'Предмет использован',
            ),
        });
      }
    }

    // Изучить — only for recipe items
    if (itemType === 'recipe' && item.blueprint_recipe_id) {
      actions.push({
        label: 'Изучить',
        handler: () =>
          handleAction(
            () =>
              dispatch(
                learnRecipeFromItem({
                  characterId,
                  recipeId: item.blueprint_recipe_id!,
                }),
              ),
            'Рецепт изучен',
          ),
      });
    }

    // Выбросить — drop 1 (with confirmation)
    actions.push({
      label: 'Выбросить',
      handler: () => {
        dispatch(closeContextMenu());
        setConfirmModal({
          isOpen: true,
          message: `Предмет "${item.name}" (x1) будет выброшен.`,
          onConfirm: () => {
            setConfirmModal((prev) => ({ ...prev, isOpen: false }));
            handleAction(
              () =>
                dispatch(
                  dropItem({ characterId, itemId: item.id, quantity: 1 }),
                ),
              'Предмет выброшен',
            );
          },
        });
      },
    });

    // Удалить — drop all (with confirmation)
    if (inventoryItem.quantity > 1) {
      actions.push({
        label: 'Удалить',
        handler: () => {
          dispatch(closeContextMenu());
          setConfirmModal({
            isOpen: true,
            message: `Все предметы "${item.name}" (x${inventoryItem.quantity}) будут выброшены.`,
            onConfirm: () => {
              setConfirmModal((prev) => ({ ...prev, isOpen: false }));
              handleAction(
                () =>
                  dispatch(
                    dropItem({
                      characterId,
                      itemId: item.id,
                      quantity: inventoryItem.quantity,
                    }),
                  ),
                'Предметы удалены',
              );
            },
          });
        },
      });
    }

    // Бросить на локацию — only when character has a current location
    if (currentLocation) {
      actions.push({
        label: 'Бросить на локацию',
        handler: () => {
          dispatch(closeContextMenu());
          setConfirmModal({
            isOpen: true,
            message: `Бросить "${item.name}" (x1) на локацию "${currentLocation.name}"?`,
            onConfirm: async () => {
              setConfirmModal((prev) => ({ ...prev, isOpen: false }));
              try {
                await axios.post(
                  `${BASE_URL}/locations/${currentLocation.id}/loot/drop`,
                  {
                    character_id: characterId,
                    item_id: item.id,
                    quantity: 1,
                  }
                );
                toast.success('Предмет брошен на локацию');
                dispatch(fetchInventory(characterId));
              } catch (err) {
                const message =
                  axios.isAxiosError(err) && err.response?.data?.detail
                    ? err.response.data.detail
                    : 'Не удалось бросить предмет на локацию';
                toast.error(message);
              }
            },
          });
        },
      });
    }

    // Продать — placeholder for future
    actions.push({
      label: 'Продать',
      handler: () => {
        dispatch(closeContextMenu());
        toast('Продажа скоро будет доступна');
      },
    });

    return actions;
  };

  // Use callback ref to avoid "ref is not a prop" warning with motion components
  const setMenuRef = useCallback((node: HTMLDivElement | null) => {
    (menuRef as React.MutableRefObject<HTMLDivElement | null>).current = node;
  }, []);

  const closeConfirmModal = () => {
    setConfirmModal((prev) => ({ ...prev, isOpen: false }));
  };

  return (
    <>
      <AnimatePresence>
        {contextMenu.isOpen && contextMenu.item && (
          <motion.div
            key="item-context-menu"
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.95 }}
            transition={{ duration: 0.15 }}
            className="context-menu"
            style={{
              position: 'fixed',
              top: contextMenu.y,
              left: contextMenu.x,
              zIndex: 100,
            }}
          >
            <div ref={setMenuRef}>
              <div className="px-3 py-1.5 mb-1">
                <span className="gold-text text-sm font-medium">
                  {contextMenu.item.item.name}
                </span>
              </div>
              {getActions(contextMenu.item).map((action) => (
                <button
                  key={action.label}
                  onClick={action.handler}
                  className="dropdown-item w-full text-left"
                >
                  {action.label}
                </button>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <ConfirmationModal
        isOpen={confirmModal.isOpen}
        message={confirmModal.message}
        onConfirm={confirmModal.onConfirm}
        onCancel={closeConfirmModal}
      />

      {repairModal.isOpen && repairModal.inventoryItem && (
        <RepairModal
          isOpen={repairModal.isOpen}
          characterId={characterId}
          inventoryItem={repairModal.inventoryItem}
          source={repairModal.source}
          onClose={() => setRepairModal({ isOpen: false, inventoryItem: null, source: 'inventory' })}
        />
      )}
    </>
  );
};

export default ItemContextMenu;
