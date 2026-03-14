import React, { useCallback, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  selectContextMenu,
  closeContextMenu,
  equipItem,
  unequipItem,
  useItem,
  dropItem,
  InventoryItem,
} from '../../../redux/slices/profileSlice';
import { EQUIPMENT_TYPES } from '../constants';

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
  const menuRef = useRef<HTMLDivElement>(null);

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

    // Описание — placeholder for future
    actions.push({
      label: 'Описание',
      handler: () => {
        dispatch(closeContextMenu());
        toast('Описание предмета скоро будет доступно');
      },
    });

    // Надеть — only for equipment types
    if (EQUIPMENT_TYPES.has(itemType)) {
      actions.push({
        label: 'Надеть',
        handler: () =>
          handleAction(
            () => dispatch(equipItem({ characterId, itemId: item.id })),
            'Предмет экипирован',
          ),
      });
    }

    // Использовать — only for consumables
    if (itemType === 'consumable') {
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

    // Выбросить — drop 1
    actions.push({
      label: 'Выбросить',
      handler: () =>
        handleAction(
          () =>
            dispatch(
              dropItem({ characterId, itemId: item.id, quantity: 1 }),
            ),
          'Предмет выброшен',
        ),
    });

    // Удалить — drop all
    if (inventoryItem.quantity > 1) {
      actions.push({
        label: 'Удалить',
        handler: () =>
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
          ),
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

  return (
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
  );
};

export default ItemContextMenu;
