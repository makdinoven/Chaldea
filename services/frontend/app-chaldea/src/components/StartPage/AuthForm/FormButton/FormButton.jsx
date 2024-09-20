import React from 'react';
import styles from './FormButton.module.css';

export default function FormButton({ text }) {
  return (
    <button type='submit' className={styles.button}>
      {text}
    </button>
  );
}
