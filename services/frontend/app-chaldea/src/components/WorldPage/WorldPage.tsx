import { useEffect, useMemo, useState } from 'react';
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
  selectDetailsLoading,
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
import RegionInteractiveMap from './RegionInteractiveMap/RegionInteractiveMap';
import type { MapItem } from './RegionInteractiveMap/RegionInteractiveMap';

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
  const detailsLoading = useAppSelector(selectDetailsLoading);
  const error = useAppSelector(selectWorldMapError);

  // Get current user character info for auto-focus
  const userCharacter = useAppSelector((state) => state.user.character);
  const currentLocationId = userCharacter?.current_location?.id ?? null;

  // Map transition animation state
  const [mapTransition, setMapTransition] = useState<'idle' | 'zoom-out' | 'fade-in'>('idle');
  const [pendingNavigation, setPendingNavigation] = useState<string | null>(null);

  // District modal state
  const [selectedDistrictId, setSelectedDistrictId] = useState<number | null>(null);

  // City map view state: when a district has map_image_url, show its map instead of modal
  const [cityMapDistrictId, setCityMapDistrictId] = useState<number | null>(null);

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

  // Reset city map view when changing route
  useEffect(() => {
    setCityMapDistrictId(null);
    setSelectedDistrictId(null);
  }, [viewLevel, entityId]);

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

  // Fetch clickable zones for world level (using first area)
  useEffect(() => {
    if (viewLevel === 'world' && areas.length > 0) {
      dispatch(fetchClickableZones({ parentType: 'area', parentId: areas[0].id }));
    }
  }, [dispatch, viewLevel, areas]);

  // Auto-focus on character's area/country when on world level
  useEffect(() => {
    if (viewLevel === 'world' && areas.length === 1 && !params.areaId) {
      navigate(`/world/area/${areas[0].id}`, { replace: true });
    }
  }, [viewLevel, areas, navigate, params.areaId]);

  // Animated navigation: zoom-out → navigate → fade-in
  const animatedNavigate = (path: string) => {
    setMapTransition('zoom-out');
    setPendingNavigation(path);
    setTimeout(() => {
      navigate(path);
      setMapTransition('fade-in');
      setTimeout(() => setMapTransition('idle'), 400);
    }, 350);
  };

  // Trigger fade-in when view changes (e.g. via breadcrumbs or back button)
  useEffect(() => {
    if (!pendingNavigation) {
      setMapTransition('fade-in');
      const t = setTimeout(() => setMapTransition('idle'), 400);
      return () => clearTimeout(t);
    }
    setPendingNavigation(null);
  }, [viewLevel, entityId]);

  // Handle zone click - navigate to target
  const handleZoneClick = (zone: ClickableZone) => {
    if (zone.target_type === 'country') {
      animatedNavigate(`/world/country/${zone.target_id}`);
    } else if (zone.target_type === 'region') {
      animatedNavigate(`/world/region/${zone.target_id}`);
    } else if (zone.target_type === 'area') {
      animatedNavigate(`/world/area/${zone.target_id}`);
    }
  };

  // Handle location click from region view
  const handleLocationClick = (locationId: number) => {
    animatedNavigate(`/location/${locationId}`);
  };

  // Handle district click from region map
  const handleDistrictClick = (districtId: number) => {
    const district = regionDetails?.districts.find((d) => d.id === districtId);
    const mapItem = regionDetails?.map_items?.find((i) => i.type === 'district' && i.id === districtId);
    const hasMapImage = district?.map_image_url || mapItem?.map_image_url;
    if (hasMapImage) {
      // Animate transition to city map
      setMapTransition('zoom-out');
      setTimeout(() => {
        setCityMapDistrictId(districtId);
        setMapTransition('fade-in');
        setTimeout(() => setMapTransition('idle'), 400);
      }, 350);
    } else {
      setSelectedDistrictId(districtId);
    }
  };

  // Handle back from city map to region map
  const handleCityMapBack = () => {
    setCityMapDistrictId(null);
  };

  // Handle district click inside city map (sub-districts open modal)
  const handleCityMapDistrictClick = (districtId: number) => {
    setSelectedDistrictId(districtId);
  };

  // City map district data (declared before breadcrumbs so it can be used there)
  const cityMapDistrict = useMemo(() => {
    if (cityMapDistrictId == null || !regionDetails) return null;
    return regionDetails.districts.find((d) => d.id === cityMapDistrictId) ?? null;
  }, [cityMapDistrictId, regionDetails]);

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

      // Add city map breadcrumb if viewing a district map
      if (cityMapDistrict) {
        items.push({ label: cityMapDistrict.name, path: '#' });
      }
    }

    return items;
  }, [viewLevel, areaDetails, countryDetails, regionDetails, hierarchyTree, cityMapDistrict]);

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

  // Build unified map items from backend map_items or fallback to client-side construction
  const regionMapItems: MapItem[] = useMemo(() => {
    if (!regionDetails) return [];

    // Use backend map_items if available, but filter out items that belong to districts with city maps
    if (regionDetails.map_items && regionDetails.map_items.length > 0) {
      // Collect ALL district IDs that belong inside a city map (recursively)
      const cityMapRootIds = new Set(
        regionDetails.districts.filter((d) => d.map_image_url).map((d) => d.id),
      );
      const cityMapAllIds = new Set(cityMapRootIds);
      const collectDescendants = (parentId: number) => {
        for (const d of regionDetails.districts) {
          if (d.parent_district_id === parentId && !cityMapAllIds.has(d.id)) {
            cityMapAllIds.add(d.id);
            collectDescendants(d.id);
          }
        }
      };
      for (const rootId of cityMapRootIds) collectDescendants(rootId);

      return regionDetails.map_items.filter((item) => {
        if (item.type === 'location' && item.district_id && cityMapAllIds.has(item.district_id)) {
          return false;
        }
        if (item.type === 'district' && item.parent_district_id && cityMapAllIds.has(item.parent_district_id)) {
          return false;
        }
        return true;
      });
    }

    // Fallback: build client-side from districts + locations
    // Also collect city-map district IDs to filter them out
    const cityMapRootIdsFb = new Set(
      regionDetails.districts.filter((d) => d.map_image_url).map((d) => d.id),
    );
    const cityMapAllIdsFb = new Set(cityMapRootIdsFb);
    const collectDescFb = (parentId: number) => {
      for (const d of regionDetails.districts) {
        if (d.parent_district_id === parentId && !cityMapAllIdsFb.has(d.id)) {
          cityMapAllIdsFb.add(d.id);
          collectDescFb(d.id);
        }
      }
    };
    for (const rootId of cityMapRootIdsFb) collectDescFb(rootId);

    const items: MapItem[] = [];

    for (const district of regionDetails.districts) {
      // Skip sub-districts that belong inside a city map
      if (district.parent_district_id && cityMapAllIdsFb.has(district.parent_district_id)) {
        continue;
      }

      // Add district as map item if it has coordinates
      if (district.x != null && district.y != null) {
        items.push({
          id: district.id,
          name: district.name,
          type: 'district',
          map_icon_url: district.map_icon_url ?? null,
          map_x: district.x,
          map_y: district.y,
          marker_type: null,
          image_url: district.image_url ?? null,
        });
      }

      // Skip locations if this district is a city-map district
      if (cityMapAllIdsFb.has(district.id)) {
        continue;
      }

      // Add locations
      for (const loc of district.locations) {
        if (loc.map_x != null && loc.map_y != null) {
          items.push({
            id: loc.id,
            name: loc.name,
            type: 'location',
            map_icon_url: loc.map_icon_url,
            map_x: loc.map_x,
            map_y: loc.map_y,
            marker_type: loc.marker_type,
            image_url: loc.image_url,
          });
        }
      }
    }

    return items;
  }, [regionDetails]);

  // City map image URL
  const cityMapImageUrl = useMemo(() => {
    if (!cityMapDistrict) return null;
    return cityMapDistrict.map_image_url ?? null;
  }, [cityMapDistrict]);

  // City map items: locations belonging to this district + sub-districts
  const cityMapItems: MapItem[] = useMemo(() => {
    if (cityMapDistrictId == null || !regionDetails) return [];
    const items: MapItem[] = [];

    // Add locations belonging to this district (from map_items)
    if (regionDetails.map_items) {
      for (const item of regionDetails.map_items) {
        if (item.type === 'location' && item.district_id === cityMapDistrictId) {
          items.push(item);
        }
        // Sub-districts of this district
        if (item.type === 'district' && item.parent_district_id === cityMapDistrictId) {
          items.push(item);
        }
      }
    }

    // Fallback: also check districts array for locations
    if (items.length === 0) {
      const district = regionDetails.districts.find((d) => d.id === cityMapDistrictId);
      if (district) {
        for (const loc of district.locations) {
          items.push({
            id: loc.id,
            name: loc.name,
            type: 'location',
            map_icon_url: loc.map_icon_url,
            map_x: loc.map_x,
            map_y: loc.map_y,
            marker_type: loc.marker_type,
            image_url: loc.image_url,
          });
        }
        // Sub-districts
        for (const subD of regionDetails.districts) {
          if (subD.parent_district_id === cityMapDistrictId) {
            items.push({
              id: subD.id,
              name: subD.name,
              type: 'district',
              map_icon_url: subD.map_icon_url,
              map_x: subD.x,
              map_y: subD.y,
              marker_type: subD.marker_type ?? null,
              image_url: subD.image_url,
            });
          }
        }
      }
    }

    return items;
  }, [cityMapDistrictId, regionDetails]);

  // Flatten all locations from all districts for the list view
  const allRegionLocations = useMemo(() => {
    if (!regionDetails) return [];
    return regionDetails.districts.flatMap((d) => d.locations);
  }, [regionDetails]);

  // Get selected district data for modal
  const selectedDistrict = useMemo(() => {
    if (selectedDistrictId == null || !regionDetails) return null;
    return regionDetails.districts.find((d) => d.id === selectedDistrictId) ?? null;
  }, [selectedDistrictId, regionDetails]);

  // Sub-districts of the selected district, sorted by sort_order
  const selectedDistrictChildren = useMemo(() => {
    if (selectedDistrictId == null || !regionDetails) return [];
    return [...regionDetails.districts]
      .filter((d) => d.parent_district_id === selectedDistrictId)
      .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
  }, [selectedDistrictId, regionDetails]);

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
                          {MARKER_ICONS[location.marker_type] ?? '\u{1F4CD}'}
                        </div>
                      )}
                    </div>

                    <div className="min-w-0 text-left">
                      <p className="text-white text-sm font-medium truncate">
                        {location.name}
                      </p>
                      <div className="flex items-center gap-1">
                        <p className="text-white/40 text-xs">
                          {MARKER_LABELS[location.marker_type] ?? 'Локация'}
                        </p>
                        {renderBadgeTag(location.marker_type, location.recommended_level)}
                      </div>
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
            {index > 0 && <span className="text-white/30">{'\u203A'}</span>}
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

        {/* Map area with transition animation */}
        <div
          className="flex-1 min-w-0 transition-all ease-site"
          style={{
            transitionDuration: mapTransition === 'idle' ? '0ms' : '350ms',
            opacity: mapTransition === 'zoom-out' ? 0 : 1,
            transform:
              mapTransition === 'zoom-out'
                ? 'scale(1.15)'
                : mapTransition === 'fade-in'
                  ? 'scale(1)'
                  : 'scale(1)',
            filter: mapTransition === 'zoom-out' ? 'blur(4px)' : 'blur(0px)',
          }}
        >
        {(detailsLoading || loading) && !areaDetails && !countryDetails && !regionDetails ? (
          <div className="flex-1 flex items-center justify-center min-h-[400px]">
            <div className="flex flex-col items-center gap-3">
              <div className="w-8 h-8 border-2 border-gold/30 border-t-gold rounded-full animate-spin" />
              <p className="text-white/50 text-sm">Загрузка карты...</p>
            </div>
          </div>
        ) : viewLevel === 'region' ? (
          cityMapDistrictId && cityMapImageUrl && cityMapDistrict ? (
            /* City map view for district */
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-3 mb-3">
                <button
                  onClick={handleCityMapBack}
                  className="text-white/50 hover:text-white text-sm bg-transparent border-none cursor-pointer transition-colors shrink-0 flex items-center gap-1"
                >
                  <span>&#9664;</span>
                  <span className="text-xs">Назад к региону</span>
                </button>
              </div>
              <h2 className="gold-text text-2xl font-medium uppercase mb-2 text-center">
                {cityMapDistrict.name}
              </h2>
              <RegionInteractiveMap
                mapImageUrl={cityMapImageUrl}
                mapItems={cityMapItems}
                neighborEdges={[]}
                currentLocationId={currentLocationId}
                onLocationClick={handleLocationClick}
                onDistrictClick={handleCityMapDistrictClick}
                isCityMap
              />
            </div>
          ) : regionDetails?.map_image_url ? (
            <div className="flex-1 min-w-0">
              <h2 className="gold-text text-2xl font-medium uppercase mb-2 text-center">
                {regionDetails.name}
              </h2>
              {regionDetails.recommended_level && (
                <p className="text-white/60 text-sm text-center mb-4">
                  Рекомендуемый уровень: {regionDetails.recommended_level}
                </p>
              )}
              <RegionInteractiveMap
                mapImageUrl={regionDetails.map_image_url}
                mapItems={regionMapItems}
                neighborEdges={regionDetails.neighbor_edges ?? []}
                districts={regionDetails.districts.map((d) => ({
                  id: d.id,
                  x: d.x,
                  y: d.y,
                  locations: d.locations.map((l) => ({
                    id: l.id,
                    name: l.name,
                    map_x: l.map_x,
                    map_y: l.map_y,
                  })),
                }))}
                currentLocationId={currentLocationId}
                onLocationClick={handleLocationClick}
                onDistrictClick={handleDistrictClick}
              />
            </div>
          ) : (
            renderRegionContent()
          )
        ) : (
          <InteractiveMap
            mapImageUrl={mapImageUrl}
            clickableZones={clickableZones}
            onZoneClick={handleZoneClick}
            title={mapTitle}
            countries={
              viewLevel === 'area'
                ? areaDetails?.countries?.map((c) => ({ id: c.id, emblem_url: c.emblem_url }))
                : viewLevel === 'world' && areaDetails?.countries
                  ? areaDetails.countries.map((c) => ({ id: c.id, emblem_url: c.emblem_url }))
                  : undefined
            }
          />
        )}
        </div>
      </div>

      {/* District contents modal */}
      {selectedDistrict && (
        <div
          className="modal-overlay"
          onClick={(e) => {
            if (e.target === e.currentTarget) setSelectedDistrictId(null);
          }}
        >
          <div className="modal-content max-w-lg w-full mx-4">
            {/* Modal header */}
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2 min-w-0">
                {selectedDistrict.parent_district_id != null && (
                  <button
                    onClick={() => setSelectedDistrictId(selectedDistrict.parent_district_id!)}
                    className="text-white/50 hover:text-white text-sm bg-transparent border-none cursor-pointer transition-colors shrink-0"
                    title="Назад"
                  >
                    &#9664;
                  </button>
                )}
                <h3 className="gold-text text-xl font-medium uppercase truncate">
                  {selectedDistrict.name}
                </h3>
              </div>
              <button
                onClick={() => setSelectedDistrictId(null)}
                className="text-white/50 hover:text-white text-xl bg-transparent border-none cursor-pointer transition-colors shrink-0"
              >
                &times;
              </button>
            </div>

            {/* Unified list: sub-zones + locations mixed, sorted by sort_order */}
            {(() => {
              const sortedLocations = [...selectedDistrict.locations].map((loc) => ({
                ...loc,
                _kind: 'location' as const,
              }));
              const sortedSubZones = selectedDistrictChildren.map((z) => ({
                ...z,
                _kind: 'zone' as const,
              }));
              const allItems = [...sortedLocations, ...sortedSubZones].sort(
                (a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0),
              );

              if (allItems.length === 0) {
                return <p className="text-white/40 text-sm mb-4">В этой зоне пока нет элементов</p>;
              }

              return (
                <div className="space-y-2 mb-4">
                  {allItems.map((item) =>
                    item._kind === 'zone' ? (
                      <button
                        key={`zone-${item.id}`}
                        onClick={() => setSelectedDistrictId(item.id)}
                        className="w-full flex items-center gap-3 p-3 rounded-card transition-all duration-200 ease-site cursor-pointer text-left bg-amber-600/10 hover:bg-amber-600/20"
                      >
                        <div className="w-9 h-9 rounded overflow-hidden shrink-0 border border-amber-400/40 bg-amber-600/30 flex items-center justify-center">
                          {item.map_icon_url ? (
                            <img src={item.map_icon_url} alt={item.name} className="w-full h-full object-cover" />
                          ) : (
                            <span className="text-amber-300/70 text-xs">&#9670;</span>
                          )}
                        </div>
                        <div className="min-w-0">
                          <p className="text-amber-200 text-sm font-medium truncate">{item.name}</p>
                          <div className="flex items-center gap-1">
                            <p className="text-white/40 text-xs">
                              {item.locations.length} {item.locations.length === 1 ? 'локация' : 'локаций'}
                            </p>
                            {renderBadgeTag(item.marker_type, item.recommended_level)}
                          </div>
                        </div>
                        <span className="ml-auto text-white/30 text-sm shrink-0">&#9654;</span>
                      </button>
                    ) : (
                      <button
                        key={`loc-${item.id}`}
                        onClick={() => {
                          setSelectedDistrictId(null);
                          handleLocationClick(item.id);
                        }}
                        className={`
                          w-full flex items-center gap-3 p-3 rounded-card
                          transition-all duration-200 ease-site cursor-pointer text-left
                          ${item.id === currentLocationId
                            ? 'bg-white/[0.12] gold-outline'
                            : 'bg-white/[0.05] hover:bg-white/[0.1]'}
                        `}
                      >
                        <div className="w-9 h-9 rounded-full overflow-hidden shrink-0 bg-site-dark">
                          {item.image_url ? (
                            <img src={item.image_url} alt={item.name} className="w-full h-full object-cover" />
                          ) : (
                            <div className="w-full h-full flex items-center justify-center text-white/20 text-xs">
                              {MARKER_ICONS[item.marker_type] ?? '\u{1F4CD}'}
                            </div>
                          )}
                        </div>
                        <div className="min-w-0">
                          <p className="text-white text-sm font-medium truncate">{item.name}</p>
                          <div className="flex items-center gap-1">
                            <p className="text-white/40 text-xs">
                              {MARKER_LABELS[item.marker_type] ?? 'Локация'}
                            </p>
                            {renderBadgeTag(item.marker_type, item.recommended_level)}
                          </div>
                        </div>
                        {item.id === currentLocationId && (
                          <span className="ml-auto text-gold text-xs font-medium shrink-0">
                            Вы здесь
                          </span>
                        )}
                      </button>
                    ),
                  )}
                </div>
              );
            })()}

            {/* Sub-districts (nested zones) */}
            {regionDetails && (() => {
              // Find districts that could be sub-districts
              // Since the DB doesn't have parent_id on districts, we just show this district's contents
              // Sub-districts would need a parent_id field; for now this section is reserved
              return null;
            })()}
          </div>
        </div>
      )}
    </div>
  );
};

