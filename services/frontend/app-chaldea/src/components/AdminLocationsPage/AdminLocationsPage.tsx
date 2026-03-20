import { useEffect, useState } from 'react';
import { useRequireAuth } from '../../hooks/useRequireAuth';
import toast from 'react-hot-toast';
import {
  fetchCountriesList,
  fetchCountryDetails,
  fetchRegionDetails,
  fetchAreasList,
  createArea,
  updateArea,
  deleteArea,
  uploadAreaMap,
} from '../../redux/actions/adminLocationsActions';
import { deleteCountry, createCountry, updateCountry } from '../../redux/actions/countryEditActions';
import { deleteRegion } from '../../redux/actions/regionEditActions';
import { deleteDistrict } from '../../redux/actions/districtEditActions';
import { deleteLocation } from '../../redux/actions/locationEditActions';
import { useAppDispatch, useAppSelector } from '../../redux/store';

import EditCountryForm from './EditForms/EditCountryForm/EditCountryForm';
import EditRegionForm from './EditForms/EditRegionForm/EditRegionForm';
import EditDistrictForm from './EditForms/EditDistrictForm/EditDistrictForm';
import EditLocationForm from './EditForms/EditLocationForm/EditLocationForm';
import AdminClickableZoneEditor from './AdminClickableZoneEditor/AdminClickableZoneEditor';
import RegionMapEditor from './RegionMapEditor/RegionMapEditor';

import type { Area } from '../../redux/actions/adminLocationsActions';

// --- Types ---

interface LocationNode {
  id: number;
  name: string;
  type: string;
  image_url?: string | null;
  marker_type?: string;
  children?: LocationNode[];
}

interface District {
  id: number;
  name: string;
  parent_district_id?: number | null;
  marker_type?: string | null;
  recommended_level?: number | null;
  image_url?: string | null;
  map_icon_url?: string | null;
  map_image_url?: string | null;
  x?: number | null;
  y?: number | null;
  locations?: LocationNode[];
}

interface Region {
  id: number;
  name: string;
  country_id: number;
}

interface Country {
  id: number;
  name: string;
  area_id?: number | null;
}

interface EditingItem {
  type: string;
  id: number | string;
  data: Record<string, unknown>;
}

interface AreaFormData {
  name: string;
  description: string;
  sort_order: number;
}

// --- Component ---

