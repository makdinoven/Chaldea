import React from 'react';

import './LogButton.css';

export default function LogButton({ text, isActive, onClick }) {
  return (
    <button
      className={`button ${isActive ? 'button_active' : 'button_disabled'}`}
      onClick={onClick}
    >
      {text}
    </button>
  );
}
