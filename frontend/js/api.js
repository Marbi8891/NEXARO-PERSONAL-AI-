// Cliente HTTP. Las cookies de sesión viajan solas (same-origin); el navegador añade el Origin.
export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

let unauthorizedHandler = () => {};
export function onUnauthorized(handler) {
  unauthorizedHandler = handler;
}

function messageFrom(data, status) {
  const detail = data?.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg).filter(Boolean).join("; ");
  if (status >= 500) return "Error del servidor. Inténtalo de nuevo.";
  return "No se ha podido completar la operación.";
}

export async function request(path, { method = "GET", body, session = true } = {}) {
  let response;
  try {
    response = await fetch(path, {
      method,
      credentials: "same-origin",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "No se ha podido conectar con el servidor.");
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    // 401 en una ruta con sesión = sesión caducada. En login/me es una respuesta normal.
    if (response.status === 401 && session) unauthorizedHandler();
    throw new ApiError(response.status, messageFrom(data, response.status));
  }
  return data;
}

const id = encodeURIComponent;

export const api = {
  me: () => request("/api/auth/me", { session: false }),
  login: (email, password) => request("/api/auth/login", { method: "POST", body: { email, password }, session: false }),
  register: (email, password) => request("/api/auth/register", { method: "POST", body: { email, password }, session: false }),
  logout: () => request("/api/auth/logout", { method: "POST" }),
  health: () => request("/api/health", { session: false }),

  dashboard: (days = 14) => request(`/api/dashboard?days=${days}`),
  notifications: () => request("/api/notifications"),

  conversations: () => request("/api/conversations"),
  conversation: (conversationId) => request(`/api/conversations/${id(conversationId)}`),
  chat: (message, conversationId) => request("/api/chat", { method: "POST", body: { message, conversation_id: conversationId } }),

  adminUsers: () => request("/api/admin/users"),
  adminCreateUser: (email, password) => request("/api/admin/users", { method: "POST", body: { email, password } }),
  adminApprove: (userId) => request(`/api/admin/users/${id(userId)}/approve`, { method: "POST" }),
  adminReject: (userId) => request(`/api/admin/users/${id(userId)}/reject`, { method: "POST" }),
  adminSetActive: (userId, active) => request(`/api/admin/users/${id(userId)}/active`, { method: "PATCH", body: { active } }),
  adminSetRegistration: (enabled) => request("/api/admin/settings/registration", { method: "PATCH", body: { enabled } }),
  adminAudit: (action) => request(`/api/admin/audit?limit=100${action ? `&action=${id(action)}` : ""}`),
  adminUsage: () => request("/api/admin/usage"),

  apiKeys: (orgId) => request(`/api/organizations/${id(orgId)}/api-keys`),
  createApiKey: (orgId, name, expiresInDays) => request(`/api/organizations/${id(orgId)}/api-keys`, { method: "POST", body: { name, expires_in_days: expiresInDays } }),
  revokeApiKey: (orgId, keyId) => request(`/api/organizations/${id(orgId)}/api-keys/${id(keyId)}`, { method: "DELETE" }),
  organizationUsage: (orgId, days = 30) => request(`/api/organizations/${id(orgId)}/usage?days=${days}`),

  organizations: () => request("/api/organizations"),
  createOrganization: (name, slug) => request("/api/organizations", { method: "POST", body: { name, slug } }),
  members: (orgId) => request(`/api/organizations/${id(orgId)}/members`),
  addMember: (orgId, email, role) => request(`/api/organizations/${id(orgId)}/members`, { method: "POST", body: { email, role } }),
  setMemberRole: (orgId, userId, role) => request(`/api/organizations/${id(orgId)}/members/${id(userId)}`, { method: "PATCH", body: { role } }),
  removeMember: (orgId, userId) => request(`/api/organizations/${id(orgId)}/members/${id(userId)}`, { method: "DELETE" }),
};
