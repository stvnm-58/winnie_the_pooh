import { useState } from 'react';
import { forgotPassword, resetPassword } from '../api';
import logo from '../assets/HoneypotSwarm.png';

export default function ForgotPassword({ onBackToLogin }) {
  // Récupérer le token s'il est présent dans l'URL (?token=XYZ)
  const urlParams = new URLSearchParams(window.location.search);
  const tokenFromUrl = urlParams.get('token');

  const [username, setUsername] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [statusMessage, setStatusMessage] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  // Demande un courriel de récupération sans révéler si le compte existe.
  const handleForgotSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setStatusMessage('');

    try {
      const data = await forgotPassword(username);
      if (data.success) {
        setStatusMessage(data.message || 'Si un compte est associé, un e-mail a été envoyé.');
      } else {
        setError(data.error || 'Erreur lors de la demande.');
      }
    } catch {
      setError('Impossible de joindre le serveur.');
    } finally {
      setLoading(false);
    }
  };

  // Vérifie la confirmation du mot de passe avant d'envoyer le jeton à l'API.
  const handleResetSubmit = async (e) => {
    e.preventDefault();
    if (newPassword !== confirmPassword) {
      setError('Les mots de passe ne correspondent pas.');
      return;
    }
    setLoading(true);
    setError('');
    setStatusMessage('');

    try {
      const data = await resetPassword(tokenFromUrl, newPassword);
      if (data.success) {
        setStatusMessage('Mot de passe réinitialisé avec succès ! Redirection...');
        setTimeout(() => {
          window.location.href = '/'; // Nettoie le token de l'URL et retourne au login
        }, 2000);
      } else {
        setError(data.error || 'Le lien est invalide ou a expiré.');
      }
    } catch {
      setError('Impossible de joindre le serveur.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      display: 'flex',
      justifyContent: 'center',
      alignItems: 'center',
      minHeight: '75vh'
    }}>
      <div style={{
        backgroundColor: '#1e293b',
        border: '1px solid #334155',
        borderRadius: '12px',
        padding: '35px',
        width: '100%',
        maxWidth: '380px',
        boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.5)'
      }}>
        <div style={{ textAlign: 'center', marginBottom: '25px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px', marginBottom: '8px' }}>
            <img src={logo} alt="Logo" style={{ width: '42px', height: '42px', objectFit: 'contain' }} />
            <h2 style={{ color: '#f8fafc', margin: 0, fontSize: '1.6rem', fontWeight: 'bold' }}>
              Honeypot Swarm
            </h2>
          </div>
          <p style={{ color: '#94a3b8', margin: 0, fontSize: '0.85rem' }}>
            {tokenFromUrl ? 'Nouveau mot de passe' : 'Récupération de compte'}
          </p>
        </div>

        {error && (
          <div style={{
            backgroundColor: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid #ef4444',
            color: '#fca5a5',
            padding: '10px',
            borderRadius: '6px',
            marginBottom: '20px',
            fontSize: '0.85rem',
            textAlign: 'center'
          }}>
            {error}
          </div>
        )}

        {statusMessage && (
          <div style={{
            backgroundColor: 'rgba(34, 197, 94, 0.1)',
            border: '1px solid #22c55e',
            color: '#86efac',
            padding: '10px',
            borderRadius: '6px',
            marginBottom: '20px',
            fontSize: '0.85rem',
            textAlign: 'center'
          }}>
            {statusMessage}
          </div>
        )}

        {!tokenFromUrl ? (
          // Formulaire de demande (Forgot Password)
          <form onSubmit={handleForgotSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div>
              <label style={{ display: 'block', color: '#94a3b8', fontSize: '0.8rem', marginBottom: '6px' }}>
                Identifiant
              </label>
              <input
                type="text"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="admin"
                required
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  borderRadius: '6px',
                  border: '1px solid #334155',
                  backgroundColor: '#0f172a',
                  color: '#fff',
                  outline: 'none',
                  boxSizing: 'border-box'
                }}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              style={{
                marginTop: '8px',
                padding: '11px',
                backgroundColor: '#3b82f6',
                color: '#fff',
                border: 'none',
                borderRadius: '6px',
                fontWeight: '600',
                cursor: 'pointer',
                opacity: loading ? 0.7 : 1
              }}
            >
              {loading ? 'Envoi en cours...' : 'Envoyer le lien de réinitialisation'}
            </button>
          </form>
        ) : (
          // Formulaire de saisie du nouveau mot de passe (Reset Password)
          <form onSubmit={handleResetSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div>
              <label style={{ display: 'block', color: '#94a3b8', fontSize: '0.8rem', marginBottom: '6px' }}>
                Nouveau mot de passe (12 car. min)
              </label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                minLength={12}
                required
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  borderRadius: '6px',
                  border: '1px solid #334155',
                  backgroundColor: '#0f172a',
                  color: '#fff',
                  outline: 'none',
                  boxSizing: 'border-box'
                }}
              />
            </div>

            <div>
              <label style={{ display: 'block', color: '#94a3b8', fontSize: '0.8rem', marginBottom: '6px' }}>
                Confirmer le nouveau mot de passe
              </label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                minLength={12}
                required
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  borderRadius: '6px',
                  border: '1px solid #334155',
                  backgroundColor: '#0f172a',
                  color: '#fff',
                  outline: 'none',
                  boxSizing: 'border-box'
                }}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              style={{
                marginTop: '8px',
                padding: '11px',
                backgroundColor: '#3b82f6',
                color: '#fff',
                border: 'none',
                borderRadius: '6px',
                fontWeight: '600',
                cursor: 'pointer',
                opacity: loading ? 0.7 : 1
              }}
            >
              {loading ? 'Mise à jour...' : 'Réinitialiser le mot de passe'}
            </button>
          </form>
        )}

        <div style={{ textAlign: 'center', marginTop: '20px' }}>
          <button
            onClick={onBackToLogin}
            style={{
              background: 'none',
              border: 'none',
              color: '#3b82f6',
              fontSize: '0.85rem',
              cursor: 'pointer',
              textDecoration: 'underline'
            }}
          >
            Retour à la connexion
          </button>
        </div>
      </div>
    </div>
  );
}