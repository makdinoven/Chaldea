import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './components/App/App.jsx';
import { UserProvider } from '../src/hooks/UserContext.jsx';

import './index.css';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <UserProvider>
      <App />
    </UserProvider>
  </React.StrictMode>

  // <UserProvider>
  //   <App />
  // </UserProvider>
);
