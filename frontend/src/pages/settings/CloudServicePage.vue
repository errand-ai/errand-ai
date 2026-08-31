<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, computed } from 'vue'
import { toast } from 'vue-sonner'
import { useAuthStore } from '../../stores/auth'
import { useTaskStore } from '../../stores/tasks'
import { fetchWebhookTriggers, type WebhookTrigger } from '../../composables/useApi'

const auth = useAuthStore()
const taskStore = useTaskStore()

interface CloudEndpoint {
  integration: string
  endpoint_type: string
  url: string
  token: string
}

interface PaymentWarning {
  alert: string
  plan?: string
  attempt_count?: number
  next_retry_at?: string | null
  final_attempt?: boolean
}

interface CloudStatus {
  status: 'not_configured' | 'connected' | 'disconnected' | 'error'
  tenant_id?: string
  email?: string
  endpoints?: CloudEndpoint[]
  slack_configured?: boolean
  detail?: string
  endpoint_error?: { detail: string }
  // `active`/`expires_at` are optional: /api/cloud/status may return a
  // subscription object carrying only `payment_warning` when the cloud
  // subscription fetch yields nothing but a payment warning is stored.
  subscription?: { active?: boolean; expires_at?: string | null; payment_warning?: PaymentWarning }
}

interface DeviceGrant {
  user_code: string
  verification_uri: string
  verification_uri_complete: string
  expires_in?: number
}

type DeviceGrantStatus = 'none' | 'pending' | 'connected' | 'denied' | 'expired' | 'error'

const cloudStatus = ref<CloudStatus>({ status: 'not_configured' })
const loading = ref(true)
const disconnecting = ref(false)
const connecting = ref(false)
const triggers = ref<WebhookTrigger[]>([])

// Device authorization grant (RFC 8628). The backend holds the device code and
// polls the cloud for us; the page only ever sees the user-facing code and URL,
// neither of which is a credential.
const deviceGrant = ref<DeviceGrant | null>(null)
const deviceStatus = ref<DeviceGrantStatus>('none')
const deviceDetail = ref<string | null>(null)
const DEVICE_POLL_MS = 3000
let devicePoll: ReturnType<typeof setInterval> | null = null

const isConnected = computed(() => cloudStatus.value.status === 'connected' || cloudStatus.value.status === 'disconnected')
const isError = computed(() => cloudStatus.value.status === 'error')
const isNotConfigured = computed(() => cloudStatus.value.status === 'not_configured')
const webhookTriggers = computed(() =>
  triggers.value.filter((t) => t.source === 'jira' || t.source === 'github'),
)
const hasEndpoints = computed(
  () => (cloudStatus.value.endpoints?.length ?? 0) > 0 || webhookTriggers.value.length > 0,
)
const hasEndpointError = computed(() => !!cloudStatus.value.endpoint_error?.detail)
const isPendingGrant = computed(() => deviceStatus.value === 'pending' && !!deviceGrant.value)
const deviceFailureMessage = computed(() => {
  switch (deviceStatus.value) {
    case 'denied':
      return 'Authorisation was refused. Start again to retry.'
    case 'expired':
      return 'The code expired before it was approved. Start again to retry.'
    case 'error':
      return deviceDetail.value
        ? `Connection failed: ${deviceDetail.value}`
        : 'Connection failed. Start again to retry.'
    default:
      return null
  }
})
function formatDate(iso: string): string | null {
  const d = new Date(iso)
  if (isNaN(d.getTime())) return null
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' })
}
const subscriptionExpiry = computed(() => {
  const expiresAt = cloudStatus.value.subscription?.expires_at
  if (!expiresAt) return null
  return formatDate(expiresAt)
})
const subscriptionInactive = computed(() => cloudStatus.value.subscription?.active === false)
const paymentWarning = computed(() => cloudStatus.value.subscription?.payment_warning ?? null)
const paymentWarningFinal = computed(() => paymentWarning.value?.final_attempt === true)
const paymentWarningMessage = computed(() => {
  const w = paymentWarning.value
  if (!w) return null
  if (w.final_attempt) return 'Payment failed — subscription expired'
  const retry = w.next_retry_at ? formatDate(w.next_retry_at) : null
  return retry ? `Payment failed — retrying ${retry}` : 'Payment failed'
})

async function apiFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> || {}),
  }
  if (auth.token) {
    headers['Authorization'] = `Bearer ${auth.token}`
  }
  return fetch(url, { ...options, headers })
}

