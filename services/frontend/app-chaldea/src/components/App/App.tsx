import { BrowserRouter as Router, Route, Routes } from "react-router-dom";
import { Toaster } from "react-hot-toast";

import StartPage from "../StartPage/StartPage";
import HomePage from "../HomePage/HomePage";
import CreateCharacterPage from "../CreateCharacterPage/CreateCharacterPage";
import RequestsPage from "../Admin/RequestsPage/RequestsPage";
import Layout from "./Layout/Layout";
import WorldPage from "../WorldPage/WorldPage";
import CountryPage from "../CountryPage/CountryPage";
import AdminLocationsPage from "../AdminLocationsPage/AdminLocationsPage";
import AdminSkillsPage from "../AdminSkillsPage/AdminSkillsPage";
import LocationPage from "../pages/LocationPage/LocationPage";
import ItemsAdminPage from "../ItemsAdminPage/ItemsAdminPage";
import AdminPage from "../Admin/AdminPage";
import StarterKitsPage from "../Admin/StarterKitsPage/StarterKitsPage";
import BattlePage from "../pages/BattlePage/BattlePage";
import ProfilePage from "../ProfilePage/ProfilePage";

const App = () => {
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
            <Route path="requestsPage" element={<RequestsPage />} />
            <Route path="world" element={<WorldPage />} />
            <Route path="location/:locationId" element={<LocationPage />} />
            <Route path="world/country/:countryId/" element={<CountryPage />} />
            <Route path="admin" element={<AdminPage />} />
            <Route path="admin/locations" element={<AdminLocationsPage />} />
            <Route path="home/admin/skills" element={<AdminSkillsPage />} />
            <Route path="admin/items" element={<ItemsAdminPage />} />
            <Route path="admin/starter-kits" element={<StarterKitsPage />} />
            <Route path="profile" element={<ProfilePage />} />
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
