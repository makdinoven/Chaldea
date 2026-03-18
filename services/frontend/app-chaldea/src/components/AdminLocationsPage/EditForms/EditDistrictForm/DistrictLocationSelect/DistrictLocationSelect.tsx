import { useState } from 'react';
import { useSelector } from 'react-redux';
import type { RootState } from '../../../../../redux/store';

interface LocationOption {
  id: number;
  name: string;
}

interface DistrictLocationSelectProps {
  name: string;
  value: string | number | null;
  onChange: (value: number | string) => void;
  placeholder?: string;
}

const DistrictLocationSelect = ({ name, value, onChange, placeholder }: DistrictLocationSelectProps) => {
  const districtLocations = useSelector(
    (state: RootState) => (state.districtEdit as { districtLocations?: LocationOption[] }).districtLocations
  ) || [];

  const [searchTerm, setSearchTerm] = useState('');

  const filteredLocations = districtLocations.filter((location) =>
    location.name.toLowerCase().includes(searchTerm.toLowerCase())
  );

  return (
    <div className="flex flex-col gap-2">
      <input
        type="text"
        className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] text-sm transition-colors focus:border-site-blue/50 focus:outline-none"
        placeholder="Поиск локации..."
        value={searchTerm}
        onChange={(e) => setSearchTerm(e.target.value)}
      />

      <select
        name={name}
        value={value || ''}
        onChange={(e) => onChange(e.target.value ? Number(e.target.value) : '')}
        className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] text-sm transition-colors focus:border-site-blue/50 focus:outline-none"
      >
        <option value="">{placeholder || 'Выберите локацию'}</option>
        {filteredLocations.map((location) => (
          <option key={location.id} value={location.id}>
            {location.name}
          </option>
        ))}
      </select>
    </div>
  );
};

export default DistrictLocationSelect;
