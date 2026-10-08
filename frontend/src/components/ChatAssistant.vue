<script setup>
import { computed, nextTick, ref } from 'vue'
import { MAX_CHAT_MESSAGE_LENGTH, sendChat } from '../api/chat.js'

const messages = ref([])
const conversationId = ref(crypto.randomUUID())
const draft = ref('')
const error = ref('')
const isLoading = ref(false)
const isOpen = ref(false)
const launcher = ref(null)
const popup = ref(null)
const transcript = ref(null)
const composer = ref(null)
let returnFocus = null
const canSend = computed(() => Boolean(draft.value.trim()) && !isLoading.value)
const initialSuggestions = [
  'Which saved hotels in ZIP 02108 have a room on October 10, 2026?',
  'Show the cheapest saved hotels for October 10–12, 2026 in ZIP 16802',
  'Do the saved hotels have availability after October 14, 2026?',
]
const suggestions = ref([...initialSuggestions])

async function openChat(event) {
  returnFocus = event?.currentTarget || launcher.value
  isOpen.value = true
  await scrollToLatest()
  if (isLoading.value) popup.value?.focus()
  else composer.value?.focus()
}

function closeChat() {
  isOpen.value = false
  returnFocus?.focus()
}

function toggleChat(event) {
  if (isOpen.value) closeChat()
  else return openChat(event)
}

defineExpose({ openChat, isOpen })

async function scrollToLatest() {
  await nextTick()
  if (transcript.value) transcript.value.scrollTop = transcript.value.scrollHeight
}

async function submitMessage() {
  if (isLoading.value) return
  const content = draft.value.trim()
  if (!content) {
    error.value = 'Enter a message to start chatting.'
    return
  }
  if ([...content].length > MAX_CHAT_MESSAGE_LENGTH) {
    error.value = 'Keep your message under 8000 characters.'
    return
  }

  error.value = ''
  isLoading.value = true
  messages.value.push({ role: 'user', content })
  draft.value = ''
  await scrollToLatest()
  try {
    const { reply, suggestions: nextSuggestions } = await sendChat(messages.value, conversationId.value)
    messages.value.push({ role: 'assistant', content: reply })
    suggestions.value = nextSuggestions
  } catch (requestError) {
    // Failed exchanges are not sent again as history; restore the draft for retry.
    messages.value.pop()
    draft.value = content
    error.value = requestError.message || 'The travel assistant could not reply. Please try again.'
  } finally {
    isLoading.value = false
    await scrollToLatest()
    // Closing the popup while waiting must not move focus when a reply arrives.
    if (isOpen.value) composer.value?.focus()
  }
}

function handleEnter(event) {
  if (event.shiftKey || event.isComposing) return
  event.preventDefault()
  submitMessage()
}

function useSuggestion(question) {
  if (isLoading.value) return
  draft.value = question
  submitMessage()
}

function startNewChat() {
  if (isLoading.value) return
  messages.value = []
  suggestions.value = [...initialSuggestions]
  conversationId.value = crypto.randomUUID()
  draft.value = ''
  error.value = ''
  composer.value?.focus()
}
</script>

