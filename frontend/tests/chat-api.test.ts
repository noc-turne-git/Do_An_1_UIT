import { afterEach, beforeEach, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ getSession: vi.fn() }))
vi.mock('../src/lib/supabase', () => ({ requireSupabase: () => ({ auth: mocks }) }))
import { chatApi } from '../src/features/chat/services/chatApi'

beforeEach(() => {
  mocks.getSession.mockResolvedValue({ data: { session: { access_token: 'test-token' } }, error: null })
  vi.stubGlobal('fetch', vi.fn())
})
afterEach(() => vi.unstubAllGlobals())

it('sends authenticated text and uses the existing conversation for subsequent messages', async () => {
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ message_id: 'm1', conversation_id: 't1' })))
  await chatApi.send('Đi Đà Lạt', 't1')
  expect(fetch).toHaveBeenCalledWith('/api/v1/chat/messages', expect.objectContaining({
    method: 'POST', body: JSON.stringify({ content: 'Đi Đà Lạt', conversation_id: 't1' }),
    headers: { Authorization: 'Bearer test-token', 'Content-Type': 'application/json' },
  }))
})

it('requires sign-in before making a request', async () => {
  mocks.getSession.mockResolvedValue({ data: { session: null }, error: null })
  await expect(chatApi.send('Hello')).rejects.toThrow('đăng nhập')
  expect(fetch).not.toHaveBeenCalled()
})

it('loads history and surfaces API failures without reporting success', async () => {
  vi.mocked(fetch).mockResolvedValueOnce(new Response('[]'))
  expect(await chatApi.history('t1')).toEqual([])
  const log = vi.spyOn(console, 'error').mockImplementation(() => {})
  try {
    vi.mocked(fetch).mockResolvedValueOnce(new Response(JSON.stringify({ error: { message: 'Trip not found' } }), { status: 404 }))
    await expect(chatApi.send('Hello', 't1')).rejects.toThrow('Trip not found')
  } finally {
    log.mockRestore()
  }
})
