<template>
  <div class="booking-widget" :class="position" :style="{ '--primary-color': config.primary_color }">
    <!-- Floating Button (when not inline) -->
    <button 
      v-if="position !== 'inline'"
      class="booking-toggle"
      @click="toggleWidget"
    >
      <span class="icon">📅</span>
      <span class="label">Book Now</span>
    </button>

    <!-- Booking Modal/Drawer -->
    <div v-if="isOpen && position !== 'inline'" class="booking-modal">
      <div class="modal-header">
        <h3>Book an Appointment</h3>
        <button class="close-btn" @click="closeWidget">×</button>
      </div>

      <form @submit.prevent="submitBooking" class="booking-form">
        <!-- Step 1: Service Selection -->
        <div v-if="step === 1" class="form-step">
          <h4>Select a Service</h4>
          <div class="service-list">
            <div
              v-for="service in services"
              :key="service.id"
              class="service-item"
              :class="{ selected: selectedService === service.id }"
              @click="selectService(service.id)"
            >
              <div class="service-name">{{ service.name }}</div>
              <div class="service-price">£{{ service.price }}</div>
              <div class="service-duration">{{ service.duration }}min</div>
            </div>
          </div>
          <button 
            type="button" 
            class="btn-next" 
            :disabled="!selectedService"
            @click="step = 2"
          >
            Next
          </button>
        </div>

        <!-- Step 2: Date & Time -->
        <div v-if="step === 2" class="form-step">
          <h4>Choose Date & Time</h4>
          <div class="datetime-picker">
            <input type="date" v-model="bookingDate" :min="minDate" />
            <select v-model="bookingTime">
              <option v-for="slot in timeSlots" :key="slot" :value="slot">
                {{ slot }}
              </option>
            </select>
          </div>
          <div class="step-actions">
            <button type="button" class="btn-back" @click="step = 1">Back</button>
            <button type="button" class="btn-next" :disabled="!bookingDate || !bookingTime" @click="step = 3">
              Next
            </button>
          </div>
        </div>

        <!-- Step 3: Customer Details -->
        <div v-if="step === 3" class="form-step">
          <h4>Your Details</h4>
          <div class="form-group">
            <label>Name *</label>
            <input type="text" v-model="customerName" required />
          </div>
          <div class="form-group">
            <label>Email *</label>
            <input type="email" v-model="customerEmail" required />
          </div>
          <div class="form-group">
            <label>Phone</label>
            <input type="tel" v-model="customerPhone" />
          </div>
          <div class="form-group">
            <label>Notes</label>
            <textarea v-model="customerNotes" rows="3"></textarea>
          </div>
          <div class="step-actions">
            <button type="button" class="btn-back" @click="step = 2">Back</button>
            <button type="submit" class="btn-submit">Book Appointment</button>
          </div>
        </div>

        <!-- Confirmation -->
        <div v-if="step === 4" class="form-step confirmation">
          <div class="success-icon">✓</div>
          <h4>Booking Confirmed!</h4>
          <p>We'll send a confirmation to {{ customerEmail }}</p>
          <button type="button" class="btn-close" @click="closeWidget">Close</button>
        </div>
      </form>
    </div>

    <!-- Inline Mode -->
    <div v-if="position === 'inline'" class="inline-booking">
      <h3>Book Your Appointment</h3>
      <!-- Same form content as modal -->
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';

const props = defineProps({
  websiteId: String,
  config: {
    type: Object,
    default: () => ({
      enabled: true,
      position: 'bottom-right',
      theme: 'light',
      primary_color: '#1E40AF',
      company_name: null,
      service_ids: []
    })
  }
});

const emit = defineEmits(['booking-created', 'widget-opened', 'widget-closed']);

// State
const isOpen = ref(false);
const step = ref(1);
const selectedService = ref(null);
const bookingDate = ref('');
const bookingTime = ref('');
const customerName = ref('');
const customerEmail = ref('');
const customerPhone = ref('');
const customerNotes = ref('');
const services = ref([]);
const timeSlots = ref([]);

// Computed
const position = computed(() => props.config?.position || 'bottom-right');
const minDate = computed(() => {
  const tomorrow = new Date();
  tomorrow.setDate(tomorrow.getDate() + 1);
  return tomorrow.toISOString().split('T')[0];
});

// Methods
const toggleWidget = () => {
  isOpen.value = !isOpen.value;
  if (isOpen.value) {
    emit('widget-opened');
    loadServices();
    generateTimeSlots();
  }
};

const closeWidget = () => {
  isOpen.value = false;
  emit('widget-closed');
  resetForm();
};