const AdminLocationsPage = () => {
  useRequireAuth();
  const dispatch = useAppDispatch();
  const { countries, countryDetails, regionDetails, areas, loading, error } = useAppSelector(
    (state) => state.adminLocations
  );

  // Local state
  const [editingCountry, setEditingCountry] = useState<Record<string, unknown> | null>(null);
  const [editingRegion, setEditingRegion] = useState<Record<string, unknown> | null>(null);
  const [editingDistrict, setEditingDistrict] = useState<Record<string, unknown> | null>(null);
  const [editingItem, setEditingItem] = useState<EditingItem | null>(null);
  const [openedAreas, setOpenedAreas] = useState<Record<number, boolean>>({});
  const [openedCountries, setOpenedCountries] = useState<Record<number, boolean>>({});
  const [openedRegions, setOpenedRegions] = useState<Record<number, boolean>>({});
  const [openedDistricts, setOpenedDistricts] = useState<Record<number, boolean>>({});

  // Area editing
  const [editingArea, setEditingArea] = useState<Area | null>(null);
  const [areaForm, setAreaForm] = useState<AreaFormData>({ name: '', description: '', sort_order: 0 });
  const [areaMapFile, setAreaMapFile] = useState<File | null>(null);
  const [isCreatingArea, setIsCreatingArea] = useState(false);
  const [editingZonesForAreaId, setEditingZonesForAreaId] = useState<number | null>(null);
  const [editingZonesForCountryId, setEditingZonesForCountryId] = useState<number | null>(null);
  const [editingMapForRegionId, setEditingMapForRegionId] = useState<number | null>(null);

  useEffect(() => {
    dispatch(fetchCountriesList());
    dispatch(fetchAreasList());
  }, [dispatch]);

  // --- Area handlers ---

  const handleAreaFormChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    const { name, value, type } = e.target;
    setAreaForm((prev) => ({
      ...prev,
      [name]: type === 'number' ? Number(value) : value,
    }));
  };

  const handleAreaMapChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files?.[0]) {
      setAreaMapFile(e.target.files[0]);
    }
  };

  const handleStartCreateArea = () => {
    setEditingArea(null);
    setAreaForm({ name: '', description: '', sort_order: 0 });
    setAreaMapFile(null);
    setIsCreatingArea(true);
  };

  const handleStartEditArea = (e: React.MouseEvent, area: Area) => {
    e.stopPropagation();
    setEditingArea(area);
    setAreaForm({
      name: area.name,
      description: area.description,
      sort_order: area.sort_order,
    });
    setAreaMapFile(null);
    setIsCreatingArea(true);
  };

  const handleSaveArea = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!areaForm.name) {
      toast.error('Укажите название области');
      return;
    }

    try {
      let areaId: number;

      if (editingArea) {
        const result = await dispatch(updateArea({ id: editingArea.id, ...areaForm })).unwrap();
        areaId = result.id;
        toast.success('Область обновлена');
      } else {
        const result = await dispatch(createArea(areaForm)).unwrap();
        areaId = result.id;
        toast.success('Область создана');
      }

      if (areaMapFile) {
        try {
          await dispatch(uploadAreaMap({ areaId, file: areaMapFile })).unwrap();
          toast.success('Карта области загружена');
        } catch {
          toast.error('Ошибка загрузки карты области');
        }
      }

      setIsCreatingArea(false);
      setEditingArea(null);
      dispatch(fetchAreasList());
    } catch {
      toast.error('Ошибка сохранения области');
    }
  };

  const handleDeleteArea = async (e: React.MouseEvent, areaId: number) => {
    e.stopPropagation();
    if (window.confirm('Вы уверены, что хотите удалить эту область?')) {
      try {
        await dispatch(deleteArea(areaId)).unwrap();
        toast.success('Область удалена');
        dispatch(fetchAreasList());
        dispatch(fetchCountriesList());
      } catch {
        toast.error('Ошибка удаления области');
      }
    }
  };

  const handleCancelAreaForm = () => {
    setIsCreatingArea(false);
    setEditingArea(null);
  };

  // --- Tree toggle handlers ---

  const toggleArea = (areaId: number) => {
    setOpenedAreas((prev) => ({ ...prev, [areaId]: !prev[areaId] }));
  };

  const toggleCountry = (countryId: number) => {
    const isOpening = !openedCountries[countryId];
    setOpenedCountries((prev) => ({ ...prev, [countryId]: isOpening }));
    if (isOpening) {
      dispatch(fetchCountryDetails(countryId));
    }
  };

  const toggleRegion = (e: React.MouseEvent, regionId: number) => {
    e.stopPropagation();
    setOpenedRegions((prev) => ({ ...prev, [regionId]: !prev[regionId] }));
    if (!regionDetails[regionId]) {
      dispatch(fetchRegionDetails(regionId));
    }
  };

  const toggleDistrict = (e: React.MouseEvent, districtId: number) => {
    e.stopPropagation();
    setOpenedDistricts((prev) => ({ ...prev, [districtId]: !prev[districtId] }));
  };

  const handleOverlayClick = (e: React.MouseEvent, closeForm: () => void) => {
    if (e.target === e.currentTarget) {
      closeForm();
    }
  };

  // --- Delete handlers ---

  const handleDeleteCountry = async (e: React.MouseEvent, countryId: number) => {
    e.stopPropagation();
    if (window.confirm('Вы уверены, что хотите удалить эту страну?')) {
      try {
        await dispatch(deleteCountry(countryId) as unknown as ReturnType<typeof deleteCountry>);
        dispatch(fetchCountriesList());
        toast.success('Страна удалена');
      } catch {
        toast.error('Ошибка удаления страны');
      }
    }
  };

  const handleDeleteRegion = async (e: React.MouseEvent, regionId: number) => {
    e.stopPropagation();
    if (window.confirm('Вы уверены, что хотите удалить этот регион?')) {
      try {
        await dispatch(deleteRegion(regionId) as unknown as ReturnType<typeof deleteRegion>);
        dispatch(fetchCountriesList());
        toast.success('Регион удалён');
      } catch {
        toast.error('Ошибка удаления региона');
      }
    }
  };

  const handleDeleteDistrict = async (e: React.MouseEvent, districtId: number) => {
    e.stopPropagation();
    if (window.confirm('Вы уверены, что хотите удалить эту зону?')) {
      try {
        await dispatch(deleteDistrict(districtId) as unknown as ReturnType<typeof deleteDistrict>);
        dispatch(fetchCountriesList());
        toast.success('Зона удалена');
      } catch {
        toast.error('Ошибка удаления зоны');
      }
    }
  };

  const handleDeleteLocation = async (e: React.MouseEvent, locationId: number) => {
    e.stopPropagation();
    if (window.confirm('Вы уверены, что хотите удалить эту локацию?')) {
      try {
        await dispatch(deleteLocation(locationId) as unknown as ReturnType<typeof deleteLocation>);
        dispatch(fetchCountriesList());
        toast.success('Локация удалена');
      } catch {
        toast.error('Ошибка удаления локации');
      }
    }
  };

  // --- Edit/Create handlers ---

  const handleEditCountry = (e: React.MouseEvent, country: Country) => {
    e.stopPropagation();
    setEditingCountry(country as unknown as Record<string, unknown>);
  };

  const handleAddNewRegion = (countryId: number) => {
    setEditingRegion({ country_id: countryId });
  };

  const handleEditRegion = (e: React.MouseEvent, region: Region) => {
    e.stopPropagation();
    setEditingRegion(region as unknown as Record<string, unknown>);
  };

  const handleAddDistrict = (e: React.MouseEvent, regionId: number) => {
    e.stopPropagation();
    setEditingDistrict({ id: 'new', initialRegionId: regionId });
  };

  const handleEditDistrict = (e: React.MouseEvent, district: District) => {
    e.stopPropagation();
    setEditingDistrict(district as unknown as Record<string, unknown>);
  };

  const handleAddLocation = (e: React.MouseEvent, districtId: number) => {
    e.preventDefault();
    e.stopPropagation();
    setEditingItem({
      type: 'location',
      id: 'new',
      data: { district_id: districtId },
    });
  };

  const handleEditLocation = (e: React.MouseEvent, location: LocationNode) => {
    e.stopPropagation();
    setEditingItem({
      type: 'location',
      id: location.id,
      data: location as unknown as Record<string, unknown>,
    });
  };

  // --- Render helpers ---

  const renderLocationsRecursively = (location: LocationNode) => (
    <div key={location.id}>
      <div className={`grid grid-cols-[4px_60px_120px_minmax(200px,1fr)_100px_auto] gap-2.5 items-center px-3 py-2 rounded my-1 text-sm transition-colors ${
        location.marker_type === 'dangerous' ? 'bg-red-600/[0.06] text-[#d4e6f3] hover:bg-red-600/[0.12] border-l-2 border-red-400/40'
        : location.marker_type === 'dungeon' ? 'bg-purple-600/[0.06] text-[#d4e6f3] hover:bg-purple-600/[0.12] border-l-2 border-purple-400/40'
        : location.marker_type === 'farm' ? 'bg-orange-600/[0.06] text-[#d4e6f3] hover:bg-orange-600/[0.12] border-l-2 border-orange-400/40'
        : 'bg-green-600/[0.06] text-[#d4e6f3] hover:bg-green-600/[0.12] border-l-2 border-green-400/30'
      }`}>
        <div />
        <div className="text-white/50">{location.id}</div>
        {location.image_url && (
          <div>
            <img src={location.image_url} alt="" className="w-[120px] h-[80px] object-cover rounded" />
          </div>
        )}
        {!location.image_url && <div />}
        <div>{location.name}</div>
        <div className={`text-xs ${
          location.marker_type === 'dangerous' ? 'text-red-400/70'
          : location.marker_type === 'dungeon' ? 'text-purple-400/70'
          : location.marker_type === 'farm' ? 'text-orange-400/70'
          : 'text-green-400/70'
        }`}>{
          location.marker_type === 'dangerous' ? 'Опасная'
          : location.marker_type === 'dungeon' ? 'Подземелье'
          : location.marker_type === 'farm' ? 'Фарм'
          : 'Безопасная'
        }</div>
        <div className="flex gap-2 items-center justify-end">
          <button
            className="px-2 py-1 bg-site-blue/20 text-site-blue border-none rounded cursor-pointer text-xs transition-colors hover:bg-site-blue/30"
            onClick={(e) => handleEditLocation(e, location)}
          >
            Изменить
          </button>
          <button
            className="px-2 py-1 bg-site-red/20 text-[#ff9999] border-none rounded cursor-pointer text-xs transition-colors hover:bg-site-red/30"
            onClick={(e) => handleDeleteLocation(e, location.id)}
          >
            Удалить
          </button>
        </div>
      </div>
      {location.children && location.children.length > 0 && (
        <div className="ml-5 border-l border-white/10 pl-5">
          {location.children.map((child) => renderLocationsRecursively(child))}
        </div>
      )}
    </div>
  );

  // Group countries by area
  const countriesByArea = areas.map((area) => ({
    area,
    countries: countries.filter((c: Country) => c.area_id === area.id),
  }));
  const unassignedCountries = countries.filter((c: Country) => !c.area_id);

  // --- Render ---

  if (error) return <div className="text-site-red text-center p-8 text-lg">{error}</div>;
  if (loading && !countries?.length && !areas?.length)
    return <div className="text-white text-center p-8 text-lg">Загрузка...</div>;

  return (
    <div className="p-5 text-white min-h-screen">
      <h1 className="gold-text text-2xl font-medium uppercase text-center mb-8 tracking-wider">
        Управление локациями
      </h1>

      <div className="flex flex-col gap-2.5 max-w-[1200px] mx-auto">
        {/* === Areas Section === */}
        <div className="mb-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="gold-text text-xl font-medium uppercase">Области</h2>
            <button
              className="px-4 py-2 bg-green-600/20 text-white border-none rounded cursor-pointer transition-colors hover:bg-green-600/30 text-sm"
              onClick={handleStartCreateArea}
            >
              Добавить область
            </button>
          </div>

          {/* Area create/edit form */}
          {isCreatingArea && (
            <div className="bg-[rgba(22,37,49,0.85)] rounded-lg p-5 mb-4">
              <h3 className="text-[#a8c6df] uppercase mb-4 text-base font-medium">
                {editingArea ? 'Редактирование области' : 'Создание области'}
              </h3>
              <form onSubmit={handleSaveArea} className="flex flex-col gap-4">
                <div>
                  <label className="block mb-1 text-[#8ab3d5] font-medium text-sm">НАЗВАНИЕ:</label>
                  <input
                    type="text"
                    name="name"
                    value={areaForm.name}
                    onChange={handleAreaFormChange}
                    required
                    className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block mb-1 text-[#8ab3d5] font-medium text-sm">ОПИСАНИЕ:</label>
                  <textarea
                    name="description"
                    value={areaForm.description}
                    onChange={handleAreaFormChange}
                    rows={3}
                    className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none resize-y"
                  />
                </div>
                <div>
                  <label className="block mb-1 text-[#8ab3d5] font-medium text-sm">ПОРЯДОК СОРТИРОВКИ:</label>
                  <input
                    type="number"
                    name="sort_order"
                    value={areaForm.sort_order}
                    onChange={handleAreaFormChange}
                    className="w-full p-2.5 bg-black/30 border border-white/10 rounded text-[#d4e6f3] transition-colors focus:border-site-blue/50 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block mb-1 text-[#8ab3d5] font-medium text-sm">КАРТА ОБЛАСТИ:</label>
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handleAreaMapChange}
                    className="text-[#d4e6f3] text-sm"
                  />
                  {editingArea?.map_image_url && !areaMapFile && (
                    <img
                      src={editingArea.map_image_url}
                      alt="Карта области"
                      className="mt-2 max-w-full max-h-[200px] rounded border border-white/10"
                    />
                  )}
                </div>
                <div className="flex gap-4">
                  <button
                    type="submit"
                    className="px-6 py-2 bg-site-blue text-white border-none rounded cursor-pointer font-medium transition-colors hover:bg-[#5d8fa8]"
                  >
                    {editingArea ? 'Сохранить' : 'Создать'}
                  </button>
                  <button
                    type="button"
                    className="px-6 py-2 bg-white/10 text-white border-none rounded cursor-pointer font-medium transition-colors hover:bg-white/20"
                    onClick={handleCancelAreaForm}
                  >
                    Отмена
                  </button>
                </div>
              </form>
            </div>
          )}

          {/* Area list with nested countries */}
          {countriesByArea.map(({ area, countries: areaCountries }) => (
            <div key={area.id} className="bg-[rgba(22,37,49,0.85)] rounded-lg p-5 mb-3">
              <div
                className="flex justify-between items-center cursor-pointer select-none hover:opacity-90"
                onClick={() => toggleArea(area.id)}
              >
                <span className="text-lg font-bold text-gold">{area.name}</span>
                <div className="flex items-center gap-4">
                  {area.map_image_url && (
                    <button
                      className="px-2 py-1 bg-green-600/20 text-green-400 border-none rounded cursor-pointer text-xs transition-colors hover:bg-green-600/30"
                      onClick={(e) => {
                        e.stopPropagation();
                        if (editingZonesForAreaId === area.id) {
                          setEditingZonesForAreaId(null);
                        } else {
                          setEditingZonesForAreaId(area.id);
                          setOpenedAreas(prev => ({ ...prev, [area.id]: true }));
                        }
                      }}
                    >
                      Редактировать зоны
                    </button>
                  )}
                  <button
                    className="px-2 py-1 bg-site-blue/20 text-site-blue border-none rounded cursor-pointer text-xs transition-colors hover:bg-site-blue/30"
                    onClick={(e) => handleStartEditArea(e, area)}
                  >
                    Редактировать
                  </button>
                  <button
                    className="px-2 py-1 bg-site-red/20 text-[#ff9999] border-none rounded cursor-pointer text-xs transition-colors hover:bg-site-red/30"
                    onClick={(e) => handleDeleteArea(e, area.id)}
                  >
                    Удалить
                  </button>
                  <span
                    className={`text-site-blue transition-transform duration-300 inline-block ${
                      openedAreas[area.id] ? 'rotate-180' : ''
                    }`}
                  >
                    ▼
                  </span>
                </div>
              </div>

              {openedAreas[area.id] && (
                <div className="mt-4 ml-4 pl-4 border-l border-white/10">
                  {area.map_image_url && (
                    <div className="mb-3">
                      <img
                        src={area.map_image_url}
                        alt={`Карта: ${area.name}`}
                        className="max-w-[300px] max-h-[200px] rounded border border-white/10"
                      />
                    </div>
                  )}
                  {renderCountries(areaCountries)}
                  {editingZonesForAreaId === area.id && area.map_image_url && (
                    <div className="mt-4">
                      <AdminClickableZoneEditor
                        parentType="area"
                        parentId={area.id}
                        mapImageUrl={area.map_image_url}
                        targetOptions={areaCountries.map((c) => ({ id: c.id, name: c.name }))}
                        targetType="country"
                        areaOptions={areas.map((a) => ({ id: a.id, name: a.name }))}
                        onClose={() => setEditingZonesForAreaId(null)}
                      />
                    </div>
                  )}
                </div>
              )}
            </div>
          ))}

          {/* Countries without area */}
          {unassignedCountries.length > 0 && (
            <div className="bg-[rgba(22,37,49,0.85)] rounded-lg p-5 mb-3">
              <h3 className="text-[#a8c6df] mb-3 text-base font-medium">
                Страны без области
              </h3>
              {renderCountries(unassignedCountries)}
            </div>
          )}
        </div>

        {/* Add country button */}
        <button
          className="px-4 py-2 bg-green-600/20 text-white border-none rounded cursor-pointer mb-4 transition-colors hover:bg-green-600/30 self-start"
          onClick={() => setEditingCountry({})}
        >
          Добавить страну
        </button>

        {/* --- Modal: Edit Country --- */}
        {editingCountry && (
          <div
            className="fixed inset-0 bg-black/85 z-[1000] overflow-y-auto py-10 px-5 flex items-start justify-center cursor-pointer"
            onClick={(e) => handleOverlayClick(e, () => setEditingCountry(null))}
          >
            <EditCountryForm
              initialData={editingCountry}
              onCancel={() => setEditingCountry(null)}
              onSuccess={async (data?: unknown) => {
                const countryData = data as Record<string, unknown> | undefined;
                if (countryData && !countryData.id) {
                  // New country — dispatch createCountry
                  try {
                    await dispatch(createCountry(countryData) as any).unwrap();
                    toast.success('Страна создана');
                  } catch {
                    toast.error('Ошибка создания страны');
                    return;
                  }
                } else if (countryData?.id) {
                  // Existing country — dispatch updateCountry
                  try {
                    await dispatch(updateCountry(countryData) as any).unwrap();
                    toast.success('Страна обновлена');
                  } catch {
                    toast.error('Ошибка обновления страны');
                    return;
                  }
                }
                setEditingCountry(null);
                dispatch(fetchCountriesList());
              }}
            />
          </div>
        )}

        {/* --- Modal: Edit Region --- */}
        {editingRegion && (
          <div
            className="fixed inset-0 bg-black/85 z-[1000] overflow-y-auto py-10 px-5 flex items-start justify-center cursor-pointer"
            onClick={(e) => handleOverlayClick(e, () => setEditingRegion(null))}
          >
            <EditRegionForm
              regionId={(editingRegion as { id?: number }).id || 'new'}
              initialCountryId={(editingRegion as { country_id?: number }).country_id}
              initialData={editingRegion}
              onCancel={() => setEditingRegion(null)}
              onSuccess={() => {
                setEditingRegion(null);
                dispatch(fetchCountriesList());
              }}
            />
          </div>
        )}

        {/* --- Modal: Edit District --- */}
        {editingDistrict && (
          <div
            className="fixed inset-0 bg-black/85 z-[1000] overflow-y-auto py-10 px-5 flex items-start justify-center cursor-pointer"
            onClick={(e) => handleOverlayClick(e, () => setEditingDistrict(null))}
          >
            <EditDistrictForm
              districtId={(editingDistrict as { id?: number | string }).id || 'new'}
              initialRegionId={(editingDistrict as { initialRegionId?: number }).initialRegionId}
              onCancel={() => setEditingDistrict(null)}
              onSuccess={() => {
                setEditingDistrict(null);
                dispatch(fetchCountriesList());
              }}
            />
          </div>
        )}

        {/* --- Modal: Edit Location --- */}
        {editingItem && editingItem.type === 'location' && (
          <div
            className="fixed inset-0 bg-black/85 z-[1000] overflow-y-auto py-10 px-5 flex items-start justify-center cursor-pointer"
            onClick={(e) => handleOverlayClick(e, () => setEditingItem(null))}
          >
            <EditLocationForm
              locationId={editingItem.id}
              initialData={editingItem.data}
              onCancel={() => setEditingItem(null)}
              onSuccess={() => {
                setEditingItem(null);
                dispatch(fetchCountriesList());
              }}
            />
          </div>
        )}
      </div>
    </div>
  );

  // --- Shared render function for countries list ---
  function renderCountries(countryList: Country[]) {
    return countryList.map((country) => (
      <div key={country.id} className="bg-[rgba(22,37,49,0.85)] rounded-lg p-5 mb-3">
        <div
          className="flex justify-between items-center cursor-pointer select-none hover:opacity-90"
          onClick={() => toggleCountry(country.id)}
        >
          <span className="text-lg font-bold text-[#a8c6df]">{country.name}</span>
          <div className="flex items-center gap-4">
            {countryDetails[country.id]?.map_image_url && (
              <button
                className="px-2 py-1 bg-green-600/20 text-green-400 border-none rounded cursor-pointer text-xs transition-colors hover:bg-green-600/30"
                onClick={(e) => {
                  e.stopPropagation();
                  if (editingZonesForCountryId === country.id) {
                    setEditingZonesForCountryId(null);
                  } else {
                    setEditingZonesForCountryId(country.id);
                    setOpenedCountries(prev => ({ ...prev, [country.id]: true }));
                  }
                }}
              >
                Редактировать зоны
              </button>
            )}
            <button
              className="px-2 py-1 bg-site-blue/20 text-site-blue border-none rounded cursor-pointer text-xs transition-colors hover:bg-site-blue/30"
              onClick={(e) => handleEditCountry(e, country)}
            >
              Редактировать
            </button>
            <button
              className="px-2 py-1 bg-site-red/20 text-[#ff9999] border-none rounded cursor-pointer text-xs transition-colors hover:bg-site-red/30"
              onClick={(e) => handleDeleteCountry(e, country.id)}
            >
              Удалить
            </button>
            <span
              className={`text-site-blue transition-transform duration-300 inline-block ${
                openedCountries[country.id] ? 'rotate-180' : ''
              }`}
            >
              ▼
            </span>
          </div>
        </div>

        {openedCountries[country.id] && countryDetails[country.id] && (
          <div className="mt-4 ml-4 pl-4 border-l border-white/10">
            <button
              className="px-3 py-1.5 bg-site-blue/20 text-white border-none rounded cursor-pointer mb-2.5 text-sm transition-colors hover:bg-site-blue/30"
              onClick={() => handleAddNewRegion(country.id)}
            >
              Добавить регион
            </button>

            {countryDetails[country.id].regions?.map((region: Region) => (
              <div key={region.id}>
                <div
                  className="grid grid-cols-[60px_minmax(200px,1fr)_100px_auto] gap-2.5 items-center px-3 py-2 bg-site-blue/10 rounded my-1 text-sm text-[#d4e6f3] cursor-pointer hover:bg-white/10 transition-colors"
                  onClick={(e) => toggleRegion(e, region.id)}
                >
                  <div>{region.id}</div>
                  <div>{region.name}</div>
                  <div>Регион</div>
                  <div className="flex gap-2 items-center justify-end">
                    <button
                      className="px-2 py-1 bg-site-blue/20 text-site-blue border-none rounded cursor-pointer text-xs transition-colors hover:bg-site-blue/30"
                      onClick={(e) => handleEditRegion(e, region)}
                    >
                      Изменить
                    </button>
                    <button
                      className="px-2 py-1 bg-site-red/20 text-[#ff9999] border-none rounded cursor-pointer text-xs transition-colors hover:bg-site-red/30"
                      onClick={(e) => handleDeleteRegion(e, region.id)}
                    >
                      Удалить
                    </button>
                    <button
                      className="px-2 py-1 bg-site-blue/20 text-white border-none rounded cursor-pointer text-xs transition-colors hover:bg-site-blue/30 whitespace-nowrap"
                      onClick={(e) => handleAddDistrict(e, region.id)}
                    >
                      Добавить зону
                    </button>
                    {regionDetails[region.id]?.map_image_url && (
                      <button
                        className={`px-2 py-1 border-none rounded cursor-pointer text-xs transition-colors whitespace-nowrap ${
                          editingMapForRegionId === region.id
                            ? 'bg-green-600/30 text-green-300'
                            : 'bg-green-600/20 text-green-400 hover:bg-green-600/30'
                        }`}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (editingMapForRegionId === region.id) {
                            setEditingMapForRegionId(null);
                          } else {
                            setEditingMapForRegionId(region.id);
                            // Ensure region is expanded and details are loaded (always re-fetch for fresh data)
                            if (!openedRegions[region.id]) {
                              setOpenedRegions((prev) => ({ ...prev, [region.id]: true }));
                            }
                            dispatch(fetchRegionDetails(region.id));
                          }
                        }}
                      >
                        Карта региона
                      </button>
                    )}
                    <span
                      className={`text-site-blue transition-transform duration-300 inline-block ml-2 ${
                        openedRegions[region.id] ? 'rotate-180' : ''
                      }`}
                    >
                      ▼
                    </span>
                  </div>
                </div>

                {openedRegions[region.id] && regionDetails[region.id] && (
                  <div className="ml-5 border-l border-white/10 pl-5">
                    {(() => {
                      const rd = regionDetails[region.id];
                      const allDistricts: District[] = rd.districts ?? [];
                      // Top-level districts (no parent)
                      const topDistricts = allDistricts.filter((d) => !d.parent_district_id);
                      // Sub-districts grouped by parent
                      const subByParent: Record<number, District[]> = {};
                      for (const d of allDistricts) {
                        if (d.parent_district_id) {
                          if (!subByParent[d.parent_district_id]) subByParent[d.parent_district_id] = [];
                          subByParent[d.parent_district_id].push(d);
                        }
                      }
                      // Standalone locations (from map_items with no district_id)
                      const standaloneLocations = (rd.map_items ?? []).filter(
                        (item: { type: string; district_id?: number | null }) => item.type === 'location' && !item.district_id,
                      );

                      const renderDistrictRow = (district: District, indent: number) => (
                        <div key={district.id}>
                          <div
                            className={`grid grid-cols-[4px_60px_120px_minmax(200px,1fr)_100px_auto] gap-2.5 items-center px-3 py-2 rounded my-1 text-sm cursor-pointer transition-colors ${
                              indent > 0
                                ? 'bg-amber-600/[0.08] text-amber-200/80 hover:bg-amber-600/[0.14] border-l-2 border-amber-500/30'
                                : 'bg-amber-600/[0.12] text-[#e8d5a0] hover:bg-amber-600/[0.18] border-l-2 border-amber-400/50'
                            }`}
                            style={indent > 0 ? { marginLeft: indent * 20 } : undefined}
                            onClick={(e) => toggleDistrict(e, district.id)}
                          >
                            <div />
                            <div className="text-white/50">{district.id}</div>
                            {district.image_url ? (
                              <div>
                                <img src={district.image_url} alt="" className="w-[120px] h-[80px] object-cover rounded" />
                              </div>
                            ) : (
                              <div />
                            )}
                            <div className="font-medium">{district.name}</div>
                            <div className={`text-xs ${indent > 0 ? 'text-amber-400/60' : 'text-amber-300/70'}`}>{indent > 0 ? 'Подзона' : 'Зона'}</div>
                            <div className="flex gap-2 items-center justify-end">
                              <button
                                className="px-2 py-1 bg-site-blue/20 text-site-blue border-none rounded cursor-pointer text-xs transition-colors hover:bg-site-blue/30"
                                onClick={(e) => handleEditDistrict(e, district)}
                              >
                                Изменить
                              </button>
                              <button
                                className="px-2 py-1 bg-site-red/20 text-[#ff9999] border-none rounded cursor-pointer text-xs transition-colors hover:bg-site-red/30"
                                onClick={(e) => handleDeleteDistrict(e, district.id)}
                              >
                                Удалить
                              </button>
                              <button
                                className="px-2 py-1 bg-site-blue/20 text-white border-none rounded cursor-pointer text-xs transition-colors hover:bg-site-blue/30 whitespace-nowrap"
                                onClick={(e) => handleAddLocation(e, district.id)}
                                type="button"
                              >
                                Добавить локацию
                              </button>
                              <span
                                className={`text-site-blue transition-transform duration-300 inline-block ml-2 ${
                                  openedDistricts[district.id] ? 'rotate-180' : ''
                                }`}
                              >
                                ▼
                              </span>
                            </div>
                          </div>

                          {openedDistricts[district.id] && (
                            <div className="ml-5 border-l border-white/10 pl-5">
                              {/* Sub-districts nested inside */}
                              {(subByParent[district.id] ?? []).map((sub) => renderDistrictRow(sub, indent + 1))}
                              {/* Locations of this district */}
                              {district.locations?.map((loc) => renderLocationsRecursively(loc))}
                            </div>
                          )}
                        </div>
                      );

                      return (
                        <>
                          {topDistricts.map((d) => renderDistrictRow(d, 0))}
                          {/* Standalone locations (not in any zone) */}
                          {standaloneLocations.length > 0 && (
                            <>
                              {standaloneLocations.map((loc: LocationNode & { id: number; name: string; type: string; image_url?: string | null; marker_type?: string }) => (
                                renderLocationsRecursively({
                                  id: loc.id,
                                  name: loc.name,
                                  type: loc.type ?? 'location',
                                  image_url: loc.image_url,
                                  marker_type: loc.marker_type,
                                })
                              ))}
                            </>
                          )}
                        </>
                      );
                    })()}

                    {/* Region Map Editor */}
                    {editingMapForRegionId === region.id && regionDetails[region.id]?.map_image_url && (
                      <RegionMapEditor
                        regionId={region.id}
                        mapImageUrl={regionDetails[region.id].map_image_url!}
                        mapItems={regionDetails[region.id].map_items ?? []}
                        districts={
                          regionDetails[region.id].districts?.map((d: District) => ({
                            id: d.id,
                            name: d.name,
                            parent_district_id: d.parent_district_id ?? null,
                            marker_type: d.marker_type ?? null,
                            recommended_level: d.recommended_level ?? null,
                            map_icon_url: d.map_icon_url ?? null,
                            map_image_url: d.map_image_url ?? null,
                            x: d.x ?? null,
                            y: d.y ?? null,
                          })) ?? []
                        }
                        neighborEdges={regionDetails[region.id].neighbor_edges ?? []}
                        onClose={() => setEditingMapForRegionId(null)}
                      />
                    )}
                  </div>
                )}
              </div>
            ))}
            {editingZonesForCountryId === country.id && countryDetails[country.id]?.map_image_url && (
              <div className="mt-4">
                <AdminClickableZoneEditor
                  parentType="country"
                  parentId={country.id}
                  mapImageUrl={countryDetails[country.id].map_image_url!}
                  targetOptions={countryDetails[country.id].regions?.map((r: Region) => ({ id: r.id, name: r.name })) || []}
                  targetType="region"
                  areaOptions={areas.map((a) => ({ id: a.id, name: a.name }))}
                  onClose={() => setEditingZonesForCountryId(null)}
                />
              </div>
            )}
          </div>
        )}
      </div>
    ));
  }
};

export default AdminLocationsPage;
