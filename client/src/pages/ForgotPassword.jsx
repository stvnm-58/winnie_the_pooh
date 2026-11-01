import { useState } from 'react';
import { forgotPassword, resetPassword } from '../api';
import logo from '../assets/HoneypotSwarm.png';
import './ForgotPassword.css';

// Écran de récupération : affiche la demande d'e-mail ou le formulaire de nouveau mot de passe selon le jeton URL.
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
    // Carte centrée commune aux deux étapes de récupération du compte.
    <div className="forgot-wrapper">
      <div className="forgot-card">
        <div className="forgot-header">
          <div className="forgot-logo-container">
            <img src={logo} alt="Logo" className="forgot-logo" />
            <h2 className="forgot-title">
              Honeypot Swarm
            </h2>
          </div>
          <p className="forgot-subtitle">
            {tokenFromUrl ? 'Nouveau mot de passe' : 'Récupération de compte'}
          </p>
        </div>

        {error && (
          <div className="forgot-alert-error">
            {error}
          </div>
        )}

        {statusMessage && (
          <div className="forgot-alert-success">
            {statusMessage}
          </div>
        )}

        {/* Sans jeton : demander un lien ; avec jeton : choisir et confirmer le nouveau mot de passe. */}
        {!tokenFromUrl ? (
          // Formulaire de demande (Forgot Password)
          <form onSubmit={handleForgotSubmit} className="forgot-form">
            <div>
              <label className="forgot-label">
                Identifiant
              </label>
              <input
                type="text"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="admin"
                required
                className="forgot-input"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="forgot-submit-btn"
            >
              {loading ? 'Envoi en cours...' : 'Envoyer le lien de réinitialisation'}
            </button>
          </form>
        ) : (
          // Formulaire de saisie du nouveau mot de passe (Reset Password)
          <form onSubmit={handleResetSubmit} className="forgot-form">
            <div>
              <label className="forgot-label">
                Nouveau mot de passe (12 car. min)
              </label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                minLength={12}
                required
                className="forgot-input"
              />
            </div>

            <div>
              <label className="forgot-label">
                Confirmer le nouveau mot de passe
              </label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                minLength={12}
                required
                className="forgot-input"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="forgot-submit-btn"
            >
              {loading ? 'Mise à jour...' : 'Réinitialiser le mot de passe'}
            </button>
          </form>
        )}

        <div className="forgot-footer">
          <button
            onClick={onBackToLogin}
            className="forgot-back-btn"
          >
            Retour à la connexion
          </button>
        </div>
      </div>
    </div>
  );
}