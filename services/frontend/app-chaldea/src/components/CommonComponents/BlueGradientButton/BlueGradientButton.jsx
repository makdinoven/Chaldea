import React from 'react';
import styles from './BlueGradientButton.module.scss';

export default function BlueGradientButton({ text, onClick }) {
  function handleClick(e) {
    onClick(e);
  }

  return (
    <button onClick={handleClick} type='submit' className={styles.button}>
      {text}
    </button>
  );
}
