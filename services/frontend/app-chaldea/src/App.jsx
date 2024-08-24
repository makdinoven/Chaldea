import React from 'react';
import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'; // Импорт компонентов для маршрутизации
import StartPage from './components/StartPage/StartPage.jsx';
import HomePage from './components/HomePage/HomePage.jsx'; // Импорт нового компонента

import './App.css';

const App = () => {
  return (
    <Router>
      <div className='container'>
        <Routes>
          <Route path="/" element={<StartPage />} /> {/* Стартовая страница */}
          <Route path="/home" element={<HomePage />} /> {/* Главная страница */}
        </Routes>
      </div>
    </Router>
  );
};

export default App;
