import React from 'react';

import styles from './LogButton.module.css';

export default function LogButton({ text, isActive, onClick }) {
  return (
    <button
      // className={`button ${isActive ? 'button_active' : 'button_disabled'}`}
      className={`${styles.button} ${
        isActive ? styles.active : styles.disabled
      }`}
      onClick={onClick}
    >
      {text}
    </button>
  );
}
