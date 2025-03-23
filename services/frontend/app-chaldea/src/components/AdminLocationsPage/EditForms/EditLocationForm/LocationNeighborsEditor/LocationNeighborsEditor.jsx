import React, { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';

// Экшены для получения всех локаций и удаления соседей
import { fetchAllLocations, removeNeighbor } from '../../../../../redux/actions/locationEditActions';
import { selectLocationEdit } from '../../../../../redux/selectors/locationSelectors';

import LocationSearch from '../../../../CommonComponents/LocationSearch/LocationSearch';
import s from './LocationNeighborsEditor.module.scss';

/**
 * Компонент для отображения и редактирования соседних локаций.
 *
 * @param {object} props
 * @param {object} props.formData - Данные текущей локации (минимум id).
 * @param {Array} props.neighbors - Изначальный список соседей ([{ neighbor_id, energy_cost }, ...]).
 * @param {function} [props.onAdd] - Колбэк, вызываемый при добавлении соседа (не обязательно).
 */
const LocationNeighborsEditor = ({
  formData,
  neighbors = [],
  onAdd
}) => {
  const dispatch = useDispatch();
  const { allLocations } = useSelector(selectLocationEdit);

  // ------------------------------------------
  // Локальный стейт для "всех соседей" в UI
  // ------------------------------------------
  const [localNeighbors, setLocalNeighbors] = useState(neighbors);

  // ------------------------------------------
  // Стейт для формы добавления соседа
  // ------------------------------------------
  const [selectedNeighbor, setSelectedNeighbor] = useState('');
  const [energyCost, setEnergyCost] = useState(1);
  const [neighborsList, setNeighborsList] = useState([]); // Все локации минус текущая

  // 1) При первом рендере загружаем список всех локаций
  useEffect(() => {
    dispatch(fetchAllLocations());
  }, [dispatch]);

  // 2) Когда приходят/обновляются пропсы neighbors, синхронизируем
  useEffect(() => {
    setLocalNeighbors(neighbors);
  }, [neighbors]);

  // 3) Когда получаем allLocations, формируем список
  //    возможных "кандидатов" в соседи (не включая саму себя)
  useEffect(() => {
    if (allLocations && allLocations.length > 0) {
      setNeighborsList(allLocations.filter(loc => loc.id !== formData.id));
    }
  }, [allLocations, formData.id]);

  // ------------------------------------------
  // Вспомогательная функция
  // ------------------------------------------
  const getLocationName = (locationId) => {
    const location = allLocations.find(loc => loc.id === parseInt(locationId));
    return location ? location.name : `Локация #${locationId}`;
  };

  // ------------------------------------------
  // Обработчики
  // ------------------------------------------
  const handleNeighborSelect = (eOrValue) => {
    let value;
    if (eOrValue && eOrValue.target) {
      value = eOrValue.target.value;
    } else {
      value = eOrValue;
    }
    setSelectedNeighbor(value);
  };

  const handleEnergyCostChange = (e) => {
    setEnergyCost(parseInt(e.target.value) || 1);
  };

  // Добавляем соседа:
  // - Если у вас уже есть колбэк onAdd (который, например, делает POST /neighbors/),
  //   используем его. Если нет, можно самостоятельно диспатчить экшен addNeighbor.
  const handleAddNeighbor = async () => {
    if (!selectedNeighbor) return;
    const neighborIdInt = parseInt(selectedNeighbor);

    // Проверяем, нет ли уже такого соседа
    const alreadyExists = localNeighbors.some(
      n => n.neighbor_id === neighborIdInt
    );
    if (alreadyExists) {
      alert('Такой сосед уже существует!');
      return;
    }

    // Если проп onAdd передан, вызовем его
    if (onAdd) {
      await onAdd({
        neighbor_id: neighborIdInt,
        energy_cost: energyCost
      });
    }

    // Локально добавляем его в список
    const newNeighbor = {
      neighbor_id: neighborIdInt,
      energy_cost: energyCost
    };
    setLocalNeighbors(prev => [...prev, newNeighbor]);

    // Сброс полей
    setSelectedNeighbor('');
    setEnergyCost(1);
  };

  // Удаляем соседа через Thunk removeNeighbor,
  // а затем локально вырезаем его из массива
  const handleRemoveNeighbor = async (neighborId) => {
    if (!window.confirm(`Удалить соседа #${neighborId}?`)) {
      return;
    }
    try {
      // 1) Вызываем DELETE /locations/{formData.id}/neighbors/{neighborId} на бэкенде
      await dispatch(removeNeighbor({ locationId: formData.id, neighborId }));

      // 2) Мгновенно убираем из localNeighbors (UI‑списка)
      setLocalNeighbors(prev => prev.filter(n => n.neighbor_id !== neighborId));
    } catch (err) {
      console.error('Ошибка при удалении соседа:', err);
    }
  };

  // ------------------------------------------
  // Render
  // ------------------------------------------
  return (
    <div className={s.neighbors_editor}>
      {/* Форма добавления соседа */}
      <div className={s.add_neighbor}>
        <div className={s.neighbor_search_container}>
          <LocationSearch
            name="neighbor_id"
            value={selectedNeighbor}
            onChange={handleNeighborSelect}
            locations={neighborsList}
            placeholder="Выберите соседнюю локацию"
            className={s.neighbor_search}
          />
        </div>

        <div className={s.energy_container}>
          <input
            type="number"
            min="1"
            value={energyCost}
            onChange={handleEnergyCostChange}
            placeholder="Энергия"
            className={s.energy_input}
          />
        </div>

        <button
          type="button"
          onClick={handleAddNeighbor}
          disabled={!selectedNeighbor}
          className={s.add_button}
        >
          Добавить
        </button>
      </div>

      {/* Список текущих соседей */}
      <div className={s.neighbors_list}>
        {localNeighbors.length > 0 ? (
          localNeighbors.map((neighbor) => (
            <div key={neighbor.neighbor_id} className={s.neighbor_item}>
              <span className={s.location_name}>
                {getLocationName(neighbor.neighbor_id)}
              </span>
              <span className={s.energy_cost}>
                Энергия: {neighbor.energy_cost}
              </span>
              <button
                type="button"
                className={s.remove_button}
                onClick={() => handleRemoveNeighbor(neighbor.neighbor_id)}
              >
                Удалить
              </button>
            </div>
          ))
        ) : (
          <div className={s.no_neighbors}>Нет соседних локаций</div>
        )}
      </div>
    </div>
  );
};

export default LocationNeighborsEditor;
