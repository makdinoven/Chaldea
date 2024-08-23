import React from 'react';

import './FormButton.css';

export default function FormButton({ text, onClick }) {
  return (
    <button className='form-button' onClick={onClick}>
      {text}
    </button>
  );
}
