import React from 'react';
import {BrowserRouter as Router, Routes, Route} from 'react-router-dom';

import StartPage from '../StartPage/StartPage.jsx';
import HomePage from '../HomePage/HomePage.jsx';
import CreateCharacterPage from '../CreateCharacterPage/CreateCharacterPage.jsx';
import RequestsPage from '../Admin/RequestsPage/RequestsPage.jsx';
import Layout from "./Layout/Layout.jsx";
import WorldPage from "../WorldPage/WorldPage.jsx";
import CountryPage from "../CountryPage/CountryPage.jsx";
import AdminLocationsPage from '../AdminLocationsPage/AdminLocationsPage.jsx';
import AdminSkillsPage from "../AdminSkillsPage/AdminSkillsPage.jsx";

const App = () => {
    return (
        <Router>
            <Routes>
                <Route path="/" element={<StartPage/>}/>
                <Route path="/*" element={<Layout/>}>
                    <Route path="home" element={<HomePage/>}/>
                    <Route path="createCharacter" element={<CreateCharacterPage/>}/>
                    <Route path="requestsPage" element={<RequestsPage/>}/>
                    <Route path="world" element={<WorldPage/>}/>
                    <Route path="world/country/:countryId/" element={<CountryPage/>}/>
                    <Route path="admin/locations" element={<AdminLocationsPage />}/>
                    <Route path="home/admin/skills" element={<AdminSkillsPage />}/>
                </Route>
            </Routes>
        </Router>
    );
};

export default App;
