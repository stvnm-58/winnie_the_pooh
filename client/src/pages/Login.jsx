import { useEffect, useState } from 'react';
import { apiFetch } from '../api';
import logo from '../assets/HoneypotSwarm.png';
import ForgotPassword from './ForgotPassword';
import './Login.css';

// Écran d'accès : création initiale de l'administrateur, connexion ou bascule vers la récupération.
export default function Login({ onLoginSuccess }) {
  const [username, setUsername] = useState('');
  const [recoveryEmail, setRecoveryEmail] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirmation, setPasswordConfirmation] = useState('');
  const [setupRequired, setSetupRequired] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [isForgotMode, setIsForgotMode] = useState(false);

  // Un lien de réinitialisation ouvre directement l'écran correspondant.
  const urlParams = new URLSearchParams(window.location.search);
  const hasTokenInUrl = urlParams.has('token');

  // Détermine s'il faut créer le compte administrateur ou afficher la connexion.
  useEffect(() => {
    let cancelled = false;
    apiFetch('/auth-status')
      .then(async response => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Impossible de vérifier la configuration.');
        if (!cancelled) setSetupRequired(data.setup_required);
      })
      .catch(err => {
        if (!cancelled) setError(err.message || 'Impossible de joindre le serveur backend.');
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (isForgotMode || hasTokenInUrl) {
    // Quitter le formulaire de récupération revient à la connexion et retire le jeton de l'URL.
    return <ForgotPassword onBackToLogin={() => {
      setIsForgotMode(false);
      window.history.replaceState({}, document.title, window.location.pathname);
    }} />;
  }

  // Envoie la création initiale du compte ou la connexion selon l'état du backend.
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (setupRequired && password !== passwordConfirmation) {
      setError('Les deux mots de passe ne correspondent pas.');
      return;
    }
    setLoading(true);
    setError('');

    try {
      const res = await apiFetch(setupRequired ? '/setup' : '/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username,
          password,
          ...(setupRequired ? { email: recoveryEmail } : {})
        })
      });

      const data = await res.json();

      if (res.ok && data.username) {
        onLoginSuccess();
      } else {
        setError(data.error || 'Erreur de connexion');
      }
    } catch {
      setError('Impossible de se connecter au serveur backend.');
    } finally {
      setLoading(false);
    }
  };

  return (
    // Carte de connexion centrée ; les champs de récupération n'apparaissent que pendant la configuration.
    <div className="login-wrapper">
      <div className="login-card">
        <div className="login-header">
          <div className="login-logo-container">
            <img 
              src={logo} 
              alt="Honeypot Swarm Logo" 
              className="login-logo" 
            />
            <h2 className="login-title">
              Honeypot Swarm
            </h2>
          </div>
          <p className="login-subtitle">
            {setupRequired
              ? 'Crée ton compte administrateur'
              : 'Honeypots controller'}
          </p>
        </div>

        {error && (
          <div className="login-alert-error">
            {error}
          </div>
        )}

        {/* Formulaire adaptatif : setup initial ou authentification selon setupRequired. */}
        <form onSubmit={handleSubmit} className="login-form">
          <div>
            <label className="login-label">Identifiant</label>
            <input
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="admin"
              required
              className="login-input"
            />
          </div>

          {setupRequired && (
            <div>
              <label className="login-label">
                Adresse e-mail de récupération
              </label>
              <input
                type="email"
                autoComplete="email"
                value={recoveryEmail}
                onChange={(e) => setRecoveryEmail(e.target.value)}
                placeholder="admin@example.com"
                required
                className="login-input"
              />
            </div>
          )}

          <div>
            <label className="login-label">Mot de passe</label>
            <input
              type="password"
              autoComplete={setupRequired ? 'new-password' : 'current-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={setupRequired ? 12 : undefined}
              placeholder={setupRequired ? '12 caractères minimum' : '••••••••'}
              required
              className="login-input"
            />
          </div>

          {setupRequired && (
            <div>
              <label className="login-label">
                Confirmer le mot de passe
              </label>
              <input
                type="password"
                autoComplete="new-password"
                value={passwordConfirmation}
                onChange={(e) => setPasswordConfirmation(e.target.value)}
                minLength={12}
                required
                className="login-input"
              />
            </div>
          )}

          <button
            type="submit"
            disabled={loading || setupRequired === null}
            className="login-submit-btn"
          >
            {loading
              ? (setupRequired ? 'Création du compte...' : 'Connexion en cours...')
              : (setupRequired ? 'Créer le compte' : 'Se connecter')}
          </button>
        </form>

        {!setupRequired && (
          <div className="login-forgot-container">
            <button
              onClick={() => setIsForgotMode(true)}
              className="login-forgot-btn"
            >
              Mot de passe oublié ?
            </button>
          </div>
        )}
      </div>
    </div>
  );
}