const MARKER_ICONS: Record<string, string> = {
  safe: '\u{1F3E0}',
  dangerous: '\u{2694}\uFE0F',
  dungeon: '\u{1F3F0}',
  farm: '\u{1F479}',
};

const MARKER_LABELS: Record<string, string> = {
  safe: 'Безопасная',
  dangerous: 'Опасная',
  dungeon: 'Подземелье',
  farm: 'Фарм',
};

const MARKER_BADGE_COLORS: Record<string, string> = {
  safe: 'text-green-400',
  dangerous: 'text-red-400',
  dungeon: 'text-purple-400',
  farm: 'text-orange-400',
};

const renderBadgeTag = (markerType?: string | null, recommendedLevel?: number | null) => {
  const icon = MARKER_ICONS[markerType ?? ''] ?? '';
  const label = MARKER_LABELS[markerType ?? ''] ?? '';
  const color = MARKER_BADGE_COLORS[markerType ?? ''] ?? 'text-white/50';
  const showLevel = (markerType === 'dangerous' || markerType === 'farm') && recommendedLevel;
  const levelStr = showLevel ? `\u0423\u0440.${recommendedLevel}` : '';
  const parts = [icon, label, levelStr ? `\u{00B7} ${levelStr}` : ''].filter(Boolean).join(' ');
  if (!parts) return null;
  return (
    <span className={`text-[10px] bg-black/20 px-1.5 py-0.5 rounded whitespace-nowrap ${color}`}>
      {parts}
    </span>
  );
};

export default WorldPage;