<template>
  <button
    ref="launcher"
    class="chat-launcher"
    type="button"
    aria-haspopup="dialog"
    aria-controls="chat-panel"
    :aria-expanded="isOpen"
    :aria-label="isOpen ? 'Close travel assistant' : 'Open travel assistant'"
    @click="toggleChat"
  >
    <span class="chat-launcher-icon" aria-hidden="true">✦</span>
    <span>Travel assistant</span>
    <span v-if="isLoading" class="chat-loading-dot" aria-hidden="true" />
  </button>

  <section
    v-if="isOpen"
    id="chat-panel"
    ref="popup"
    class="chat-assistant"
    role="dialog"
    aria-labelledby="chat-title"
    tabindex="-1"
    @keydown.esc.stop.prevent="closeChat"
  >
    <header class="chat-heading">
      <div class="chat-heading-label">
        <span class="chat-icon" aria-hidden="true">✦</span>
        <div>
          <p class="chat-eyebrow">A little help along the way</p>
          <h2 id="chat-title">Your travel assistant</h2>
        </div>
      </div>
      <div class="chat-heading-actions">
        <button
          class="chat-reset"
          type="button"
          :disabled="isLoading || (!messages.length && !draft && !error)"
          @click="startNewChat"
        >New chat</button>
        <button class="chat-close" type="button" aria-label="Close chat popup" @click="closeChat">
          <span aria-hidden="true">×</span>
        </button>
      </div>
    </header>

    <div ref="transcript" class="chat-body" tabindex="0" aria-label="Chat messages and suggestions">
      <div
        class="chat-transcript"
        role="log"
        aria-label="Travel assistant conversation"
        aria-live="polite"
        aria-relevant="additions"
        :aria-busy="isLoading"
      >
        <article
          v-for="(message, index) in messages"
          :key="index"
          class="chat-message"
          :class="`chat-message-${message.role}`"
        >
          <span class="chat-speaker">{{ message.role === 'user' ? 'You' : 'Travel assistant' }}</span>
          <p>{{ message.content }}</p>
        </article>
      </div>
      <p v-if="isLoading" class="chat-progress" role="status">Travel assistant is thinking…</p>
      <p v-if="error" id="chat-error" class="message-text error-text" role="alert">{{ error }}</p>
      <div v-if="!isLoading && suggestions.length" :class="messages.length ? 'chat-followups' : 'chat-welcome'">
        <p>{{ messages.length ? 'Keep exploring' : 'Where shall we go next?' }}</p>
        <div class="chat-suggestions" aria-label="Suggested questions">
          <button
            v-for="question in suggestions"
            :key="question"
            class="secondary-button"
            type="button"
            @click="useSuggestion(question)"
          >{{ question }} <span aria-hidden="true">↗</span></button>
        </div>
      </div>
    </div>

    <form class="chat-form" @submit.prevent="submitMessage">
      <label for="chat-message">Your message</label>
      <div class="chat-composer">
        <textarea
          id="chat-message"
          ref="composer"
          v-model="draft"
          name="chat-message"
          rows="2"
          :maxlength="MAX_CHAT_MESSAGE_LENGTH"
          placeholder="Ask a question or tell me about your trip…"
          :disabled="isLoading"
          :aria-describedby="error ? 'chat-error' : undefined"
          :aria-invalid="Boolean(error)"
          @keydown.enter="handleEnter"
        />
        <button class="primary-button" type="submit" :disabled="!canSend">
          {{ isLoading ? 'Sending…' : error ? 'Try again' : 'Send' }}
          <span aria-hidden="true">→</span>
        </button>
      </div>
    </form>
  </section>
</template>

