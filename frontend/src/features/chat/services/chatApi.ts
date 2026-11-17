import { supabase } from '../../../lib/supabase'

const ANONYMOUS_SESSION_STORAGE_KEY = 'travelio.anonymous_session_id'
const apiBaseUrl = import.meta.env.VITE_API_BASE_URL ?? ''
let anonymousSessionPromise: Promise<string> | null = null

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
  input_id: string
  revision: number
  workflow_id: string | null
  episode_id: string | null
  workflow_status: 'parsing' | 'clarifying' | 'planning' | 'validating' | 'awaiting_relaxation' | 'completed' | 'failed' | null
  questions: Array<{ question_id: string | null; episode_id: string | null; status: string; question: string; fields: string[]; options: unknown[] }>
  clarification_round: number
  destination_round: number
  remaining_destination_rounds: number
  selection_policy: Record<string, unknown> | null
  transitions: number | null
}

export type ChatTurnContext = {
  input_id: string
  workflow_id?: string
  episode_id?: string
  question_id?: string
  expected_revision?: number
  expected_transitions?: number
}

function storedAnonymousSessionId(): string | null {
  return localStorage.getItem(ANONYMOUS_SESSION_STORAGE_KEY)
}

async function getAnonymousSessionId(): Promise<string> {
  const existing = storedAnonymousSessionId()
  if (existing) return existing
  if (!anonymousSessionPromise) {
    anonymousSessionPromise = fetch(`${apiBaseUrl}/api/v1/chat/anonymous-sessions`, {
      method: 'POST',
      signal: AbortSignal.timeout(10000),
    }).then(async (response) => {
      if (!response.ok) throw new Error('Không thể tạo phiên chat ẩn danh. Vui lòng thử lại.')
      const payload = await response.json() as { anonymous_session_id: string }
      localStorage.setItem(ANONYMOUS_SESSION_STORAGE_KEY, payload.anonymous_session_id)
      return payload.anonymous_session_id
    }).finally(() => { anonymousSessionPromise = null })
  }
  return anonymousSessionPromise
}

async function request<T>(path: string, body?: unknown): Promise<T> {
  const { data, error } = supabase
    ? await supabase.auth.getSession()
    : { data: { session: null }, error: null }
  if (error) throw new Error('Không thể kiểm tra phiên đăng nhập. Vui lòng thử lại.')
  const accessToken = data.session?.access_token
  const anonymousSessionId = accessToken ? null : await getAnonymousSessionId()
  const response = await fetch(`${apiBaseUrl}/api/v1/chat${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    headers: {
      ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : { 'X-Anonymous-Session-ID': anonymousSessionId! }),
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
  send: (content: string, conversationId?: string, context?: ChatTurnContext) => request<ChatTurn>('/messages', {
    content,
    conversation_id: conversationId,
    input_id: context?.input_id ?? crypto.randomUUID(),
    workflow_id: context?.workflow_id,
    episode_id: context?.episode_id,
    question_id: context?.question_id,
    expected_revision: context?.expected_revision,
    expected_transitions: context?.expected_transitions,
  }),
  history: (conversationId: string) => request<ChatMessage[]>(`/conversations/${encodeURIComponent(conversationId)}/messages`),
}
