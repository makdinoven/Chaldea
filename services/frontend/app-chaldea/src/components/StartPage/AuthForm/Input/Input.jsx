import React from 'react';

import './Input.css';

export default function Input({ text }) {
  return <input placeholder={text} className='auth-input' />;
}
