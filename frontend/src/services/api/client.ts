export type ApiError = { message: string; status?: number }

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

export async function apiRequest<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch {
    throw { message: 'Unable to connect. Please try again.' } satisfies ApiError
  }
  if (!response.ok) {
    let message = response.statusText || 'Something went wrong'
    try { message = (await response.json()).message ?? message } catch { /* response has no JSON body */ }
    throw { message, status: response.status } satisfies ApiError
  }
  return response.json() as Promise<T>
}
