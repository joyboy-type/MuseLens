import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { MuseLensApp } from "./app/MuseLensApp";
import "./app/globals.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <MuseLensApp />
  </StrictMode>,
);
