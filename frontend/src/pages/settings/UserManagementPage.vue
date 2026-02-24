<script setup lang="ts">
import { inject, ref, computed, onMounted } from 'vue'
import { useAuthStore } from '../../stores/auth'
import { toast } from 'vue-sonner'

const auth = useAuthStore()
const { settingsMetadata, saveSettings } = inject<any>('settings-state')

// OIDC configuration
const discoveryUrl = ref('')
const clientId = ref('')
const clientSecret = ref('')
const rolesClaim = ref('')
const oidcLoading = ref(false)
const oidcError = ref('')
const oidcSuccess = ref('')
const testingOidc = ref(false)
const removingOidc = ref(false)

// Password change
const currentPassword = ref('')
const newPassword = ref('')
const confirmNewPassword = ref('')
const passwordLoading = ref(false)
const passwordError = ref('')

const isOidcConfigured = computed(() => {
  return !!(discoveryUrl.value || settingsMetadata.value?.oidc_discovery_url?.value)
})

const isOidcFromEnv = computed(() => {
  return settingsMetadata.value?.oidc_discovery_url?.source === 'env'
})

function isReadonly(key: string): boolean {
  return settingsMetadata.value?.[key]?.readonly === true
}

const passwordMismatch = computed(() =>
  confirmNewPassword.value !== '' && newPassword.value !== confirmNewPassword.value
)

const userDisplayName = computed(() => {
  return auth.userDisplay || 'admin'
})

onMounted(() => {
  // Pre-fill OIDC fields from metadata
  if (settingsMetadata.value?.oidc_discovery_url?.value) {
    discoveryUrl.value = settingsMetadata.value.oidc_discovery_url.value
  }
  if (settingsMetadata.value?.oidc_client_id?.value) {
    clientId.value = settingsMetadata.value.oidc_client_id.value
  }
  if (settingsMetadata.value?.oidc_client_secret?.value) {
    clientSecret.value = settingsMetadata.value.oidc_client_secret.value
  }
  if (settingsMetadata.value?.oidc_roles_claim?.value) {
    rolesClaim.value = settingsMetadata.value.oidc_roles_claim.value
  }
})

async function testOidcConnection() {
  oidcError.value = ''
  oidcSuccess.value = ''
  testingOidc.value = true
  try {
    const resp = await fetch(discoveryUrl.value)
    if (!resp.ok) {
      oidcError.value = `Discovery URL returned HTTP ${resp.status}.`
      return
    }
    const data = await resp.json()
    if (!data.authorization_endpoint) {
      oidcError.value = 'Invalid OIDC discovery document — missing authorization_endpoint.'
      return
    }
    oidcSuccess.value = 'OIDC discovery URL is valid'
    toast.success('OIDC discovery URL is valid.')
  } catch {
    oidcError.value = 'Failed to reach discovery URL. Check the URL and try again.'
  } finally {
    testingOidc.value = false
  }
}

async function saveOidcSettings() {
  oidcError.value = ''
  oidcLoading.value = true
  try {
    await saveSettings({
      oidc_discovery_url: discoveryUrl.value,
      oidc_client_id: clientId.value,
      oidc_client_secret: clientSecret.value,
      oidc_roles_claim: rolesClaim.value || undefined,
    })
    toast.success('SSO settings saved. Reload to use SSO login.')
  } catch (e: any) {
    oidcError.value = e.message || 'Failed to save OIDC settings.'
  } finally {
    oidcLoading.value = false
  }
}

async function removeOidc() {
  oidcError.value = ''
  removingOidc.value = true
  try {
    await saveSettings({
      oidc_discovery_url: null,
      oidc_client_id: null,
      oidc_client_secret: null,
      oidc_roles_claim: null,
    })
    discoveryUrl.value = ''
    clientId.value = ''
    clientSecret.value = ''
    rolesClaim.value = ''
    toast.success('SSO configuration removed.')
  } catch (e: any) {
    oidcError.value = e.message || 'Failed to remove SSO configuration.'
  } finally {
    removingOidc.value = false
  }
}