async function fetchStatus() {
  loading.value = true
  try {
    const [statusResp, triggersResp] = await Promise.all([
      apiFetch('/api/cloud/status'),
      fetchWebhookTriggers().catch(() => [] as WebhookTrigger[]),
    ])
    if (statusResp.ok) {
      cloudStatus.value = await statusResp.json()
      taskStore.cloudStatus = cloudStatus.value.status
    }
    triggers.value = triggersResp
  } catch {
    // Silent failure — status display is best-effort
  } finally {
    loading.value = false
  }
}

function stopDevicePolling() {
  if (devicePoll !== null) {
    clearInterval(devicePoll)
    devicePoll = null
  }
}

async function pollDeviceStatus() {
  let data: { status: DeviceGrantStatus; detail?: string } & Partial<DeviceGrant>
  try {
    const resp = await apiFetch('/api/cloud/auth/device/status')
    if (!resp.ok) return
    data = await resp.json()
  } catch {
    // Transient — keep polling; the grant is bounded by its own expiry server-side.
    return
  }

  deviceStatus.value = data.status
  if (data.status === 'pending') {
    deviceGrant.value = {
      user_code: data.user_code ?? '',
      verification_uri: data.verification_uri ?? '',
      verification_uri_complete: data.verification_uri_complete ?? '',
      expires_in: data.expires_in,
    }
    return
  }

  stopDevicePolling()
  deviceGrant.value = null
  deviceDetail.value = data.detail ?? null
  if (data.status === 'connected') {
    toast.success('Connected to Errand Cloud')
    await fetchStatus()
  }
}

function startDevicePolling() {
  stopDevicePolling()
  devicePoll = setInterval(pollDeviceStatus, DEVICE_POLL_MS)
}

async function restoreDeviceGrant() {
  // A reload must not lose an in-flight grant: the backend still holds it.
  try {
    const resp = await apiFetch('/api/cloud/auth/device/status')
    if (!resp.ok) return
    const data = await resp.json()
    if (data.status !== 'pending') return
    deviceGrant.value = {
      user_code: data.user_code ?? '',
      verification_uri: data.verification_uri ?? '',
      verification_uri_complete: data.verification_uri_complete ?? '',
      expires_in: data.expires_in,
    }
    deviceStatus.value = 'pending'
    startDevicePolling()
  } catch {
    // Best-effort restore
  }
}

async function handleConnect() {
  connecting.value = true
  deviceDetail.value = null
  deviceStatus.value = 'none'
  try {
    const resp = await apiFetch('/api/cloud/auth/device', { method: 'POST' })
    if (!resp.ok) {
      toast.error('Failed to start cloud connection')
      return
    }
    deviceGrant.value = await resp.json()
    deviceStatus.value = 'pending'
    startDevicePolling()
  } catch {
    toast.error('Failed to start cloud connection')
  } finally {
    connecting.value = false
  }
}

async function handleDisconnect() {
  disconnecting.value = true
  try {
    const resp = await apiFetch('/api/cloud/auth/disconnect', { method: 'POST' })
    if (resp.ok) {
      toast.success('Disconnected from Errand Cloud')
      await fetchStatus()
    } else {
      toast.error('Failed to disconnect')
    }
  } catch {
    toast.error('Failed to disconnect')
  } finally {
    disconnecting.value = false
  }
}

function handleReconnect() {
  handleConnect()
}

async function copyUrl(url: string) {
  try {
    await navigator.clipboard.writeText(url)
    toast.success('URL copied to clipboard')
  } catch {
    toast.error('Failed to copy URL')
  }
}

onMounted(async () => {
  await fetchStatus()
  await restoreDeviceGrant()

  // Toast endpoint registration errors so the user knows about failures
  if (cloudStatus.value.endpoint_error?.detail) {
    toast.error('Endpoint registration failed: ' + cloudStatus.value.endpoint_error.detail)
  }
})

onBeforeUnmount(stopDevicePolling)
</script>

