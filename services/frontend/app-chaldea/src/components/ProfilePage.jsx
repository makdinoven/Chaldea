import React, { useState, useEffect } from 'react';
import axios from 'axios';

const ProfilePage = () => {
    const [username, setUsername] = useState('');
    const [message, setMessage] = useState('');

    useEffect(() => {
        const fetchUserData = async () => {
            try {
                const token = localStorage.getItem('accessToken');
                const response = await axios.get('/api/users/me', {
                    headers: {
                        Authorization: `Bearer ${token}`
                    }
                });
                setUsername(response.data.username);
            } catch (error) {
                setMessage('Failed to fetch user data: ' + error.response.data.detail);
            }
        };

        fetchUserData();
    }, []);

    return (
        <div>
            <h2>Profile Page</h2>
            {username ? (
                <p>Welcome, {username}!</p>
            ) : (
                <p>{message}</p>
            )}
        </div>
    );
};

export default ProfilePage;
