import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';

import StartPage from '../StartPage/StartPage.jsx';
import HomePage from '../HomePage/HomePage.jsx';
import CreateCharacterPage from '../CreateCharacterPage/CreateCharacterPage.jsx';
import RequestsPage from '../Admin/RequestsPage/RequestsPage.jsx';
import Layout from "./Layout/Layout.jsx";
import WorldPage from "../WorldPage/WorldPage.jsx";
import RegionPage from "../RegionPage/RegionPage.jsx";

const App = () => {
  return (
    <Router>
        <Routes>
          <Route path="/" element={<StartPage />} />
          <Route path="/*" element={<Layout />}>
            <Route path="home" element={<HomePage />} />
            <Route path="createCharacter" element={<CreateCharacterPage />} />
            <Route path="requestsPage" element={<RequestsPage />} />
            <Route path="world" element={<WorldPage />} />
            <Route path="region/:regionId" element={<RegionPage />} />
          </Route>
        </Routes>
    </Router>
  );
};

export default App;
