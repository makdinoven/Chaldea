import React from 'react';
import styles from './Input.module.css';

export default function Input({
  text,
  type = 'text',
  maxLength = 200,
  minValue = 1,
  maxValue = 400,
  value,
  onChange,
  id,
  isRequired,
}) {
  const handleChange = (e) => {
    const { value } = e.target;
    if (type === 'number') {
      // Ограничиваем ввод чисел по диапазону
      const numericValue = parseInt(value, 10);
      if (numericValue < minValue || numericValue > maxValue) {
        return; // Не обновляем значение, если оно выходит за пределы диапазона
      }
    }
    onChange(e);
  };
  return (
    <input
      required={isRequired}
      placeholder={text}
      type={type}
      maxLength={maxLength}
      value={value}
      onChange={handleChange}
      className={styles.input}
      id={id}
      min={type === 'number' ? minValue : undefined}
      max={type === 'number' ? maxValue : undefined}
    />
  );
}