async function changePassword() {
  passwordError.value = ''
  if (passwordMismatch.value) {
    passwordError.value = 'Passwords do not match.'
    return
  }
  if (newPassword.value.length < 8) {
    passwordError.value = 'New password must be at least 8 characters.'
    return
  }
  passwordLoading.value = true
  try {
    const resp = await fetch('/auth/local/change-password', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${auth.token}`,
      },
      body: JSON.stringify({
        current_password: currentPassword.value,
        new_password: newPassword.value,
      }),
    })
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}))
      passwordError.value = data.detail || 'Failed to change password.'
      return
    }
    currentPassword.value = ''
    newPassword.value = ''
    confirmNewPassword.value = ''
    toast.success('Password changed successfully.')
  } catch {
    passwordError.value = 'Unable to connect. Please try again.'
  } finally {
    passwordLoading.value = false
  }
}
</script>

<template>
  <div class="space-y-6">
    <!-- Authentication Mode / OIDC Configuration -->
    <div class="rounded-lg bg-white p-6 shadow" data-testid="oidc-section">
      <h3 class="text-lg font-semibold text-gray-900 mb-1">Authentication Mode</h3>
      <p class="text-sm text-gray-500 mb-4">Configure SSO via OpenID Connect to enable organization-level access control.</p>

      <div class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-700">Discovery URL</label>
          <div class="relative">
            <input
              v-model="discoveryUrl"
              type="url"
              placeholder="https://auth.example.com/realms/myrealm/.well-known/openid-configuration"
              :disabled="isReadonly('oidc_discovery_url')"
              data-testid="oidc-discovery-url"
              class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-gray-500 focus:outline-none focus:ring-1 focus:ring-gray-500 disabled:bg-gray-50 disabled:text-gray-500"
            />
            <div v-if="isReadonly('oidc_discovery_url')" class="absolute right-2 top-1/2 -translate-y-1/2 mt-0.5" title="Set via environment variable">
              <svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
            </div>
          </div>
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700">Client ID</label>
          <div class="relative">
            <input
              v-model="clientId"
              type="text"
              :disabled="isReadonly('oidc_client_id')"
              data-testid="oidc-client-id"
              class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-gray-500 focus:outline-none focus:ring-1 focus:ring-gray-500 disabled:bg-gray-50 disabled:text-gray-500"
            />
            <div v-if="isReadonly('oidc_client_id')" class="absolute right-2 top-1/2 -translate-y-1/2 mt-0.5" title="Set via environment variable">
              <svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
            </div>
          </div>
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700">Client Secret</label>
          <div class="relative">
            <input
              v-model="clientSecret"
              type="password"
              :disabled="isReadonly('oidc_client_secret')"
              data-testid="oidc-client-secret"
              class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-gray-500 focus:outline-none focus:ring-1 focus:ring-gray-500 disabled:bg-gray-50 disabled:text-gray-500"
            />
            <div v-if="isReadonly('oidc_client_secret')" class="absolute right-2 top-1/2 -translate-y-1/2 mt-0.5" title="Set via environment variable">
              <svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
            </div>
          </div>
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700">Roles Claim</label>
          <div class="relative">
            <input
              v-model="rolesClaim"
              type="text"
              placeholder="resource_access.errand.roles"
              :disabled="isReadonly('oidc_roles_claim')"
              data-testid="oidc-roles-claim"
              class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-gray-500 focus:outline-none focus:ring-1 focus:ring-gray-500 disabled:bg-gray-50 disabled:text-gray-500"
            />
            <div v-if="isReadonly('oidc_roles_claim')" class="absolute right-2 top-1/2 -translate-y-1/2 mt-0.5" title="Set via environment variable">
              <svg class="h-4 w-4 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
              </svg>
            </div>
          </div>
          <p class="mt-1 text-xs text-gray-500">JSON path to roles array in the JWT. Leave blank for default.</p>
        </div>

        <div v-if="oidcError" class="text-sm text-red-600" data-testid="oidc-error">{{ oidcError }}</div>
        <div v-if="oidcSuccess" class="text-sm text-green-600" data-testid="oidc-success">{{ oidcSuccess }}</div>

        <div class="flex gap-3">
          <button
            type="button"
            @click="testOidcConnection"
            :disabled="!discoveryUrl || testingOidc"
            data-testid="oidc-test"
            class="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
          >
            {{ testingOidc ? 'Testing...' : oidcSuccess ? 'Connection Verified \u2713' : 'Test Connection' }}
          </button>
          <button
            type="button"
            @click="saveOidcSettings"
            :disabled="!discoveryUrl || !clientId || oidcLoading"
            data-testid="oidc-save"
            class="rounded-md bg-gray-800 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
          >
            {{ oidcLoading ? 'Saving...' : 'Save & Enable SSO' }}
          </button>
          <button
            v-if="isOidcConfigured && !isOidcFromEnv"
            type="button"
            @click="removeOidc"
            :disabled="removingOidc"
            data-testid="oidc-remove"
            class="rounded-md border border-red-300 bg-white px-4 py-2 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50"
          >
            {{ removingOidc ? 'Removing...' : 'Remove SSO' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Local Admin Account -->
    <div class="rounded-lg bg-white p-6 shadow" data-testid="local-admin-section">
      <h3 class="text-lg font-semibold text-gray-900 mb-1">Local Admin Account</h3>
      <p class="text-sm text-gray-500 mb-4">Manage your local administrator account.</p>

      <div class="space-y-4">
        <div>
          <label class="block text-sm font-medium text-gray-700">Username</label>
          <p class="mt-1 text-sm text-gray-900" data-testid="admin-username">{{ userDisplayName }}</p>
        </div>

        <h4 class="text-sm font-medium text-gray-900 pt-2">Change Password</h4>

        <div>
          <label class="block text-sm font-medium text-gray-700">Current Password</label>
          <input
            v-model="currentPassword"
            type="password"
            autocomplete="current-password"
            data-testid="current-password"
            class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-gray-500 focus:outline-none focus:ring-1 focus:ring-gray-500"
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700">New Password</label>
          <input
            v-model="newPassword"
            type="password"
            autocomplete="new-password"
            data-testid="new-password"
            class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-gray-500 focus:outline-none focus:ring-1 focus:ring-gray-500"
          />
        </div>

        <div>
          <label class="block text-sm font-medium text-gray-700">Confirm New Password</label>
          <input
            v-model="confirmNewPassword"
            type="password"
            autocomplete="new-password"
            data-testid="confirm-new-password"
            class="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-gray-500 focus:outline-none focus:ring-1 focus:ring-gray-500"
          />
          <p v-if="passwordMismatch" class="mt-1 text-sm text-red-600">Passwords do not match.</p>
        </div>

        <div v-if="passwordError" class="text-sm text-red-600" data-testid="password-error">{{ passwordError }}</div>

        <button
          type="button"
          @click="changePassword"
          :disabled="!currentPassword || !newPassword || !confirmNewPassword || passwordLoading"
          data-testid="change-password-submit"
          class="rounded-md bg-gray-800 px-4 py-2 text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50"
        >
          {{ passwordLoading ? 'Changing...' : 'Change Password' }}
        </button>
      </div>
    </div>
  </div>
</template>
