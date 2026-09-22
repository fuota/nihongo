export const API_URL = process.env.EXPO_PUBLIC_API_URL;

export class ApiError extends Error {}

export async function apiFetch(
  path: string,
  token: string | null,
  init?: RequestInit
): Promise<any> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers ?? {}),
    },
  });

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new ApiError(data ? JSON.stringify(data) : `Request failed: ${response.status}`);
  }

  return data;
}