<template>
  <div class="space-y-6">
    <div class="rounded-lg bg-white p-6 shadow-sm">
      <h3 class="text-lg font-semibold text-gray-900 mb-1">Cloud Service</h3>
      <p class="text-sm text-gray-500 mb-6">
        Connect your instance to Errand Cloud to receive webhooks without configuring port forwarding.
      </p>

      <!-- Loading state -->
      <div v-if="loading" class="space-y-3">
        <div class="h-4 w-48 rounded-sm bg-gray-200 animate-pulse"></div>
        <div class="h-4 w-32 rounded-sm bg-gray-200 animate-pulse"></div>
      </div>

      <!-- Device authorization pending -->
      <div v-else-if="isPendingGrant" data-testid="cloud-device-grant">
        <p class="text-sm text-gray-600 mb-4">
          Open the verification page and enter this code to connect this instance:
        </p>
        <p
          class="font-mono text-3xl font-semibold tracking-widest text-gray-900 mb-4"
          data-testid="cloud-device-code"
        >
          {{ deviceGrant?.user_code }}
        </p>
        <p class="text-sm text-gray-600 mb-4">
          <a
            :href="deviceGrant?.verification_uri_complete || deviceGrant?.verification_uri"
            target="_blank"
            rel="noopener noreferrer"
            class="font-medium text-blue-600 hover:text-blue-700 underline"
            data-testid="cloud-device-link"
          >
            {{ deviceGrant?.verification_uri }}
          </a>
          <span class="text-gray-500"> — opens on this machine with the code already filled in.</span>
        </p>
        <div class="flex items-center gap-3">
          <span class="text-sm text-gray-500" data-testid="cloud-device-waiting">
            Waiting for authorisation...
          </span>
          <button
            class="rounded-md bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-200"
            data-testid="cloud-device-restart"
            :disabled="connecting"
            @click="handleConnect"
          >
            Start again
          </button>
        </div>
      </div>

      <!-- Not configured -->
      <div v-else-if="isNotConfigured" data-testid="cloud-not-connected">
        <p
          v-if="deviceFailureMessage"
          class="text-sm text-amber-600 mb-3"
          data-testid="cloud-device-failure"
        >
          {{ deviceFailureMessage }}
        </p>
        <button
          class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          data-testid="cloud-connect-btn"
          :disabled="connecting"
          @click="handleConnect"
        >
          {{ connecting ? 'Starting...' : 'Connect to Errand Cloud' }}
        </button>
      </div>

      <!-- Connected -->
      <div v-else-if="isConnected" data-testid="cloud-connected">
        <div class="flex items-center gap-2 mb-2">
          <span class="inline-block h-2.5 w-2.5 rounded-full bg-green-500"></span>
          <span class="text-sm font-medium text-green-700">Connected</span>
          <span v-if="cloudStatus.email || cloudStatus.tenant_id" class="text-xs text-gray-400 ml-2">
            {{ cloudStatus.email || cloudStatus.tenant_id }}
          </span>
        </div>

        <!-- Subscription info -->
        <p v-if="subscriptionInactive" class="text-sm text-amber-600 mb-2" data-testid="cloud-subscription-warning">
          Your Errand Cloud subscription has expired. Endpoint registration is unavailable.
        </p>
        <p v-if="subscriptionExpiry" class="text-xs text-gray-500 mb-4" data-testid="cloud-subscription-expiry">
          Subscription expires {{ subscriptionExpiry }}
        </p>
        <div v-else class="mb-4"></div>

        <!-- Payment failure warning -->
        <p
          v-if="paymentWarningMessage"
          class="text-sm mb-4 flex items-center gap-1.5"
          :class="paymentWarningFinal ? 'text-red-600' : 'text-amber-600'"
          data-testid="cloud-payment-warning"
        >
          <span
            class="inline-block h-2 w-2 rounded-full"
            :class="paymentWarningFinal ? 'bg-red-500' : 'bg-amber-500'"
          ></span>
          {{ paymentWarningMessage }}
        </p>

        <div class="flex items-center gap-3">
          <a
            href="https://errand.cloud"
            target="_blank"
            rel="noopener noreferrer"
            class="rounded-md bg-gray-100 px-4 py-2 text-sm font-medium text-gray-700 hover:bg-gray-200"
            data-testid="cloud-manage-account-btn"
          >
            Manage Account
          </a>
          <button
            class="rounded-md bg-red-50 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-100"
            data-testid="cloud-disconnect-btn"
            :disabled="disconnecting"
            @click="handleDisconnect"
          >
            {{ disconnecting ? 'Disconnecting...' : 'Disconnect' }}
          </button>
        </div>
      </div>

      <!-- Error -->
      <div v-else-if="isError" data-testid="cloud-error">
        <div class="flex items-center gap-2 mb-2">
          <span class="inline-block h-2.5 w-2.5 rounded-full bg-red-500"></span>
          <span class="text-sm font-medium text-red-700">Error</span>
        </div>
        <p v-if="cloudStatus.detail" class="text-sm text-red-600 mb-4">{{ cloudStatus.detail }}</p>
        <p
          v-if="deviceFailureMessage"
          class="text-sm text-amber-600 mb-4"
          data-testid="cloud-device-failure"
        >
          {{ deviceFailureMessage }}
        </p>
        <button
          class="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
          data-testid="cloud-reconnect-btn"
          @click="handleReconnect"
        >
          Reconnect
        </button>
      </div>
    </div>

    <!-- Cloud Endpoints -->
    <div
      v-if="isConnected || webhookTriggers.length > 0"
      class="rounded-lg bg-white p-6 shadow-sm"
    >
      <h3 class="text-lg font-semibold text-gray-900 mb-1">Cloud Endpoints</h3>

      <!-- Persistent banner for the global endpoint registration error.
           Shown above the rows so it stays visible even when trigger rows exist
           but no URLs have been registered (the previous v-else-if hid this). -->
      <p
        v-if="hasEndpointError"
        class="mt-3 rounded-md bg-red-50 border border-red-200 px-3 py-2 text-sm text-red-700"
        data-testid="cloud-endpoint-error-banner"
      >
        Endpoint registration failed: {{ cloudStatus.endpoint_error?.detail }}
      </p>

      <div v-if="hasEndpoints" class="space-y-3 mt-4" data-testid="cloud-endpoints">
        <div
          v-for="ep in cloudStatus.endpoints"
          :key="ep.token"
          class="flex items-center justify-between rounded-md border border-gray-200 px-4 py-3"
        >
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <span class="text-xs font-medium text-gray-500 uppercase">{{ ep.integration }}</span>
              <span class="text-xs text-gray-400">/</span>
              <span class="text-xs font-medium text-gray-500">{{ ep.endpoint_type }}</span>
            </div>
            <p class="mt-1 truncate text-sm font-mono text-gray-700">{{ ep.url }}</p>
          </div>
          <button
            class="ml-4 rounded-md bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-200"
            data-testid="copy-endpoint-btn"
            @click="copyUrl(ep.url)"
          >
            Copy
          </button>
        </div>

        <!-- Per-trigger Jira/GitHub webhook URLs -->
        <div
          v-for="trigger in webhookTriggers"
          :key="`trigger-${trigger.id}`"
          class="flex items-center justify-between rounded-md border border-gray-200 px-4 py-3"
          data-testid="trigger-endpoint-row"
        >
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <span class="text-xs font-medium text-gray-500 uppercase">{{ trigger.source }}</span>
              <span class="text-xs text-gray-400">/</span>
              <span class="text-xs font-medium text-gray-500">{{ trigger.name }}</span>
            </div>
            <p
              v-if="trigger.cloud_webhook_url"
              class="mt-1 truncate text-sm font-mono text-gray-700"
              :data-testid="`trigger-url-${trigger.id}`"
            >
              {{ trigger.cloud_webhook_url }}
            </p>
            <p
              v-else-if="!isConnected"
              class="mt-1 text-sm italic text-gray-500"
              data-testid="trigger-cloud-not-connected"
            >
              Cloud not connected
            </p>
            <p
              v-else
              class="mt-1 text-sm italic text-amber-600"
              data-testid="trigger-registration-failed"
            >
              Registration failed — re-save trigger to retry
            </p>
          </div>
          <button
            v-if="trigger.cloud_webhook_url"
            class="ml-4 rounded-md bg-gray-100 px-3 py-1.5 text-xs font-medium text-gray-600 hover:bg-gray-200"
            data-testid="copy-trigger-url-btn"
            @click="copyUrl(trigger.cloud_webhook_url)"
          >
            Copy
          </button>
        </div>
      </div>

      <template v-else-if="!hasEndpointError">
        <p v-if="subscriptionInactive" class="text-sm text-gray-500 mt-4" data-testid="cloud-subscription-inactive">
          Endpoint registration is unavailable while your subscription is inactive.
        </p>

        <p v-else-if="cloudStatus.slack_configured" class="text-sm text-gray-500 mt-4" data-testid="cloud-registering">
          Endpoints are being registered with Errand Cloud...
        </p>

        <p v-else class="text-sm text-gray-500 mt-4" data-testid="cloud-no-slack">
          Configure Slack, Jira, or GitHub in Integrations to see cloud webhook endpoints.
        </p>
      </template>
    </div>
  </div>
</template>
