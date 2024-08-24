import React from 'react';
import './FormButton.css';

export default function FormButton({ text }) {
  return (
    <button type="submit" className='form-button'>
      {text}
    </button>
  );
}
