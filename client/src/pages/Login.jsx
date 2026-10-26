import { useEffect, useState } from 'react';
import { apiFetch } from '../api';
import logo from '../assets/HoneypotSwarm.png';
import ForgotPassword from './ForgotPassword';

export default function Login({ onLoginSuccess }) {
  const [username, setUsername] = useState('');
  const [recoveryEmail, setRecoveryEmail] = useState('');
  const [password, setPassword] = useState('');
  const [passwordConfirmation, setPasswordConfirmation] = useState('');
  const [setupRequired, setSetupRequired] = useState(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [isForgotMode, setIsForgotMode] = useState(false);

  // Vérifier aussi si un token est présent dans l'URL pour forcer l'affichage direct de ForgotPassword (reset)
  const urlParams = new URLSearchParams(window.location.search);
  const hasTokenInUrl = urlParams.has('token');

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
    return <ForgotPassword onBackToLogin={() => {
      setIsForgotMode(false);
      window.history.replaceState({}, document.title, window.location.pathname);
    }} />;
  }

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
            <img 
              src={logo} 
              alt="Honeypot Swarm Logo" 
              style={{ width: '42px', height: '42px', objectFit: 'contain' }} 
            />
            <h2 style={{ color: '#f8fafc', margin: 0, fontSize: '1.6rem', fontWeight: 'bold' }}>
              Honeypot Swarm
            </h2>
          </div>
          <p style={{ color: '#94a3b8', margin: 0, fontSize: '0.85rem' }}>
            {setupRequired
              ? 'Crée ton compte administrateur'
              : 'Honeypots controller'}
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

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ display: 'block', color: '#94a3b8', fontSize: '0.8rem', marginBottom: '6px' }}>Identifiant</label>
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

          {setupRequired && (
            <div>
              <label style={{ display: 'block', color: '#94a3b8', fontSize: '0.8rem', marginBottom: '6px' }}>
                Adresse e-mail de récupération
              </label>
              <input
                type="email"
                autoComplete="email"
                value={recoveryEmail}
                onChange={(e) => setRecoveryEmail(e.target.value)}
                placeholder="admin@example.com"
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
          )}

          <div>
            <label style={{ display: 'block', color: '#94a3b8', fontSize: '0.8rem', marginBottom: '6px' }}>Mot de passe</label>
            <input
              type="password"
              autoComplete={setupRequired ? 'new-password' : 'current-password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              minLength={setupRequired ? 12 : undefined}
              placeholder={setupRequired ? '12 caractères minimum' : '••••••••'}
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

          {setupRequired && (
            <div>
              <label style={{ display: 'block', color: '#94a3b8', fontSize: '0.8rem', marginBottom: '6px' }}>
                Confirmer le mot de passe
              </label>
              <input
                type="password"
                autoComplete="new-password"
                value={passwordConfirmation}
                onChange={(e) => setPasswordConfirmation(e.target.value)}
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
          )}

          <button
            type="submit"
            disabled={loading || setupRequired === null}
            style={{
              marginTop: '8px',
              padding: '11px',
              backgroundColor: '#3b82f6',
              color: '#fff',
              border: 'none',
              borderRadius: '6px',
              fontWeight: '600',
              cursor: 'pointer',
              opacity: loading ? 0.7 : 1,
              transition: 'background 0.2s'
            }}
          >
            {loading
              ? (setupRequired ? 'Création du compte...' : 'Connexion en cours...')
              : (setupRequired ? 'Créer le compte' : 'Se connecter')}
          </button>
        </form>

        {!setupRequired && (
          <div style={{ textAlign: 'center', marginTop: '16px' }}>
            <button
              onClick={() => setIsForgotMode(true)}
              style={{
                background: 'none',
                border: 'none',
                color: '#94a3b8',
                fontSize: '0.8rem',
                cursor: 'pointer',
                textDecoration: 'underline'
              }}
            >
              Mot de passe oublié ?
            </button>
          </div>
        )}
      </div>
    </div>
  );
}