<style scoped>
.chat-launcher {
  position: fixed;
  z-index: 1200;
  right: 24px;
  bottom: calc(24px + env(safe-area-inset-bottom, 0px));
  display: flex;
  min-height: 56px;
  align-items: center;
  gap: 10px;
  border: 1px solid #191932;
  border-radius: 30px;
  padding: 12px 20px;
  color: #fff;
  background: #191932;
  box-shadow: 0 8px 24px #19193226;
  font-size: 14px;
}
.chat-launcher:hover {
  background: #303054;
}
.chat-launcher-icon {
  color: #ffe331;
  font-size: 25px;
  line-height: 1;
}
.chat-loading-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #ffe331;
}
.chat-assistant {
  position: fixed;
  z-index: 1200;
  right: 24px;
  bottom: calc(96px + env(safe-area-inset-bottom, 0px));
  display: flex;
  width: min(440px, calc(100vw - 48px));
  height: min(640px, calc(100vh - 120px));
  height: min(640px, calc(100dvh - 120px - env(safe-area-inset-bottom, 0px)));
  overflow: hidden;
  flex-direction: column;
  margin: 0;
  border: 1px solid #dedde1;
  border-radius: 20px;
  background: #fff;
  box-shadow: 0 16px 60px #19193229;
}
.chat-heading,
.chat-heading-label {
  display: flex;
  align-items: center;
  gap: 10px;
}
.chat-heading {
  flex-shrink: 0;
  justify-content: space-between;
  gap: 6px;
  border-bottom: 1px solid #e9e7e1;
  padding: 16px;
}
.chat-heading-label {
  min-width: 0;
}
.chat-heading-actions {
  display: flex;
  flex-shrink: 0;
  align-items: center;
  gap: 4px;
}
.chat-reset,
.chat-close {
  border: 0;
  padding: 8px;
  background: transparent;
}
.chat-reset {
  color: #1464d5;
  font-size: 12px;
}
.chat-close {
  min-width: 36px;
  color: #62616d;
  font-size: 26px;
  line-height: 1;
}
.chat-reset:hover:not(:disabled),
.chat-close:hover {
  background: #f4f3f8;
}
.chat-eyebrow {
  margin-bottom: 5px;
  color: #62616d;
  font-size: 9px;
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}
.chat-icon {
  display: grid;
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  place-items: center;
  border-radius: 11px;
  color: #fff;
  background: #191932;
  font-size: 22px;
}
.chat-heading h2 {
  margin: 0;
  font-size: 18px;
  line-height: 1.2;
}
.chat-body {
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  flex: 1;
  padding: 18px;
  background: #faf9f5;
}
.chat-welcome {
  padding: 4px 0;
}
.chat-welcome > p {
  margin: 8px 0 16px;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: 24px;
}
.chat-followups > p {
  margin: 20px 0 12px;
  color: #62616d;
  font-size: 12px;
  font-weight: 700;
}
.chat-suggestions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.chat-suggestions button {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  padding: 10px 14px;
  text-align: left;
  font-size: 12px;
}
.chat-transcript {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin: 12px 0;
}
.chat-transcript:empty {
  margin: 0;
  padding: 0;
}
.chat-message {
  max-width: 92%;
  padding: 12px 14px;
  border-radius: 14px;
  background: #f4f3f8;
}
.chat-message-user {
  align-self: flex-end;
  background: #fff7cf;
}
.chat-message-assistant {
  align-self: flex-start;
}
.chat-speaker {
  font-size: 12px;
  font-weight: 700;
}
.chat-message p {
  margin: 8px 0 0;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
  line-height: 1.6;
  font-size: 13px;
}
.chat-progress {
  color: #62616d;
  font-size: 14px;
}
.chat-form {
  flex-shrink: 0;
  margin: 0;
  border-top: 1px solid #e9e7e1;
  padding: 14px 18px;
}
.chat-form label {
  display: block;
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 700;
}
.chat-composer {
  display: flex;
  align-items: flex-end;
  gap: 8px;
}
.chat-composer textarea {
  width: 100%;
  min-width: 0;
  min-height: 74px;
  max-height: 128px;
  resize: vertical;
  border: 1px solid #aaa9b0;
  border-radius: 10px;
  padding: 12px;
  color: #191932;
  background: #fff;
  font: inherit;
  font-size: 14px;
  line-height: 1.5;
}
.chat-composer button {
  flex-shrink: 0;
  padding: 11px 14px;
  font-size: 13px;
}
.chat-composer textarea:focus-visible,
.chat-body:focus-visible {
  outline: 3px solid #3159ca;
  outline-offset: 3px;
}
@media (max-width: 480px) {
  .chat-launcher {
    right: 12px;
    bottom: calc(12px + env(safe-area-inset-bottom, 0px));
  }
  .chat-assistant {
    right: 12px;
    bottom: calc(80px + env(safe-area-inset-bottom, 0px));
    width: calc(100vw - 24px);
    height: min(640px, calc(100vh - 96px));
    height: min(640px, calc(100dvh - 96px - env(safe-area-inset-bottom, 0px)));
  }
  .chat-heading {
    padding: 12px;
  }
  .chat-heading h2 {
    font-size: 16px;
  }
  .chat-eyebrow {
    font-size: 8px;
  }
  .chat-icon {
    display: none;
  }
  .chat-message {
    max-width: 96%;
  }
}
</style>
