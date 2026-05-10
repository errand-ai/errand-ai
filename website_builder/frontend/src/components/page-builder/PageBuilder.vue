<template>
  <div class="page-builder">
    <div class="builder-header">
      <h1>{{ pageTitle }}</h1>
      <div class="builder-actions">
        <button @click="saveChanges" :disabled="!hasChanges" class="btn-save">
          Save Changes
        </button>
        <button @click="previewPage" class="btn-preview">
          Preview
        </button>
        <button @click="publishPage" class="btn-publish">
          Publish
        </button>
      </div>
    </div>

    <div class="builder-layout">
      <!-- Section Sidebar -->
      <aside class="sections-panel">
        <h2>Available Sections</h2>
        <div class="section-list">
          <div
            v-for="sectionType in availableSections"
            :key="sectionType.type"
            class="section-item"
            draggable="true"
            @dragstart="onDragStart(sectionType)"
          >
            <span class="section-icon">{{ sectionType.icon }}</span>
            <span class="section-name">{{ sectionType.name }}</span>
          </div>
        </div>
      </aside>

      <!-- Page Canvas -->
      <main class="page-canvas" @drop="onDrop" @dragover.prevent>
        <div v-if="sections.length === 0" class="empty-state">
          <p>Drag sections here to build your page</p>
        </div>
        <div
          v-for="(section, index) in sections"
          :key="section.id"
          class="canvas-section"
          :class="{ selected: selectedSection === section.id }"
          @click="selectSection(section.id)"
        >
          <div class="section-header">
            <span class="section-type">{{ section.type }}</span>
            <div class="section-actions">
              <button @click.stop="moveSectionUp(index)" :disabled="index === 0">↑</button>
              <button @click.stop="moveSectionDown(index)" :disabled="index === sections.length - 1">↓</button>
              <button @click.stop="deleteSection(index)" class="btn-delete">×</button>
            </div>
          </div>
          <div class="section-content">
            <component
              :is="getSectionComponent(section.type)"
              :section="section"
              @update="updateSectionContent(section.id, $event)"
            />
          </div>
        </div>
      </main>

      <!-- Properties Panel -->
      <aside class="properties-panel" v-if="selectedSection">
        <h2>Section Properties</h2>
        <div class="property-group">
          <label>Section Type</label>
          <input type="text" :value="getSectionType(selectedSection)" disabled />
        </div>
        <div class="property-group">
          <label>Content</label>
          <textarea
            v-model="sectionContent"
            @input="updateSelectedSection"
            rows="6"
          ></textarea>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue';
import { websiteService } from '@/services/websiteService';

// Props
const props = defineProps({
  websiteId: String,
  pageId: String,
  initialSections: Array
});

// Emits
const emit = defineEmits(['save', 'publish', 'preview']);

// State
const sections = ref(props.initialSections || []);
const selectedSection = ref(null);
const hasChanges = ref(false);
const pageTitle = ref('Untitled Page');

// Available section types
const availableSections = [
  { type: 'hero', name: 'Hero Section', icon: '🎯' },
  { type: 'services', name: 'Services Grid', icon: '📋' },
  { type: 'gallery', name: 'Image Gallery', icon: '🖼' },
  { type: 'testimonials', name: 'Testimonials', icon: '💬' },
  { type: 'contact', name: 'Contact Form', icon: '📧' },
  { type: 'about', name: 'About Section', icon: 'ℹ' },
  { type: 'pricing', name: 'Pricing Table', icon: '💰' },
  { type: 'team', name: 'Team Section', icon: '👥' },
  { type: 'footer', name: 'Footer', icon: '📌' },
];

// Computed
const sectionContent = computed({
  get() {
    const section = sections.value.find(s => s.id === selectedSection.value);
    return section ? JSON.stringify(section.content, null, 2) : '';
  },
  set(value) {
    try {
      const section = sections.value.find(s => s.id === selectedSection.value);
      if (section) {
        section.content = JSON.parse(value);
      }
    } catch (e) {
      // Invalid JSON, ignore
    }
  }
});

// Methods
const getSectionComponent = (type) => {
  // Return appropriate component based on section type
  return { template: '<div class="section-placeholder">Configure this section</div>' };
};

const getSectionType = (sectionId) => {
  const section = sections.value.find(s => s.id === sectionId);
  return section ? section.type : '';
};

const selectSection = (sectionId) => {
  selectedSection.value = selectedSection.value === sectionId ? null : sectionId;
};

const onDragStart = (sectionType) => {
  event.dataTransfer.setData('sectionType', JSON.stringify(sectionType));
};

