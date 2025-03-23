import React, { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
// Пример: removeNeighbor — Thunk (DELETE /locations/:locId/neighbors/:neighborId)
import { fetchAllLocations, removeNeighbor } from '../../../../../redux/actions/locationEditActions';
import { selectLocationEdit } from '../../../../../redux/selectors/locationSelectors';
import LocationSearch from '../../../../CommonComponents/LocationSearch/LocationSearch';
import s from './LocationNeighborsEditor.module.scss';

const LocationNeighborsEditor = ({
  formData,           // Данные текущей локации (id, ...)
  neighbors,          // Локальный массив: [{ neighbor_id, energy_cost }, ...]
  onAdd,              // Callback при добавлении
  onRemove,           // Callback при удалении — если хотим управлять из родителя
  canDeleteImmediately = true // Можно ли сразу делать DELETE на сервер
}) => {
  const dispatch = useDispatch();
  const { allLocations } = useSelector(selectLocationEdit);

  // Локальный стейт для выбора при добавлении
  const [selectedNeighbor, setSelectedNeighbor] = useState('');
  const [energyCost, setEnergyCost] = useState(1);
  const [neighborsList, setNeighborsList] = useState([]);

  useEffect(() => {
    dispatch(fetchAllLocations());
  }, [dispatch]);

  useEffect(() => {
    if (allLocations && allLocations.length > 0) {
      setNeighborsList(allLocations.filter(loc => loc.id !== formData.id));
    }
  }, [allLocations, formData.id]);

  // Вспомогательная функция
  const getLocationName = (locationId) => {
    const found = allLocations.find(loc => loc.id === parseInt(locationId));
    return found ? found.name : `Локация #${locationId}`;
  };

  // Добавить соседа в локальный массив (и, если нужно, сразу POST на сервер)
  const handleAddNeighbor = () => {
    if (!selectedNeighbor) return;
    const neighborId = parseInt(selectedNeighbor);

    if (neighbors.some(n => n.neighbor_id === neighborId)) {
      alert('Сосед уже есть');
      return;
    }
    const newNeighbor = {
      neighbor_id: neighborId,
      energy_cost: energyCost
    };

    // Вызываем onAdd (переданный из родителя EditLocationForm)
    onAdd?.(newNeighbor);

    setSelectedNeighbor('');
    setEnergyCost(1);
  };

  // Удалить соседа (локально и с сервера)
  const handleRemoveNeighbor = async (neighborId) => {
    // Если хотим сразу удалять на сервере (DELETE /locations/:id/neighbors/:neighborId):
    if (canDeleteImmediately && formData.id !== 'new') {
      await dispatch(removeNeighbor({
        locationId: formData.id,
        neighborId
      }));
    }
    // Вызываем onRemove (чтобы родитель тоже удалил его из локального массива)
    onRemove?.(neighborId);
  };

  return (
    <div className={s.neighbors_editor}>
      <div className={s.add_neighbor}>
        <div className={s.neighbor_search_container}>
          <LocationSearch
            name="neighbor_id"
            value={selectedNeighbor}
            onChange={(e) => setSelectedNeighbor(e.target.value)}
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
            onChange={(e) => setEnergyCost(parseInt(e.target.value) || 1)}
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

      <div className={s.neighbors_list}>
        {neighbors.length > 0 ? (
          neighbors.map((n) => (
            <div key={n.neighbor_id} className={s.neighbor_item}>
              <span className={s.location_name}>
                {getLocationName(n.neighbor_id)}
              </span>
              <span className={s.energy_cost}>
                Энергия: {n.energy_cost}
              </span>
              <button
                type="button"
                className={s.remove_button}
                onClick={() => handleRemoveNeighbor(n.neighbor_id)}
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
