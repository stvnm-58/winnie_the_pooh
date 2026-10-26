import { useEffect, useState } from 'react';
import { apiFetch } from '../api';

export default function AccountManager() {
  const [email, setEmail] = useState('');
  const [smtpHost, setSmtpHost] = useState('');
  const [smtpPort, setSmtpPort] = useState('587');
  const [smtpUser, setSmtpUser] = useState('');
  const [smtpFrom, setSmtpFrom] = useState('');
  const [smtpPassword, setSmtpPassword] = useState('');
  const [smtpPasswordConfigured, setSmtpPasswordConfigured] = useState(false);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  useEffect(() => {
    let cancelled = false;
    apiFetch('/account')
      .then(async response => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Impossible de charger le compte.');
        if (!cancelled) {
          setEmail(data.email || '');
          setSmtpHost(data.smtp_host || '');
          setSmtpPort(data.smtp_port || '587');
          setSmtpUser(data.smtp_user || '');
          setSmtpFrom(data.smtp_from || '');
          setSmtpPasswordConfigured(data.smtp_password_configured || false);
        }
      })
      .catch(fetchError => {
        if (!cancelled) setError(fetchError.message || 'Impossible de joindre le serveur.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleSubmit = async (event) => {
    event.preventDefault();
    setSaving(true);
    setError('');
    setMessage('');

    try {
      const response = await apiFetch('/account', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          smtp_host: smtpHost,
          smtp_port: smtpPort,
          smtp_user: smtpUser,
          smtp_from: smtpFrom,
          smtp_password: smtpPassword
        })
      });
      const data = await response.json();
      if (!response.ok) {
        setError(data.error || 'Impossible de mettre à jour le compte.');
      } else {
        setEmail(data.email);
        setSmtpHost(data.smtp_host || '');
        setSmtpPort(data.smtp_port || '587');
        setSmtpUser(data.smtp_user || '');
        setSmtpFrom(data.smtp_from || '');
        setSmtpPasswordConfigured(data.smtp_password_configured || false);
        setSmtpPassword('');
        setMessage('Paramètres du compte enregistrés.');
      }
    } catch {
      setError('Impossible de joindre le serveur.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="card" style={{ maxWidth: '620px' }}>
      <div className="card-header-flex">
        <h3>Gestion du compte</h3>
      </div>
      <p className="muted">
        Configurez l’adresse de récupération et le serveur d’envoi. Pour Gmail, utilisez un mot de passe d’application.
      </p>

      {error && (
        <p role="alert" style={{ color: '#fca5a5' }}>{error}</p>
      )}
      {message && (
        <p role="status" style={{ color: '#86efac' }}>{message}</p>
      )}

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
        <label style={{ color: '#94a3b8', fontSize: '0.85rem' }} htmlFor="recovery-email">
          Adresse e-mail de récupération
        </label>
        <input
          id="recovery-email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
          disabled={loading || saving}
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
        <label style={{ color: '#94a3b8', fontSize: '0.85rem' }} htmlFor="smtp-host">
          Serveur SMTP
        </label>
        <input
          id="smtp-host"
          type="text"
          autoComplete="url"
          placeholder="smtp.gmail.com"
          value={smtpHost}
          onChange={(event) => setSmtpHost(event.target.value)}
          disabled={loading || saving}
          style={inputStyle}
        />
        <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
          <div style={{ flex: '0 1 120px' }}>
            <label style={{ display: 'block', color: '#94a3b8', fontSize: '0.85rem', marginBottom: '6px' }} htmlFor="smtp-port">
              Port
            </label>
            <input
              id="smtp-port"
              type="number"
              min="1"
              max="65535"
              value={smtpPort}
              onChange={(event) => setSmtpPort(event.target.value)}
              disabled={loading || saving}
              style={inputStyle}
            />
          </div>
          <div style={{ flex: '1 1 220px' }}>
            <label style={{ display: 'block', color: '#94a3b8', fontSize: '0.85rem', marginBottom: '6px' }} htmlFor="smtp-user">
              Identifiant SMTP
            </label>
            <input
              id="smtp-user"
              type="text"
              autoComplete="username"
              value={smtpUser}
              onChange={(event) => setSmtpUser(event.target.value)}
              disabled={loading || saving}
              style={inputStyle}
            />
          </div>
        </div>
        <label style={{ color: '#94a3b8', fontSize: '0.85rem' }} htmlFor="smtp-from">
          Adresse d’expéditeur
        </label>
        <input
          id="smtp-from"
          type="email"
          autoComplete="email"
          placeholder="Identifiant SMTP si laissé vide"
          value={smtpFrom}
          onChange={(event) => setSmtpFrom(event.target.value)}
          disabled={loading || saving}
          style={inputStyle}
        />
        <label style={{ color: '#94a3b8', fontSize: '0.85rem' }} htmlFor="smtp-password">
          Mot de passe SMTP {smtpPasswordConfigured && '(déjà enregistré ; saisir uniquement pour le remplacer)'}
        </label>
        <input
          id="smtp-password"
          type="password"
          autoComplete="new-password"
          value={smtpPassword}
          onChange={(event) => setSmtpPassword(event.target.value)}
          disabled={loading || saving}
          placeholder={smtpPasswordConfigured ? '••••••••••••' : 'Mot de passe d’application'}
          style={inputStyle}
        />
        <p className="muted" style={{ fontSize: '0.8rem', margin: 0 }}>
          Port 587 : STARTTLS. Port 465 : TLS. Le mot de passe est conservé uniquement côté serveur et n’est jamais renvoyé au navigateur.
        </p>
        <button
          type="submit"
          disabled={loading || saving}
          style={{
            alignSelf: 'flex-start',
            padding: '10px 16px',
            backgroundColor: '#3b82f6',
            color: '#fff',
            border: 'none',
            borderRadius: '6px',
            fontWeight: '600',
            cursor: 'pointer',
            opacity: loading || saving ? 0.7 : 1
          }}
        >
          {saving ? 'Enregistrement...' : 'Enregistrer'}
        </button>
      </form>
    </div>
  );
}

const inputStyle = {
  width: '100%',
  padding: '10px 12px',
  borderRadius: '6px',
  border: '1px solid #334155',
  backgroundColor: '#0f172a',
  color: '#fff',
  outline: 'none',
  boxSizing: 'border-box'
};
