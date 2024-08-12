import React, { useState } from 'react';
import './AuthForm.css';

const AuthForm = () => {
  const [isRegister, setIsRegister] = useState(true);
  const [formData, setFormData] = useState({
    username: '',
    email: '',
    password: '',
  });

  const handleChange = (e) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const url = isRegister ? '/api/register' : '/api/login';
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(formData),
      });
      const data = await response.json();
      console.log(data);
    } catch (error) {
      console.error('Error:', error);
    }
  };

  return (
    <div className='auth-form'>
      <h2 className='auth-form__name'>{isRegister ? 'Register' : 'Login'}</h2>
      <form className='form' onSubmit={handleSubmit}>
        <div className='form__input'>
          <label>Username:</label>
          <input
            type='text'
            name='username'
            value={formData.username}
            onChange={handleChange}
            required
          />
        </div>

        {isRegister && (
          <div className='form__input'>
            <label>Email:</label>
            <input
              type='email'
              name='email'
              value={formData.email}
              onChange={handleChange}
              required
            />
          </div>
        )}
        <div className='form__input'>
          <label>Password:</label>
          <input
            type='password'
            name='password'
            value={formData.password}
            onChange={handleChange}
            required
          />
        </div>

        <button className='form__button' type='submit'>
          {isRegister ? 'Register' : 'Login'}
        </button>
      </form>
      <button
        className='button-switch'
        onClick={() => setIsRegister(!isRegister)}
      >
        {isRegister ? 'Switch to Login' : 'Switch to Register'}
      </button>
    </div>
  );
};

export default AuthForm;
