<script setup>
import { ref } from 'vue'

defineProps({ busy: Boolean, error: { type: String, default: '' } })
const emit = defineEmits(['create-account', 'sign-in'])
const username = ref('')
const displayName = ref('')
const password = ref('')

function submit() {
  emit('create-account', { username: username.value, displayName: displayName.value, password: password.value })
  password.value = ''
}
</script>

<template>
  <section class="authentication-section" aria-labelledby="auth-title" :aria-busy="busy">
    <div class="section-heading">
      <p class="step-label">Your travel account</p>
      <h2 id="auth-title">Create an account</h2>
      <p>Create your account and sign in automatically to start booking.</p>
    </div>
    <form id="create-account-form" class="authentication-form" @submit.prevent="submit">
      <div class="field">
        <label for="display-name">Display name</label>
        <input id="display-name" v-model="displayName" name="display-name" type="text"
          autocomplete="nickname" required :disabled="busy" :aria-invalid="Boolean(error)"
          :aria-describedby="error ? 'auth-error' : undefined" />
      </div>
      <div class="field">
        <label for="username">Username</label>
        <input id="username" v-model="username" name="username" type="text"
          autocomplete="username" autocapitalize="none" :spellcheck="false"
          minlength="3" maxlength="64" required :disabled="busy"
          :aria-invalid="Boolean(error)" :aria-describedby="error ? 'auth-error' : undefined" />
      </div>
      <div class="field">
        <label for="password">Password</label>
        <input id="password" v-model="password" name="password" type="password"
          autocomplete="new-password" minlength="8" maxlength="256" required :disabled="busy"
          :aria-invalid="Boolean(error)"
          :aria-describedby="error ? 'password-help auth-error' : 'password-help'" />
      </div>
      <p id="password-help" class="password-help">At least 8 characters, including an uppercase letter, a digit, and a special character.</p>
      <button class="primary-button" type="submit" :disabled="busy">
        {{ busy ? 'Creating account…' : 'Create account' }}
      </button>
    </form>
    <p v-if="error" id="auth-error" class="message-text error-text" role="alert">{{ error }}</p>
    <button class="secondary-button auth-switch" type="button" :disabled="busy" @click="emit('sign-in')">Already have an account? Sign in</button>
  </section>
</template>

<style scoped src="../assets/authentication.css"></style>
