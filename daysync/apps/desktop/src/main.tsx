import React from "react";
import ReactDOM from "react-dom/client";

import App from "./App";
import "./styles.css";
import { AppStateProvider } from "./state/AppState";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <AppStateProvider>
      <App />
    </AppStateProvider>
  </React.StrictMode>,
);
