import { useEffect } from "react";
import { BrowserRouter as Router, Route, Routes } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import { useAppDispatch } from "../../redux/store";
import { getMe, setAuthInitialized } from "../../redux/slices/userSlice";

import StartPage from "../StartPage/StartPage";
import HomePage from "../HomePage/HomePage";
import CreateCharacterPage from "../CreateCharacterPage/CreateCharacterPage";
import RequestsPage from "../Admin/RequestsPage/RequestsPage";
import Layout from "./Layout/Layout";
import WorldPage from "../WorldPage/WorldPage";
import AdminLocationsPage from "../AdminLocationsPage/AdminLocationsPage";
import AdminSkillsPage from "../AdminSkillsPage/AdminSkillsPage";
import LocationPage from "../pages/LocationPage/LocationPage";
import ItemsAdminPage from "../ItemsAdminPage/ItemsAdminPage";
import AdminPage from "../Admin/AdminPage";
import StarterKitsPage from "../Admin/StarterKitsPage/StarterKitsPage";
import BattlePage from "../pages/BattlePage/BattlePage";
import ProfilePage from "../ProfilePage/ProfilePage";
import AdminCharactersPage from "../Admin/CharactersPage/AdminCharactersPage";
import AdminCharacterDetailPage from "../Admin/CharactersPage/AdminCharacterDetailPage";
import RulesPage from "../RulesPage/RulesPage";
import RulesAdminPage from "../Admin/RulesAdminPage/RulesAdminPage";
import RbacAdminPage from "../Admin/RbacAdminPage/RbacAdminPage";
import AdminRacesPage from "../Admin/AdminRaces/AdminRacesPage";
import UserProfilePage from "../UserProfilePage/UserProfilePage";
import AllUsersPage from "../pages/AllUsersPage/AllUsersPage";
import OnlineUsersPage from "../pages/OnlineUsersPage/OnlineUsersPage";
import ProtectedRoute from "../CommonComponents/ProtectedRoute/ProtectedRoute";
import ChatHistoryPage from "../Chat/ChatHistoryPage";
import GameTimeAdminPage from "../Admin/GameTimeAdminPage";

const App = () => {
  const dispatch = useAppDispatch();

  useEffect(() => {
    const token = localStorage.getItem('accessToken');
    if (token) {
      dispatch(getMe());
    } else {
      dispatch(setAuthInitialized());
    }
  }, [dispatch]);

  return (
    <>
      <Toaster
        position="top-right"
        toastOptions={{
          style: {
            background: '#1a1a2e',
            color: '#fff',
            border: '1px solid rgba(255,255,255,0.1)',
          },
        }}
      />
      <Router>
        <Routes>
          <Route path="/" element={<StartPage />} />
          <Route path="/*" element={<Layout />}>
            <Route path="home" element={<HomePage />} />
            <Route path="createCharacter" element={<CreateCharacterPage />} />
            <Route path="requestsPage" element={
              <ProtectedRoute requiredPermission="characters:approve">
                <RequestsPage />
              </ProtectedRoute>
            } />
            <Route path="world" element={<WorldPage />} />
            <Route path="world/area/:areaId" element={<WorldPage />} />
            <Route path="world/country/:countryId" element={<WorldPage />} />
            <Route path="world/region/:regionId" element={<WorldPage />} />
            <Route path="location/:locationId" element={<LocationPage />} />
            <Route path="admin" element={
              <ProtectedRoute requiredRole="editor">
                <AdminPage />
              </ProtectedRoute>
            } />
            <Route path="admin/locations" element={
              <ProtectedRoute requiredPermission="locations:read">
                <AdminLocationsPage />
              </ProtectedRoute>
            } />
            <Route path="home/admin/skills" element={
              <ProtectedRoute requiredPermission="skills:read">
                <AdminSkillsPage />
              </ProtectedRoute>
            } />
            <Route path="admin/items" element={
              <ProtectedRoute requiredPermission="items:read">
                <ItemsAdminPage />
              </ProtectedRoute>
            } />
            <Route path="admin/starter-kits" element={
              <ProtectedRoute requiredPermission="characters:update">
                <StarterKitsPage />
              </ProtectedRoute>
            } />
            <Route path="admin/characters" element={
              <ProtectedRoute requiredPermission="characters:read">
                <AdminCharactersPage />
              </ProtectedRoute>
            } />
            <Route path="admin/characters/:characterId" element={
              <ProtectedRoute requiredPermission="characters:read">
                <AdminCharacterDetailPage />
              </ProtectedRoute>
            } />
            <Route path="rules" element={<RulesPage />} />
            <Route path="admin/rules" element={
              <ProtectedRoute requiredPermission="rules:read">
                <RulesAdminPage />
              </ProtectedRoute>
            } />
            <Route path="admin/users-roles" element={
              <ProtectedRoute requiredPermission="users:manage">
                <RbacAdminPage />
              </ProtectedRoute>
            } />
            <Route path="admin/races" element={
              <ProtectedRoute requiredPermission="races:create">
                <AdminRacesPage />
              </ProtectedRoute>
            } />
            <Route path="admin/game-time" element={
              <ProtectedRoute requiredPermission="gametime:read">
                <GameTimeAdminPage />
              </ProtectedRoute>
            } />
            <Route path="chat/history" element={<ChatHistoryPage />} />
            <Route path="players" element={<AllUsersPage />} />
            <Route path="players/online" element={<OnlineUsersPage />} />
            <Route path="profile" element={<ProfilePage />} />
            <Route path="user-profile" element={<UserProfilePage />} />
            <Route path="user-profile/:userId" element={<UserProfilePage />} />
            <Route
              path="location/:locationId/battle/:battleId"
              element={<BattlePage />}
            />
          </Route>
        </Routes>
      </Router>
    </>
  );
};

export default App;
