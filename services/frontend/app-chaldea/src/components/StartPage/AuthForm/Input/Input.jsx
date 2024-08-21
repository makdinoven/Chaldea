import React from 'react';

import './Input.css';

export default function Input({ text, id, type }) {
  return (
    <div className='input-container'>
      <label className='input-label' htmlFor={id}>
        {text}
      </label>
      <input id={id} className='auth-input' type={type} />
    </div>
  );
}
