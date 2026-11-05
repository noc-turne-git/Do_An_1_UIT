import { requireSupabase } from '../../../lib/supabase'

export type ChatMessage = {
  message_id: string
  conversation_id: string
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

export type ChatTurn = ChatMessage & {
  assistant: ChatMessage
  trip_summary: ChatMessage | null
  parser_status: 'clarifying' | 'ready' | 'error'
  missing_fields: string[]
  error_code: string | null
}

async function request<T>(path: string, body?: unknown): Promise<T> {
  const { data, error } = await requireSupabase().auth.getSession()
  if (error || !data.session) throw new Error('Vui lòng đăng nhập để sử dụng chat.')
  const response = await fetch(`${import.meta.env.VITE_API_BASE_URL ?? ''}/api/v1/chat${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: {
      Authorization: `Bearer ${data.session.access_token}`,
      ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(90000),
  })
  if (!response.ok) {
    console.error('chat.request_failed', { status: response.status, requestId: response.headers.get('X-Request-ID') })
    const payload = await response.json().catch(() => null)
    throw new Error(payload?.error?.message ?? 'Không thể kết nối chat. Vui lòng thử lại.')
  }
  return response.json() as Promise<T>
}

export const chatApi = {
  send: (content: string, conversationId?: string) => request<ChatTurn>('/messages', { content, conversation_id: conversationId }),
  history: (conversationId: string) => request<ChatMessage[]>(`/conversations/${encodeURIComponent(conversationId)}/messages`),
}
