import axios from 'axios';

// Create an Axios instance
const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || 'http://localhost:5000',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to add the JWT token to headers
api.interceptors.request.use(
  (config) => {
    // We will store the token in localStorage for now
    if (typeof window !== 'undefined') {
      const token = localStorage.getItem('token');
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
    }
    // Let the browser set 'multipart/form-data' with the correct boundary.
    // The instance-level 'Content-Type: application/json' default would
    // otherwise make axios JSON-stringify the FormData (silently dropping
    // any File entries) instead of sending it as a real file upload.
    if (typeof FormData !== 'undefined' && config.data instanceof FormData) {
      delete config.headers['Content-Type'];
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Response interceptor to handle 401s (unauthorized)
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('token');
        // Optionally redirect to login page if unauthorized
        if (window.location.pathname !== '/login' && window.location.pathname !== '/register') {
           window.location.href = '/login';
        }
      }
    }
    return Promise.reject(error);
  }
);

export default api;
