const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || `http://${window.location.hostname}:5000/api`
).replace(/\/$/, '');

// Centralise les requêtes API et transmet le cookie de session à chaque appel.
export function apiFetch(path, options = {}) {
  return fetch(`${API_BASE_URL}${path}`, {
    ...options,
    credentials: 'include'
  });
}

// Demande au backend d'envoyer un lien de réinitialisation pour cet utilisateur.
export async function forgotPassword(username) {
  const response = await apiFetch('/auth/forgot-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username })
  });
  return response.json();
}

// Transmet au backend le jeton de réinitialisation et le nouveau mot de passe.
export async function resetPassword(token, password) {
  const response = await apiFetch('/auth/reset-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ token, password })
  });
  return response.json();
}