const loadServices = async () => {
  // Mock services - in production, fetch from booking API
  services.value = [
    { id: 'svc-1', name: 'Haircut & Style', price: 35, duration: 45 },
    { id: 'svc-2', name: 'Color Treatment', price: 65, duration: 90 },
    { id: 'svc-3', name: 'Manicure', price: 25, duration: 30 },
    { id: 'svc-4', name: 'Massage (60 min)', price: 55, duration: 60 },
  ];
};

const generateTimeSlots = () => {
  // Generate time slots from 9 AM to 5 PM
  const slots = [];
  for (let hour = 9; hour <= 17; hour++) {
    slots.push(`${hour.toString().padStart(2, '0')}:00`);
    slots.push(`${hour.toString().padStart(2, '0')}:30`);
  }
  timeSlots.value = slots;
};

const selectService = (serviceId) => {
  selectedService.value = selectedService.value === serviceId ? null : serviceId;
};

const submitBooking = async () => {
  const booking = {
    website_id: props.websiteId,
    service_id: selectedService.value,
    date: bookingDate.value,
    time: bookingTime.value,
    customer: {
      name: customerName.value,
      email: customerEmail.value,
      phone: customerPhone.value,
      notes: customerNotes.value
    }
  };

  console.log('Booking submitted:', booking);
  emit('booking-created', booking);
  step.value = 4;
};

const resetForm = () => {
  step.value = 1;
  selectedService.value = null;
  bookingDate.value = '';
  bookingTime.value = '';
  customerName.value = '';
  customerEmail.value = '';
  customerPhone.value = '';
  customerNotes.value = '';
};
</script>

<style scoped>
.booking-widget {
  position: fixed;
  z-index: 1000;
}

.booking-widget.bottom-right {
  bottom: 20px;
  right: 20px;
}

.booking-widget.bottom-left {
  bottom: 20px;
  left: 20px;
}

.booking-toggle {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem 1.25rem;
  background: var(--primary-color, #1E40AF);
  color: white;
  border: none;
  border-radius: 50px;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
  transition: transform 0.2s, box-shadow 0.2s;
}

.booking-toggle:hover {
  transform: translateY(-2px);
  box-shadow: 0 6px 16px rgba(0, 0, 0, 0.2);
}

.booking-toggle .icon {
  font-size: 1.25rem;
}

.booking-modal {
  position: absolute;
  bottom: 70px;
  right: 0;
  width: 360px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  overflow: hidden;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  background: var(--primary-color, #1E40AF);
  color: white;
}

.modal-header h3 {
  margin: 0;
  font-size: 1rem;
}

.close-btn {
  background: none;
  border: none;
  color: white;
  font-size: 1.5rem;
  cursor: pointer;
  padding: 0;
  line-height: 1;
}

.booking-form {
  padding: 1rem;
}

.form-step h4 {
  margin: 0 0 1rem 0;
  font-size: 1rem;
}

.service-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.service-item {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: 0.5rem;
  padding: 0.75rem;
  border: 2px solid #e0e0e0;
  border-radius: 8px;
  cursor: pointer;
  transition: border-color 0.2s;
}

.service-item.selected {
  border-color: var(--primary-color, #1E40AF);
  background: rgba(30, 64, 175, 0.05);
}

.service-name {
  font-weight: 500;
}

.service-price {
  color: var(--primary-color, #1E40AF);
  font-weight: 600;
}

.service-duration {
  color: #666;
  font-size: 0.875rem;
}

.datetime-picker {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.datetime-picker input,
.datetime-picker select {
  width: 100%;
  padding: 0.75rem;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
}

.form-group {
  margin-bottom: 0.75rem;
}

.form-group label {
  display: block;
  margin-bottom: 0.25rem;
  font-size: 0.875rem;
  font-weight: 500;
}

.form-group input,
.form-group textarea {
  width: 100%;
  padding: 0.75rem;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
}

.step-actions {
  display: flex;
  gap: 0.5rem;
  margin-top: 1rem;
}

.btn-next,
.btn-submit {
  flex: 1;
  padding: 0.75rem;
  background: var(--primary-color, #1E40AF);
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
}

.btn-next:disabled,
.btn-submit:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn-back {
  padding: 0.75rem;
  background: #e0e0e0;
  border: none;
  border-radius: 8px;
  cursor: pointer;
}

.confirmation {
  text-align: center;
}

.success-icon {
  width: 60px;
  height: 60px;
  margin: 0 auto 1rem;
  background: #4caf50;
  color: white;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 2rem;
}

.btn-close {
  width: 100%;
  padding: 0.75rem;
  background: var(--primary-color, #1E40AF);
  color: white;
  border: none;
  border-radius: 8px;
  cursor: pointer;
  margin-top: 1rem;
}

.inline-booking {
  padding: 2rem;
  background: white;
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}
</style>