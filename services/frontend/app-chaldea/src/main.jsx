import "./api/axiosSetup.ts";

import React from "react";
import ReactDOM from "react-dom/client";
import App from "./components/App/App";
import { Provider } from "react-redux";
import { store } from "./redux/store";

import "./index.css";
import "./styles/cosmetic-frames.css";
import "./styles/cosmetic-backgrounds.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <Provider store={store}>
    <App />
  </Provider>,
);
