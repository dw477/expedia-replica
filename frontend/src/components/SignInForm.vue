<script setup>
import { ref } from 'vue'

defineProps({
  busy: Boolean,
  checking: Boolean,
  error: { type: String, default: '' },
})
const emit = defineEmits(['sign-in', 'create-account'])
const username = ref('')
const password = ref('')

function submit() {
  emit('sign-in', { username: username.value, password: password.value })
  password.value = ''
}
</script>

<template>
  <section class="authentication-section" aria-labelledby="auth-title" :aria-busy="busy">
    <div class="section-heading">
      <p class="step-label">Your travel account</p>
      <h2 id="auth-title">Sign in</h2>
      <p>Sign in to book a stay and see your bookings.</p>
    </div>
    <form id="sign-in-form" class="authentication-form" @submit.prevent="submit">
      <div class="field">
        <label for="username">Username</label>
        <input
          id="username"
          v-model="username"
          name="username"
          type="text"
          autocomplete="username"
          autocapitalize="none"
          :spellcheck="false"
          maxlength="64"
          required
          :disabled="busy"
          :aria-invalid="Boolean(error)"
          :aria-describedby="error ? 'auth-error' : undefined"
        />
      </div>
      <div class="field">
        <label for="password">Password</label>
        <input
          id="password"
          v-model="password"
          name="password"
          type="password"
          autocomplete="current-password"
          maxlength="256"
          required
          :disabled="busy"
          :aria-invalid="Boolean(error)"
          :aria-describedby="error ? 'auth-error' : undefined"
        />
      </div>
      <button class="primary-button" type="submit" :disabled="busy">
        {{ checking ? 'Checking session…' : busy ? 'Signing in…' : 'Sign in' }}
      </button>
    </form>
    <p v-if="error" id="auth-error" class="message-text error-text" role="alert">{{ error }}</p>
    <button class="secondary-button auth-switch" type="button" :disabled="busy" @click="emit('create-account')">Create an account</button>
  </section>
</template>

<style scoped src="../assets/authentication.css"></style>
