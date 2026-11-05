import { createClient } from '@supabase/supabase-js'

const url = import.meta.env.VITE_SUPABASE_URL
const key = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY
export const supabase = url && key ? createClient(url, key) : null

export function requireSupabase() {
  if (!supabase) throw new Error('Please configure VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY in .env.local.')
  return supabase
}

export async function requireGoogleProvider() {
  requireSupabase()
  const response = await fetch(`${url.replace(/\/$/, '')}/auth/v1/settings`, {
    headers: { apikey: key },
    signal: AbortSignal.timeout(10000),
  })
  if (!response.ok) throw new Error('Could not check Google sign-in availability. Please try again.')
  const settings = await response.json()
  if (settings.external?.google !== true) {
    throw new Error('Đăng nhập Google chưa được bật. Vui lòng liên hệ quản trị viên để cấu hình Google trong Supabase Auth.')
  }
}
