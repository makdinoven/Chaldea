import { BrowserRouter as Router, Route, Routes } from "react-router-dom";
import { Toaster } from "react-hot-toast";

import StartPage from "../StartPage/StartPage.jsx";
import HomePage from "../HomePage/HomePage.jsx";
import CreateCharacterPage from "../CreateCharacterPage/CreateCharacterPage.jsx";
import RequestsPage from "../Admin/RequestsPage/RequestsPage.tsx";
import Layout from "./Layout/Layout.tsx";
import WorldPage from "../WorldPage/WorldPage.jsx";
import CountryPage from "../CountryPage/CountryPage.jsx";
import AdminLocationsPage from "../AdminLocationsPage/AdminLocationsPage.jsx";
import AdminSkillsPage from "../AdminSkillsPage/AdminSkillsPage.tsx";
import LocationPage from "../pages/LocationPage/LocationPage.tsx";
import ItemsAdminPage from "../ItemsAdminPage/ItemsAdminPage";
import AdminPage from "../Admin/AdminPage";
import StarterKitsPage from "../Admin/StarterKitsPage/StarterKitsPage";
import BattlePage from "../pages/BattlePage/BattlePage.jsx";
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
