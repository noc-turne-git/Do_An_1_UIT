import { afterEach, beforeEach, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ getSession: vi.fn() }))
vi.mock('../src/lib/supabase', () => ({ supabase: { auth: mocks } }))
import { chatApi } from '../src/features/chat/services/chatApi'

beforeEach(() => {
  mocks.getSession.mockResolvedValue({ data: { session: { access_token: 'test-token' } }, error: null })
  vi.stubGlobal('fetch', vi.fn())
  localStorage.clear()
})
afterEach(() => vi.unstubAllGlobals())

it('sends authenticated text and uses the existing conversation for subsequent messages', async () => {
  vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ message_id: 'm1', conversation_id: 't1' })))
  await chatApi.send('Đi Đà Lạt', 't1', { input_id: 'input-1' })
  expect(fetch).toHaveBeenCalledWith('/api/v1/chat/messages', expect.objectContaining({
    method: 'POST', body: JSON.stringify({ content: 'Đi Đà Lạt', conversation_id: 't1', input_id: 'input-1' }),
    headers: { Authorization: 'Bearer test-token', 'Content-Type': 'application/json' },
  }))
})

it('creates and reuses an anonymous session when signed out', async () => {
  mocks.getSession.mockResolvedValue({ data: { session: null }, error: null })
  vi.mocked(fetch)
    .mockResolvedValueOnce(new Response(JSON.stringify({ anonymous_session_id: 'guest-1' }), { status: 201 }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ message_id: 'm1', conversation_id: 't1' })))
    .mockResolvedValueOnce(new Response('[]'))
  await chatApi.send('Hello')
  await chatApi.history('t1')
  expect(fetch).toHaveBeenNthCalledWith(1, '/api/v1/chat/anonymous-sessions', expect.objectContaining({ method: 'POST' }))
  expect(fetch).toHaveBeenNthCalledWith(2, '/api/v1/chat/messages', expect.objectContaining({
    headers: expect.objectContaining({ 'X-Anonymous-Session-ID': 'guest-1' }),
  }))
  expect(fetch).toHaveBeenNthCalledWith(3, '/api/v1/chat/conversations/t1/messages', expect.objectContaining({
    headers: expect.objectContaining({ 'X-Anonymous-Session-ID': 'guest-1' }),
  }))
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
