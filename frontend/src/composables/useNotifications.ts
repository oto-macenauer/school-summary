import { ref, computed } from 'vue'
import { getVapidKey, subscribePush, unsubscribePush } from '@/api/client'

const permission = ref<NotificationPermission>(
  typeof Notification !== 'undefined' ? Notification.permission : 'default'
)
const subscription = ref<PushSubscription | null>(null)
const loading = ref(false)
const supported = typeof window !== 'undefined' && 'serviceWorker' in navigator && 'PushManager' in window

const isSubscribed = computed(() => subscription.value !== null)

async function getRegistration(): Promise<ServiceWorkerRegistration | null> {
  if (!supported) return null
  return navigator.serviceWorker.ready
}

async function checkExistingSubscription(): Promise<void> {
  const reg = await getRegistration()
  if (!reg) return
  subscription.value = await reg.pushManager.getSubscription()
}

async function subscribe(student: string): Promise<boolean> {
  if (!supported) return false

  loading.value = true
  try {
    // Request permission
    const perm = await Notification.requestPermission()
    permission.value = perm
    if (perm !== 'granted') return false

    // Get VAPID public key from backend
    const { public_key } = await getVapidKey()
    const applicationServerKey = urlBase64ToUint8Array(public_key)

    // Subscribe to push
    const reg = await getRegistration()
    if (!reg) return false

    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey,
    })

    // Send subscription to backend
    await subscribePush(student, sub.toJSON())
    subscription.value = sub
    return true
  } catch (err) {
    console.error('Failed to subscribe to push:', err)
    return false
  } finally {
    loading.value = false
  }
}

async function unsubscribe(student: string): Promise<void> {
  loading.value = true
  try {
    if (subscription.value) {
      await unsubscribePush(student, subscription.value.endpoint)
      await subscription.value.unsubscribe()
      subscription.value = null
    }
  } catch (err) {
    console.error('Failed to unsubscribe from push:', err)
  } finally {
    loading.value = false
  }
}

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(base64)
  const array = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) {
    array[i] = raw.charCodeAt(i)
  }
  return array
}

export function useNotifications() {
  return {
    supported,
    permission,
    isSubscribed,
    loading,
    subscribe,
    unsubscribe,
    checkExistingSubscription,
  }
}
