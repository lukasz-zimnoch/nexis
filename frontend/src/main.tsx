import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import { AuthProvider } from "./auth/AuthContext";
import { initFirebase } from "./auth/firebase";
import "./index.css";

initFirebase()
  .then(() => {
    createRoot(document.getElementById("root")!).render(
      <StrictMode>
        <BrowserRouter
          future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
        >
          <AuthProvider>
            <App />
          </AuthProvider>
        </BrowserRouter>
      </StrictMode>,
    );
  })
  .catch((error: unknown) => {
    console.error("Failed to bootstrap Firebase:", error);
    const root = document.getElementById("root");
    if (root) {
      root.textContent =
        "Failed to load application configuration. Please try again later.";
    }
  });
