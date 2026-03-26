import React, { useEffect, useState } from 'react';
import { useDispatch, useSelector } from 'react-redux';
import toast from 'react-hot-toast';
import { fetchAllLocations, removeNeighbor } from '../../../../../redux/actions/locationEditActions';
import { selectLocationEdit } from '../../../../../redux/selectors/locationSelectors';
import LocationSearch from '../../../../CommonComponents/LocationSearch/LocationSearch';

interface Neighbor {
  neighbor_id: number;
  energy_cost: number;
}

interface LocationItem {
  id: number;
  name: string;
}

interface LocationEditState {
  allLocations: LocationItem[];
}

interface FormData {
  id: number | 'new';
}

interface LocationNeighborsEditorProps {
  formData: FormData;
  neighbors: Neighbor[];
  onAdd?: (neighbor: Neighbor) => void;
  onRemove?: (neighborId: number) => void;
  canDeleteImmediately?: boolean;
}

const LocationNeighborsEditor = ({
  formData,
  neighbors,
  onAdd,
  onRemove,
  canDeleteImmediately = true,
}: LocationNeighborsEditorProps) => {
  const dispatch = useDispatch();
  const { allLocations } = useSelector(selectLocationEdit) as LocationEditState;

  const [selectedNeighbor, setSelectedNeighbor] = useState('');
  const [energyCost, setEnergyCost] = useState(1);
  const [neighborsList, setNeighborsList] = useState<LocationItem[]>([]);

  useEffect(() => {
    dispatch(fetchAllLocations() as unknown as any);
  }, [dispatch]);

  useEffect(() => {
    if (allLocations && allLocations.length > 0) {
      setNeighborsList(allLocations.filter((loc) => loc.id !== formData.id));
    }
  }, [allLocations, formData.id]);

  const getLocationName = (locationId: number): string => {
    const found = allLocations.find((loc) => loc.id === locationId);
    return found ? found.name : `Локация #${locationId}`;
  };

  const handleAddNeighbor = () => {
    if (!selectedNeighbor) return;
    const neighborId = parseInt(selectedNeighbor);

    if (neighbors.some((n) => n.neighbor_id === neighborId)) {
      toast.error('Сосед уже есть');
      return;
    }
    const newNeighbor: Neighbor = {
      neighbor_id: neighborId,
      energy_cost: energyCost,
    };

    onAdd?.(newNeighbor);

    setSelectedNeighbor('');
    setEnergyCost(1);
  };

  const handleRemoveNeighbor = async (neighborId: number) => {
    if (canDeleteImmediately && formData.id !== 'new') {
      await dispatch(
        removeNeighbor({ locationId: formData.id, neighborId }) as unknown as any
      );
    }
    onRemove?.(neighborId);
  };

  return (
    <div className="mt-4 w-full">
      <div className="flex items-center mb-4 gap-2.5 flex-wrap">
        <div className="flex-1 min-w-[250px]">
          <LocationSearch
            name="neighbor_id"
            value={selectedNeighbor}
            onChange={(e: React.ChangeEvent<HTMLSelectElement>) =>
              setSelectedNeighbor(e.target.value)
            }
            locations={neighborsList}
            placeholder="Выберите соседнюю локацию"
            className="w-full"
          />
        </div>

        <div className="w-[100px]">
          <input
            type="number"
            min="1"
            value={energyCost}
            onChange={(e) => setEnergyCost(parseInt(e.target.value) || 1)}
            placeholder="Энергия"
            className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] text-sm transition-colors focus:border-blue-500/50 focus:outline-none"
          />
        </div>

        <button
          type="button"
          onClick={handleAddNeighbor}
          disabled={!selectedNeighbor}
          className="px-4 py-2 bg-blue-500/20 text-white border-none rounded cursor-pointer font-medium transition-colors hover:bg-blue-500/30 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          Добавить
        </button>
      </div>

      <div className="mt-4 border border-white/10 rounded p-2.5 bg-black/20 max-h-[300px] overflow-y-auto gold-scrollbar">
        {neighbors.length > 0 ? (
          neighbors.map((n) => (
            <div
              key={n.neighbor_id}
              className="flex justify-between items-center p-2.5 mb-2 bg-black/30 border border-white/10 rounded"
            >
              <span className="font-medium flex-1 text-[#8ab3d5]">
                {getLocationName(n.neighbor_id)}
              </span>
              <span className="mx-4 text-[#a8c6df]">
                Энергия: {n.energy_cost}
              </span>
              <button
                type="button"
                className="px-2.5 py-1.5 bg-red-500/20 text-white border-none rounded cursor-pointer transition-colors hover:bg-red-500/30"
                onClick={() => handleRemoveNeighbor(n.neighbor_id)}
              >
                Удалить
              </button>
            </div>
          ))
        ) : (
          <div className="text-center text-[#8ab3d5] py-5">
            Нет соседних локаций
          </div>
        )}
      </div>
    </div>
  );
};

export default LocationNeighborsEditor;
