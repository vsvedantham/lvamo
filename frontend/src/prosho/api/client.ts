import axios from 'axios'

// Every ProSho endpoint lives under this vertical's namespace, with its own
// localStorage token key, so a session can never collide with Applaut's or
// Jobref's — see CLAUDE.md's structure rule.
export const TOKEN_KEY = 'prosho_access_token'

// Fired when an authenticated request comes back 401 (expired or revoked
// token); ProshoAuthProvider listens and signs the user out.
export const UNAUTHORIZED_EVENT = 'prosho:unauthorized'

// ProSho has its own backend hostname in production (api.prosho.lvamo.com,
// same shared nginx/backend as the other verticals) — set
// VITE_PROSHO_API_BASE_URL in the Cloudflare Pages build settings. Falls back
// to the single local backend container in dev.
export const API_ROOT = import.meta.env.VITE_PROSHO_API_BASE_URL ?? 'http://localhost:8000'
export const API_BASE = API_ROOT + '/api/v1/prosho'

const client = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
})

client.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY)
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  if (config.data instanceof FormData) {
    delete config.headers['Content-Type']
  }
  return config
})

client.interceptors.response.use(
  (resp) => resp,
  (err) => {
    if (err.response?.status === 401 && err.config?.headers?.Authorization) {
      localStorage.removeItem(TOKEN_KEY)
      window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
    }
    return Promise.reject(err)
  },
)

export default client
