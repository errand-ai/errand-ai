/**
 * Website Builder Service
 * API client for website management
 */

import axios from 'axios';

const API_BASE = import.meta.env.VITE_API_URL || '/api';

const api = axios.create({
  baseURL: API_BASE,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Add auth token if available
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export const websiteService = {
  // Website CRUD
  async createWebsite(data) {
    const response = await api.post('/websites', data);
    return response.data;
  },

  async listWebsites(tenantId = null) {
    const params = tenantId ? { tenant_id: tenantId } : {};
    const response = await api.get('/websites', { params });
    return response.data;
  },

  async getWebsite(websiteId) {
    const response = await api.get(`/websites/${websiteId}`);
    return response.data;
  },

  async updateWebsite(websiteId, data) {
    const response = await api.put(`/websites/${websiteId}`, data);
    return response.data;
  },

  async deleteWebsite(websiteId) {
    await api.delete(`/websites/${websiteId}`);
  },

  async publishWebsite(websiteId) {
    const response = await api.post(`/websites/${websiteId}/publish`);
    return response.data;
  },

  // Templates
  async listTemplates() {
    const response = await api.get('/websites/templates');
    return response.data;
  },

  async getTemplate(templateId) {
    const response = await api.get(`/websites/templates/${templateId}`);
    return response.data;
  },

  async applyTemplate(websiteId, templateId) {
    const response = await api.post(`/websites/${websiteId}/apply-template/${templateId}`);
    return response.data;
  },

  // Pages
  async listPages(websiteId) {
    const response = await api.get(`/websites/${websiteId}/pages`);
    return response.data;
  },

  async createPage(websiteId, data) {
    const response = await api.post(`/websites/${websiteId}/pages`, data);
    return response.data;
  },

  async updatePage(websiteId, pageId, data) {
    const response = await api.put(`/websites/${websiteId}/pages/${pageId}`, data);
    return response.data;
  },

  // Sections
  async listSections(websiteId, pageId = null) {
    const params = pageId ? { page_id: pageId } : {};
    const response = await api.get(`/websites/${websiteId}/sections`, { params });
    return response.data;
  },

  async updateSection(websiteId, sectionId, data) {
    const response = await api.put(`/websites/${websiteId}/sections/${sectionId}`, data);
    return response.data;
  },

  // Domain & SSL
  async configureDomain(websiteId, domain) {
    const response = await api.post(`/websites/${websiteId}/domain`, null, {
      params: { domain },
    });
    return response.data;
  },

  async provisionSSL(websiteId) {
    const response = await api.post(`/websites/${websiteId}/ssl`);
    return response.data;
  },

  // Booking Widget
  async getBookingWidget(websiteId) {
    const response = await api.get(`/websites/${websiteId}/booking-widget`);
    return response.data;
  },

  async updateBookingWidget(websiteId, config) {
    const response = await api.put(`/websites/${websiteId}/booking-widget`, config);
    return response.data;
  },
};

export default websiteService;