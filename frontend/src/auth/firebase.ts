import { initializeApp, type FirebaseApp } from "firebase/app";
import { getAuth, type Auth } from "firebase/auth";

interface FirebaseWebConfig {
  apiKey: string;
  authDomain: string;
  projectId: string;
}

let firebaseApp: FirebaseApp | null = null;
let firebaseAuth: Auth | null = null;

// Fetched at bootstrap from the backend's /config.json endpoint so the
// Firebase Web SDK values live next to the rest of the runtime config
// (Cloud Run env → Terraform) instead of being baked into the static bundle.
export async function initFirebase(): Promise<void> {
  if (firebaseApp) return;
  const response = await fetch("/config.json");
  if (!response.ok) {
    throw new Error(`Failed to load Firebase config (${response.status})`);
  }
  const config: FirebaseWebConfig = await response.json();
  firebaseApp = initializeApp(config);
  firebaseAuth = getAuth(firebaseApp);
}

export function getFirebaseAuth(): Auth {
  if (!firebaseAuth) {
    throw new Error("Firebase not initialised — call initFirebase() first");
  }
  return firebaseAuth;
}
