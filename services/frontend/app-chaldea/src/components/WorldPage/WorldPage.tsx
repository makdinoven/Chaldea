import { useEffect, useMemo } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import { motion } from 'motion/react';
import toast from 'react-hot-toast';
import { useAppDispatch, useAppSelector } from '../../redux/store';
import {
  selectAreas,
  selectHierarchyTree,
  selectClickableZones,
  selectAreaDetails,
  selectCountryDetails,
  selectRegionDetails,
  selectWorldMapLoading,
  selectWorldMapError,
  clearError,
} from '../../redux/slices/worldMapSlice';
import {
  fetchAreas,
  fetchAreaDetails,
  fetchClickableZones,
  fetchHierarchyTree,
  fetchCountryDetails,
  fetchRegionDetails,
} from '../../redux/actions/worldMapActions';
import type { ClickableZone } from '../../redux/actions/worldMapActions';
import HierarchyTree from './HierarchyTree/HierarchyTree';
import InteractiveMap from './InteractiveMap/InteractiveMap';

type ViewLevel = 'world' | 'area' | 'country' | 'region';

interface RouteParams {
  areaId?: string;
  countryId?: string;
  regionId?: string;
}

const WorldPage = () => {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const params = useParams<RouteParams>();

  const areas = useAppSelector(selectAreas);
  const hierarchyTree = useAppSelector(selectHierarchyTree);
  const clickableZones = useAppSelector(selectClickableZones);
  const areaDetails = useAppSelector(selectAreaDetails);
  const countryDetails = useAppSelector(selectCountryDetails);
  const regionDetails = useAppSelector(selectRegionDetails);
  const loading = useAppSelector(selectWorldMapLoading);
  const error = useAppSelector(selectWorldMapError);

  // Get current user character info for auto-focus
  const userCharacter = useAppSelector((state) => state.user.character);
  const currentLocationId = userCharacter?.current_location?.id ?? null;

  // Determine view level from route params
  const viewLevel: ViewLevel = useMemo(() => {
    if (params.regionId) return 'region';
    if (params.countryId) return 'country';
    if (params.areaId) return 'area';
    return 'world';
  }, [params.areaId, params.countryId, params.regionId]);

  const entityId = useMemo(() => {
    if (params.regionId) return Number(params.regionId);
    if (params.countryId) return Number(params.countryId);
    if (params.areaId) return Number(params.areaId);
    return null;
  }, [params.areaId, params.countryId, params.regionId]);

  // Show error toast
  useEffect(() => {
    if (error) {
      toast.error(error);
      dispatch(clearError());
    }
  }, [error, dispatch]);

  // Fetch hierarchy tree on mount
  useEffect(() => {
    dispatch(fetchHierarchyTree());
  }, [dispatch]);

  // Fetch data based on view level
  useEffect(() => {
    switch (viewLevel) {
      case 'world':
        dispatch(fetchAreas());
        break;
      case 'area':
        if (entityId) {
          dispatch(fetchAreaDetails(entityId));
          dispatch(fetchClickableZones({ parentType: 'area', parentId: entityId }));
        }
        break;
      case 'country':
        if (entityId) {
          dispatch(fetchCountryDetails(entityId));
          dispatch(fetchClickableZones({ parentType: 'country', parentId: entityId }));
        }
        break;
      case 'region':
        if (entityId) {
          dispatch(fetchRegionDetails(entityId));
        }
        break;
    }
  }, [dispatch, viewLevel, entityId]);

  // Auto-focus on character's area/country when on world level
  // We look through areas to find which area contains the character's location country
  useEffect(() => {
    if (viewLevel === 'world' && areas.length === 1 && !params.areaId) {
      navigate(`/world/area/${areas[0].id}`, { replace: true });
    }
  }, [viewLevel, areas, navigate, params.areaId]);

  // Handle zone click - navigate to target
  const handleZoneClick = (zone: ClickableZone) => {
    if (zone.target_type === 'country') {
      navigate(`/world/country/${zone.target_id}`);
    } else if (zone.target_type === 'region') {
      navigate(`/world/region/${zone.target_id}`);
    }
  };

  // Handle location click from region view
  const handleLocationClick = (locationId: number) => {
    navigate(`/location/${locationId}`);
  };

  // Build breadcrumb
  const breadcrumbs = useMemo(() => {
    const items: { label: string; path: string }[] = [
      { label: 'Мир', path: '/world' },
    ];

    if (viewLevel === 'area' && areaDetails) {
      items.push({ label: areaDetails.name, path: `/world/area/${areaDetails.id}` });
    }

    if (viewLevel === 'country' && countryDetails) {
      // Try to find the area for this country from the hierarchy tree
      const parentArea = hierarchyTree.find((node) =>
        node.type === 'area' && node.children.some((c) => c.id === countryDetails.id && c.type === 'country'),
      );
      if (parentArea) {
        items.push({ label: parentArea.name, path: `/world/area/${parentArea.id}` });
      }
      items.push({ label: countryDetails.name, path: `/world/country/${countryDetails.id}` });
    }

    if (viewLevel === 'region' && regionDetails) {
      // Find parent path from hierarchy tree
      for (const area of hierarchyTree) {
        if (area.type !== 'area') continue;
        for (const country of area.children) {
          const regionNode = country.children.find((r) => r.type === 'region' && r.id === regionDetails.id);
          if (regionNode) {
            items.push({ label: area.name, path: `/world/area/${area.id}` });
            items.push({ label: country.name, path: `/world/country/${country.id}` });
            break;
          }
        }
      }
      // Also check root-level countries (no area)
      for (const node of hierarchyTree) {
        if (node.type === 'country') {
          const regionNode = node.children.find((r) => r.type === 'region' && r.id === regionDetails.id);
          if (regionNode) {
            items.push({ label: node.name, path: `/world/country/${node.id}` });
            break;
          }
        }
      }
      items.push({ label: regionDetails.name, path: `/world/region/${regionDetails.id}` });
    }

    return items;
  }, [viewLevel, areaDetails, countryDetails, regionDetails, hierarchyTree]);

  // Determine map image and title for current view
  const mapImageUrl = useMemo(() => {
    switch (viewLevel) {
      case 'world':
        return areas.length > 0 ? areas[0]?.map_image_url : null;
      case 'area':
        return areaDetails?.map_image_url ?? null;
      case 'country':
        return countryDetails?.map_image_url ?? null;
      case 'region':
        return regionDetails?.map_image_url ?? null;
      default:
        return null;
    }
  }, [viewLevel, areas, areaDetails, countryDetails, regionDetails]);

  const mapTitle = useMemo(() => {
    switch (viewLevel) {
      case 'world':
        return 'Игровой мир';
      case 'area':
        return areaDetails?.name ?? 'Область';
      case 'country':
        return countryDetails?.name ?? 'Страна';
      case 'region':
        return regionDetails?.name ?? 'Регион';
      default:
        return 'Карта';
    }
  }, [viewLevel, areaDetails, countryDetails, regionDetails]);

  // For region view, render location list instead of polygon map
  const renderRegionContent = () => {
    if (!regionDetails) return null;

    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: 'easeOut' }}
        className="flex-1 min-w-0"
      >
        <h2 className="gold-text text-2xl font-medium uppercase mb-2 text-center">
          {regionDetails.name}
        </h2>

        {regionDetails.recommended_level && (
          <p className="text-white/60 text-sm text-center mb-4">
            Рекомендуемый уровень: {regionDetails.recommended_level}
          </p>
        )}

        <div className="space-y-4">
          {regionDetails.districts.map((district) => (
            <div key={district.id} className="gray-bg p-4">
              <h3 className="gold-text text-lg font-medium uppercase mb-3">
                {district.name}
              </h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {district.locations.map((location) => (
                  <button
                    key={location.id}
                    onClick={() => handleLocationClick(location.id)}
                    className={`
                      flex items-center gap-3 p-3 rounded-card
                      transition-all duration-200 ease-site cursor-pointer
                      ${location.id === currentLocationId
                        ? 'bg-white/[0.12] gold-outline'
                        : 'bg-white/[0.05] hover:bg-white/[0.1]'}
                    `}
                  >
                    {/* Location image or placeholder */}
                    <div className="w-10 h-10 rounded-full overflow-hidden shrink-0 bg-site-dark">
                      {location.image_url ? (
                        <img
                          src={location.image_url}
                          alt={location.name}
                          className="w-full h-full object-cover"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-white/20 text-xs">
                          {MARKER_ICONS[location.marker_type] ?? '📍'}
                        </div>
                      )}
                    </div>

                    <div className="min-w-0 text-left">
                      <p className="text-white text-sm font-medium truncate">
                        {location.name}
                      </p>
                      <p className="text-white/40 text-xs">
                        {MARKER_LABELS[location.marker_type] ?? 'Локация'}
                      </p>
                    </div>

                    {location.id === currentLocationId && (
                      <span className="ml-auto text-gold text-xs font-medium shrink-0">
                        Вы здесь
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </div>
          ))}

          {regionDetails.districts.length === 0 && (
            <div className="text-center py-8">
              <p className="text-white/40 text-sm">В этом регионе пока нет зон</p>
            </div>
          )}
        </div>
      </motion.div>
    );
  };

  return (
    <div className="py-4">
      {/* Breadcrumb */}
      <nav className="flex items-center gap-2 mb-4 flex-wrap text-sm">
        {breadcrumbs.map((crumb, index) => (
          <span key={crumb.path} className="flex items-center gap-2">
            {index > 0 && <span className="text-white/30">›</span>}
            {index === breadcrumbs.length - 1 ? (
              <span className="text-gold">{crumb.label}</span>
            ) : (
              <Link
                to={crumb.path}
                className="site-link text-white/70 hover:text-site-blue transition-colors duration-200 ease-site"
              >
                {crumb.label}
              </Link>
            )}
          </span>
        ))}
      </nav>

      {/* Main layout: tree + map */}
      <div className="flex gap-5 items-start">
        <HierarchyTree currentLocationId={currentLocationId} />

        {/* Map area */}
        {loading && !areaDetails && !countryDetails && !regionDetails ? (
          <div className="flex-1 flex items-center justify-center min-h-[400px]">
            <div className="flex flex-col items-center gap-3">
              <div className="w-8 h-8 border-2 border-gold/30 border-t-gold rounded-full animate-spin" />
              <p className="text-white/50 text-sm">Загрузка карты...</p>
            </div>
          </div>
        ) : viewLevel === 'region' ? (
          renderRegionContent()
        ) : (
          <InteractiveMap
            mapImageUrl={mapImageUrl}
            clickableZones={clickableZones}
            onZoneClick={handleZoneClick}
            title={mapTitle}
          />
        )}
      </div>
    </div>
  );
};

const MARKER_ICONS: Record<string, string> = {
  safe: '🏠',
  dangerous: '⚔️',
  dungeon: '🏰',
};

const MARKER_LABELS: Record<string, string> = {
  safe: 'Безопасная',
  dangerous: 'Опасная',
  dungeon: 'Подземелье',
};

export default WorldPage;
