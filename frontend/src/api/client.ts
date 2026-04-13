import { getFirebaseAuth } from "../auth/firebase";

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function authHeader(): Promise<Record<string, string>> {
  const user = getFirebaseAuth().currentUser;
  if (!user) {
    throw new ApiError(401, "Not authenticated");
  }
  const token = await user.getIdToken();
  return { Authorization: `Bearer ${token}` };
}

export async function apiFetch<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const headers: Record<string, string> = {
    ...((init.headers as Record<string, string>) ?? {}),
    ...(await authHeader()),
  };
  if (init.body) {
    headers["Content-Type"] = "application/json";
  }

  const response = await fetch(path, { ...init, headers });

  if (!response.ok) {
    let detail: string;
    try {
      const body = (await response.json()) as { detail?: string };
      detail = body.detail ?? response.statusText;
    } catch {
      detail = response.statusText;
    }
    throw new ApiError(response.status, detail);
  }

  return (await response.json()) as T;
}
