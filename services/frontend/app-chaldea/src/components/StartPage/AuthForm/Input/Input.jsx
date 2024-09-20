import React from 'react';
import styles from './Input.module.css';

export default function Input({ text, type = 'text', value, onChange, id }) {
  return (
    <input
      placeholder={text}
      type={type}
      value={value}
      onChange={onChange}
      className={styles.input}
      id={id}
    />
  );
}
