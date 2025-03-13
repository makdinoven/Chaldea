import React from 'react';
import styles from './Select.module.scss';

export default function Select({ options, value, onChange }) {
  return (
    <select
      className={styles.select}
      name='sex'
      id='sex'
      value={value}
      onChange={onChange}
    >
      {options.map((option, index) => (
        <option
          key={index}
          value={option.value}
          disabled={option.isDisabled} // Делаем опцию недоступной
        >
          {option.name}
        </option>
      ))}
    </select>
  );
}
