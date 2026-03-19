import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../../redux/store';
import {
  fetchRaces,
  createRace,
  updateRace,
  deleteRace,
  createSubrace,
  updateSubrace,
  deleteSubrace,
  uploadRaceImage,
  uploadSubraceImage,
} from '../../../redux/slices/racesSlice';
import type { Race, Subrace, StatPreset } from '../../../redux/slices/racesSlice';
import RaceForm from './RaceForm';
import SubraceForm from './SubraceForm';
import { STAT_FIELDS } from './StatPresetEditor';

const AdminRacesPage = () => {
  const dispatch = useAppDispatch();
  const { races, loading, error } = useAppSelector((state) => state.races);

  const [expandedRaces, setExpandedRaces] = useState<Record<number, boolean>>({});

  // Form state
  const [showRaceForm, setShowRaceForm] = useState(false);
  const [editingRace, setEditingRace] = useState<Race | null>(null);
  const [showSubraceForm, setShowSubraceForm] = useState(false);
  const [editingSubrace, setEditingSubrace] = useState<Subrace | null>(null);
  const [defaultRaceIdForSubrace, setDefaultRaceIdForSubrace] = useState<number | null>(null);

  // Delete confirmation
  const [confirmDelete, setConfirmDelete] = useState<{
    type: 'race' | 'subrace';
    id: number;
    name: string;
  } | null>(null);

  useEffect(() => {
    dispatch(fetchRaces());
  }, [dispatch]);

  useEffect(() => {
    if (error) {
      toast.error(error);
    }
  }, [error]);

  // --- Race handlers ---

  const handleToggleRace = (raceId: number) => {
    setExpandedRaces((prev) => ({ ...prev, [raceId]: !prev[raceId] }));
  };

  const handleCreateRace = () => {
    setEditingRace(null);
    setShowRaceForm(true);
  };

  const handleEditRace = (e: React.MouseEvent, race: Race) => {
    e.stopPropagation();
    setEditingRace(race);
    setShowRaceForm(true);
  };

  const handleSaveRace = async (
    data: { name: string; description: string },
    imageFile: File | null
  ) => {
    try {
      let raceId: number;

      if (editingRace) {
        const result = await dispatch(
          updateRace({ raceId: editingRace.id_race, data })
        ).unwrap();
        raceId = result.id_race;
        toast.success('Раса обновлена');
      } else {
        const result = await dispatch(createRace(data)).unwrap();
        raceId = result.id_race;
        toast.success('Раса создана');
      }

      if (imageFile) {
        try {
          await dispatch(uploadRaceImage({ raceId, file: imageFile })).unwrap();
          toast.success('Изображение расы загружено');
        } catch {
          toast.error('Не удалось загрузить изображение расы');
        }
      }

      setShowRaceForm(false);
      setEditingRace(null);
      dispatch(fetchRaces());
    } catch {
      toast.error('Не удалось сохранить расу');
    }
  };

  const handleRequestDeleteRace = (e: React.MouseEvent, race: Race) => {
    e.stopPropagation();
    setConfirmDelete({ type: 'race', id: race.id_race, name: race.name });
  };

  const handleConfirmDelete = async () => {
    if (!confirmDelete) return;

    try {
      if (confirmDelete.type === 'race') {
        await dispatch(deleteRace(confirmDelete.id)).unwrap();
        toast.success('Раса удалена');
      } else {
        await dispatch(deleteSubrace(confirmDelete.id)).unwrap();
        toast.success('Подраса удалена');
      }
      dispatch(fetchRaces());
    } catch (err) {
      const message = typeof err === 'string' ? err : 'Не удалось выполнить удаление';
      toast.error(message);
    }
    setConfirmDelete(null);
  };

  // --- Subrace handlers ---

  const handleCreateSubrace = (e: React.MouseEvent, raceId: number) => {
    e.stopPropagation();
    setEditingSubrace(null);
    setDefaultRaceIdForSubrace(raceId);
    setShowSubraceForm(true);
  };

  const handleEditSubrace = (e: React.MouseEvent, subrace: Subrace) => {
    e.stopPropagation();
    setEditingSubrace(subrace);
    setDefaultRaceIdForSubrace(subrace.id_race);
    setShowSubraceForm(true);
  };

  const handleSaveSubrace = async (
    data: { id_race: number; name: string; description: string; stat_preset: StatPreset },
    imageFile: File | null
  ) => {
    try {
      let subraceId: number;

      if (editingSubrace) {
        const result = await dispatch(
          updateSubrace({ subraceId: editingSubrace.id_subrace, data })
        ).unwrap();
        subraceId = result.id_subrace;
        toast.success('Подраса обновлена');
      } else {
        const result = await dispatch(createSubrace(data)).unwrap();
        subraceId = result.id_subrace;
        toast.success('Подраса создана');
      }

      if (imageFile) {
        try {
          await dispatch(uploadSubraceImage({ subraceId, file: imageFile })).unwrap();
          toast.success('Изображение подрасы загружено');
        } catch {
          toast.error('Не удалось загрузить изображение подрасы');
        }
      }

      setShowSubraceForm(false);
      setEditingSubrace(null);
      dispatch(fetchRaces());
    } catch {
      toast.error('Не удалось сохранить подрасу');
    }
  };

  const handleRequestDeleteSubrace = (e: React.MouseEvent, subrace: Subrace) => {
    e.stopPropagation();
    setConfirmDelete({ type: 'subrace', id: subrace.id_subrace, name: subrace.name });
  };

  // --- Render ---

  return (
    <div className="p-5 text-white min-h-screen">
      <h1 className="gold-text text-2xl font-medium uppercase text-center mb-8 tracking-wider">
        Управление расами
      </h1>

      <div className="max-w-[1200px] mx-auto">
        {/* Top bar */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 mb-6">
          <button
            className="px-4 py-2 bg-green-600/20 text-white border-none rounded cursor-pointer
              transition-colors hover:bg-green-600/30 text-sm"
            onClick={handleCreateRace}
          >
            Добавить расу
          </button>
        </div>

        {/* Loading */}
        {loading && races.length === 0 && (
          <p className="text-white/60 text-center">Загрузка...</p>
        )}

        {/* Empty state */}
        {!loading && races.length === 0 && (
          <p className="text-white/60 text-center">Расы не найдены</p>
        )}

        {/* Race list */}
        <div className="flex flex-col gap-3">
          {races.map((race) => (
            <div
              key={race.id_race}
              className="bg-[rgba(22,37,49,0.85)] rounded-lg p-5"
            >
              {/* Race header */}
              <div
                className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 cursor-pointer select-none hover:opacity-90"
                onClick={() => handleToggleRace(race.id_race)}
              >
                <div className="flex items-center gap-3">
                  {race.image && (
                    <img
                      src={race.image}
                      alt={race.name}
                      className="w-10 h-10 rounded-full object-cover border border-white/10 flex-shrink-0"
                    />
                  )}
                  <span className="text-lg font-medium text-gold">{race.name}</span>
                  <span className="text-white/40 text-sm">
                    ({race.subraces?.length || 0} подрас)
                  </span>
                </div>
                <div className="flex items-center gap-3 flex-wrap">
                  <button
                    className="px-3 py-1.5 bg-green-600/20 text-white border-none rounded cursor-pointer text-xs
                      transition-colors hover:bg-green-600/30 whitespace-nowrap"
                    onClick={(e) => handleCreateSubrace(e, race.id_race)}
                  >
                    Добавить подрасу
                  </button>
                  <button
                    className="px-2 py-1 bg-site-blue/20 text-site-blue border-none rounded cursor-pointer text-xs
                      transition-colors hover:bg-site-blue/30"
                    onClick={(e) => handleEditRace(e, race)}
                  >
                    Редактировать
                  </button>
                  <button
                    className="px-2 py-1 bg-site-red/20 text-[#ff9999] border-none rounded cursor-pointer text-xs
                      transition-colors hover:bg-site-red/30"
                    onClick={(e) => handleRequestDeleteRace(e, race)}
                  >
                    Удалить
                  </button>
                  <span
                    className={`text-site-blue transition-transform duration-300 inline-block ${
                      expandedRaces[race.id_race] ? 'rotate-180' : ''
                    }`}
                  >
                    ▼
                  </span>
                </div>
              </div>

              {/* Race description */}
              {race.description && expandedRaces[race.id_race] && (
                <p className="text-white/50 text-sm mt-2 ml-[52px]">{race.description}</p>
              )}

              {/* Expanded subraces */}
              {expandedRaces[race.id_race] && (
                <div className="mt-4 ml-4 pl-4 border-l border-white/10">
                  {(!race.subraces || race.subraces.length === 0) && (
                    <p className="text-white/40 text-sm">Нет подрас</p>
                  )}
                  {race.subraces?.map((subrace) => (
                    <div
                      key={subrace.id_subrace}
                      className="bg-white/[0.04] rounded-lg p-4 mb-3 hover:bg-white/[0.06] transition-colors"
                    >
                      {/* Subrace header */}
                      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
                        <div className="flex items-center gap-3">
                          {subrace.image && (
                            <img
                              src={subrace.image}
                              alt={subrace.name}
                              className="w-8 h-8 rounded-full object-cover border border-white/10 flex-shrink-0"
                            />
                          )}
                          <span className="text-white font-medium">{subrace.name}</span>
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            className="px-2 py-1 bg-site-blue/20 text-site-blue border-none rounded cursor-pointer text-xs
                              transition-colors hover:bg-site-blue/30"
                            onClick={(e) => handleEditSubrace(e, subrace)}
                          >
                            Редактировать
                          </button>
                          <button
                            className="px-2 py-1 bg-site-red/20 text-[#ff9999] border-none rounded cursor-pointer text-xs
                              transition-colors hover:bg-site-red/30"
                            onClick={(e) => handleRequestDeleteSubrace(e, subrace)}
                          >
                            Удалить
                          </button>
                        </div>
                      </div>

                      {/* Subrace description */}
                      {subrace.description && (
                        <p className="text-white/40 text-sm mt-2">{subrace.description}</p>
                      )}

                      {/* Stat preset display */}
                      {subrace.stat_preset && (
                        <div className="mt-3 grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
                          {STAT_FIELDS.map(({ key, label }) => (
                            <div
                              key={key}
                              className="flex justify-between items-center bg-black/20 rounded px-2 py-1"
                            >
                              <span className="text-white/50 text-xs">{label}</span>
                              <span className="text-white text-xs font-medium">
                                {subrace.stat_preset?.[key] ?? 0}
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Race form modal */}
      {showRaceForm && (
        <RaceForm
          race={editingRace}
          onSave={handleSaveRace}
          onCancel={() => {
            setShowRaceForm(false);
            setEditingRace(null);
          }}
          loading={loading}
        />
      )}

      {/* Subrace form modal */}
      {showSubraceForm && (
        <SubraceForm
          subrace={editingSubrace}
          races={races}
          defaultRaceId={defaultRaceIdForSubrace}
          onSave={handleSaveSubrace}
          onCancel={() => {
            setShowSubraceForm(false);
            setEditingSubrace(null);
          }}
          loading={loading}
        />
      )}

      {/* Delete confirmation modal */}
      {confirmDelete && (
        <div
          className="fixed inset-0 bg-black/85 z-[1000] flex items-center justify-center px-5"
          onClick={(e) => {
            if (e.target === e.currentTarget) setConfirmDelete(null);
          }}
        >
          <div className="modal-content gold-outline gold-outline-thick max-w-md w-full">
            <h2 className="gold-text text-2xl uppercase mb-4">Подтверждение удаления</h2>
            <p className="text-white mb-6">
              Вы уверены, что хотите удалить{' '}
              {confirmDelete.type === 'race' ? 'расу' : 'подрасу'}{' '}
              <span className="text-gold font-medium">{confirmDelete.name}</span>?
            </p>
            <div className="flex gap-4">
              <button
                className="px-6 py-2 bg-site-red text-white border-none rounded cursor-pointer font-medium
                  transition-colors hover:bg-[#d45a3a]"
                onClick={handleConfirmDelete}
                disabled={loading}
              >
                {loading ? 'Удаление...' : 'Удалить'}
              </button>
              <button
                className="px-6 py-2 bg-white/10 text-white border-none rounded cursor-pointer font-medium
                  transition-colors hover:bg-white/20"
                onClick={() => setConfirmDelete(null)}
              >
                Отмена
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default AdminRacesPage;
