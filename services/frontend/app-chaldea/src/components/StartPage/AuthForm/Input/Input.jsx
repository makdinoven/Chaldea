import React from 'react';
import './Input.css';

export default function Input({ text, type = 'text', value, onChange }) {
  return <input placeholder={text} type={type} value={value} onChange={onChange} className='auth-input' />;
}
