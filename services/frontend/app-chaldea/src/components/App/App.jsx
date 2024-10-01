import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';

import StartPage from '../StartPage/StartPage.jsx';
import HomePage from '../HomePage/HomePage.jsx';
import CreateCharacterPage from '../CreateCharacterPage/CreateCharacterPage.jsx';
import RequestsPage from '../Admin/RequestsPage/RequestsPage.jsx';

import './App.css';

const App = () => {
  return (
    <Router>
      <div className='container'>
        <Routes>
          <Route path='/' element={<StartPage />} />
          <Route path='/home' element={<HomePage />} />
          <Route path='/createCharacter' element={<CreateCharacterPage />} />
          <Route path='/requestsPage' element={<RequestsPage />} />
        </Routes>
      </div>
    </Router>
  );
};

export default App;
