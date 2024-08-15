import React from 'react';
import { BrowserRouter as Router, Route, Routes } from 'react-router-dom';
import RegisterForm from './components/RegisterForm';
import LoginForm from './components/LoginForm';
import ProfilePage from './components/ProfilePage';

const App = () => {
    return (
        <Router>
            <div>
                <h1>My Application</h1>
                <Routes>
                    <Route path="/register" element={<RegisterForm />} />
                    <Route path="/login" element={<LoginForm />} />
                    <Route path="/profile" element={<ProfilePage />} />
                    <Route path="/" element={<RegisterForm />} />
                </Routes>
            </div>
        </Router>
    );
};

export default App;
