import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "./styles/base.css";

import { App } from "./App";

const root = document.getElementById("root");
if (root === null) throw new Error("no #root element");
createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
