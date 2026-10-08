import { requestJson } from './request.js'

// Mirrors backend/models/chat.py; OpenAPI is the HTTP contract source of truth.
export const MAX_CHAT_MESSAGE_LENGTH = 8000
const MAX_CHAT_MESSAGES = 21
const MAX_CHAT_CHARACTERS = 32000
const MAX_CHAT_SUGGESTIONS = 3
const MAX_CHAT_SUGGESTION_LENGTH = 160

export async function sendChat(messages, conversationId) {
  // Retain complete recent exchanges, always ending with the new user message.
  let context = messages.slice(-MAX_CHAT_MESSAGES).map(({ role, content }) => ({ role, content }))
  while (context.length > 1 && context.reduce((length, message) => length + [...message.content].length, 0) > MAX_CHAT_CHARACTERS) {
    context = context.slice(2)
  }
  const response = await requestJson('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ messages: context, conversation_id: conversationId }),
  })
  if (typeof response?.reply !== 'string' || !response.reply.trim() || [...response.reply].length > MAX_CHAT_MESSAGE_LENGTH) {
    throw new Error('The travel assistant returned an unexpected reply. Please try again.')
  }
  if (!Array.isArray(response.suggestions) || response.suggestions.length > MAX_CHAT_SUGGESTIONS || response.suggestions.some((question) => (
    typeof question !== 'string' || !question.trim() || [...question].length > MAX_CHAT_SUGGESTION_LENGTH
  ))) {
    throw new Error('The travel assistant returned unexpected suggestions. Please try again.')
  }
  const suggestions = response.suggestions.map((question) => question.trim())
  if (new Set(suggestions.map((question) => question.toLowerCase())).size !== suggestions.length) {
    throw new Error('The travel assistant returned unexpected suggestions. Please try again.')
  }
  return { reply: response.reply.trim(), suggestions }
}
