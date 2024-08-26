import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'; // Импорт компонентов для маршрутизации
import StartPage from '../StartPage/StartPage.jsx';
import HomePage from '../HomePage/HomePage.jsx';

import './App.css';

const App = () => {
  return (
    <Router>
      <div className='container'>
        {/* <Routes>
          <Route path="/" element={<StartPage />} /> 
          <Route path="/home" element={<HomePage />} /> 
        </Routes> */}
        <StartPage />
      </div>
    </Router>
  );
};

export default App;