const onDrop = () => {
  const sectionData = JSON.parse(event.dataTransfer.getData('sectionType'));
  sections.value.push({
    id: `section-${Date.now()}`,
    type: sectionData.type,
    order: sections.value.length,
    content: {},
    styles: {}
  });
  hasChanges.value = true;
};

const moveSectionUp = (index) => {
  if (index > 0) {
    const temp = sections.value[index];
    sections.value[index] = sections.value[index - 1];
    sections.value[index - 1] = temp;
    hasChanges.value = true;
  }
};

const moveSectionDown = (index) => {
  if (index < sections.value.length - 1) {
    const temp = sections.value[index];
    sections.value[index] = sections.value[index + 1];
    sections.value[index + 1] = temp;
    hasChanges.value = true;
  }
};

const deleteSection = (index) => {
  sections.value.splice(index, 1);
  selectedSection.value = null;
  hasChanges.value = true;
};

const updateSectionContent = (sectionId, content) => {
  const section = sections.value.find(s => s.id === sectionId);
  if (section) {
    section.content = content;
    hasChanges.value = true;
  }
};

const updateSelectedSection = () => {
  hasChanges.value = true;
};

const saveChanges = async () => {
  try {
    if (props.pageId) {
      await websiteService.updatePage(props.websiteId, props.pageId, { sections: sections.value });
    }
    emit('save', sections.value);
    hasChanges.value = false;
  } catch (error) {
    console.error('Failed to save changes:', error);
  }
};

const previewPage = () => {
  emit('preview', sections.value);
};

const publishPage = async () => {
  try {
    await saveChanges();
    await websiteService.publishWebsite(props.websiteId);
    emit('publish');
  } catch (error) {
    console.error('Failed to publish page:', error);
  }
};

onMounted(async () => {
  if (props.websiteId && props.pageId) {
    try {
      const page = await websiteService.getWebsite(props.websiteId);
      const targetPage = page.pages?.find(p => p.id === props.pageId);
      if (targetPage) {
        sections.value = targetPage.sections || [];
        pageTitle.value = targetPage.title;
      }
    } catch (error) {
      console.error('Failed to load page:', error);
    }
  }
});
</script>

<style scoped>
.page-builder {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: #f5f5f5;
}

.builder-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem 2rem;
  background: white;
  border-bottom: 1px solid #e0e0e0;
}

.builder-header h1 {
  margin: 0;
  font-size: 1.25rem;
}

.builder-actions {
  display: flex;
  gap: 0.5rem;
}

.builder-actions button {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.btn-save { background: #1976d2; color: white; }
.btn-preview { background: #e0e0e0; }
.btn-publish { background: #4caf50; color: white; }

.builder-layout {
  display: grid;
  grid-template-columns: 200px 1fr 280px;
  gap: 1rem;
  padding: 1rem;
  flex: 1;
  overflow: hidden;
}

.sections-panel,
.properties-panel {
  background: white;
  border-radius: 8px;
  padding: 1rem;
  overflow-y: auto;
}

.section-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.section-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  background: #f5f5f5;
  border-radius: 4px;
  cursor: grab;
  transition: background 0.2s;
}

.section-item:hover {
  background: #e0e0e0;
}

.section-icon {
  font-size: 1.25rem;
}

.page-canvas {
  background: white;
  border-radius: 8px;
  padding: 1rem;
  overflow-y: auto;
  min-height: 400px;
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #999;
}

.canvas-section {
  border: 2px solid transparent;
  border-radius: 8px;
  margin-bottom: 1rem;
  transition: border-color 0.2s;
}

.canvas-section.selected {
  border-color: #1976d2;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem;
  background: #f5f5f5;
  border-radius: 6px 6px 0 0;
  cursor: pointer;
}

.section-type {
  font-weight: 500;
  text-transform: capitalize;
}

.section-actions {
  display: flex;
  gap: 0.25rem;
}

.section-actions button {
  padding: 0.25rem 0.5rem;
  border: none;
  background: white;
  border-radius: 4px;
  cursor: pointer;
}

.section-actions button:hover {
  background: #e0e0e0;
}

.btn-delete {
  color: #f44336;
}

.property-group {
  margin-bottom: 1rem;
}

.property-group label {
  display: block;
  margin-bottom: 0.5rem;
  font-weight: 500;
}

.property-group input,
.property-group textarea {
  width: 100%;
  padding: 0.5rem;
  border: 1px solid #e0e0e0;
  border-radius: 4px;
}
</style>