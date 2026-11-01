import { useState, useEffect } from 'react';
import { apiFetch } from '../api';
import useBannedIps from '../hooks/useBannedIps';
import './FirewallManager.css';

// Écran Pare-feu : configuration auto-ban, surveillance des tentatives et liste des IP bloquées.
export default function FirewallManager() {
  const { bannedIps, refreshBannedIps: fetchBannedIps } = useBannedIps();
  const [inputIp, setInputIp] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [autoBanStats, setAutoBanStats] = useState({});
  const [activeAttempts, setActiveAttempts] = useState({});

  const [autoBanConfig, setAutoBanConfig] = useState({ enabled: true, window: 15, max_attempts: 15 });
  const [configLoading, setConfigLoading] = useState(false);
  const [isEditingConfig, setIsEditingConfig] = useState(false);

  // Actualise les statistiques, tentatives récentes et paramètres de blocage automatique.
  const fetchFirewallData = async () => {
    try {
      const resStats = await apiFetch('/autoban-stats');
      if (resStats.ok) {
        const data = await resStats.json();
        setAutoBanStats(data.autoban_stats || {});
      }

      const resAttempts = await apiFetch('/attempt-stats');
      if (resAttempts.ok) {
        const data = await resAttempts.json();
        setActiveAttempts(data.active_attempts || {});
      }

      const resConfig = await apiFetch('/autoban-config');
      if (resConfig.ok) {
        const data = await resConfig.json();
        if (!isEditingConfig) {
          setAutoBanConfig(data);
        }
      }
    } catch (err) {
      console.error("Erreur lors de la récupération des données du pare-feu :", err);
    }
  };

  useEffect(() => {
    const initialFetch = setTimeout(fetchFirewallData, 0);
    const interval = setInterval(fetchFirewallData, 3000);
    return () => {
      clearTimeout(initialFetch);
      clearInterval(interval);
    };
  }, [isEditingConfig]);

  const handleUpdateConfig = async (newFields) => {
    setConfigLoading(true);
    const updated = { ...autoBanConfig, ...newFields };
    setAutoBanConfig(updated);

    try {
      const res = await apiFetch('/autoban-config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(updated)
      });
      if (res.ok) {
        const data = await res.json();
        setAutoBanConfig(data);
      }
    } catch (err) {
      console.error("Erreur lors de la mise à jour de la configuration :", err);
    } finally {
      setConfigLoading(false);
      setIsEditingConfig(false);
    }
  };

  const handleManualBan = async (e) => {
    e.preventDefault();
    if (!inputIp.trim()) return;

    setLoading(true);
    setErrorMsg('');
    try {
      const res = await apiFetch('/ban', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ip: inputIp.trim() })
      });
      const data = await res.json();
      if (res.ok) {
        setInputIp('');
        await fetchBannedIps();
        await fetchFirewallData();
      } else {
        setErrorMsg(data.error || "Erreur lors du bannissement de l'IP.");
      }
    } catch {
      setErrorMsg("Impossible de joindre l'API Flask.");
    } finally {
      setLoading(false);
    }
  };

  const handleUnban = async (ipAddress) => {
    try {
      const res = await apiFetch('/unban', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ip: ipAddress })
      });
      if (res.ok) {
        await fetchBannedIps();
        await fetchFirewallData();
      } else {
        const data = await res.json();
        alert(data.error || "Erreur lors du débannissement.");
      }
    } catch {
      alert("Erreur réseau.");
    }
  };

  return (
    <div className="card">
      <div className="card-header-flex">
        <h3>🛡️ Gestion du Pare-feu (IPs Bloquées & Surveillance)</h3>
      </div>
      <p className="muted firewall-intro">
        Visualisez et gérez l'ensemble des adresses IP bloquées au niveau système et configurez les règles d'auto-défense en temps réel.
      </p>

      {/* Bandeau supérieur : activation de l'auto-ban, seuil et fenêtre de détection. */}
      <div className="firewall-panel">
        <div className="firewall-config-group">
          <span className="firewall-label-bold">Auto-Ban (Anti-Flood) :</span>
          <button 
            onClick={() => handleUpdateConfig({ enabled: !autoBanConfig.enabled })}
            disabled={configLoading}
            className={`btn-autoban-toggle ${autoBanConfig.enabled ? 'is-enabled' : 'is-disabled'}`}
          >
            {autoBanConfig.enabled ? 'Activé ✓' : 'Désactivé ✕'}
          </button>
        </div>

        <div className="firewall-input-group">
          <label className="firewall-label-sub">Essais max :</label>
          <input 
            type="number" 
            min="1" max="100"
            value={autoBanConfig.max_attempts}
            onFocus={() => setIsEditingConfig(true)}
            onChange={(e) => setAutoBanConfig({ ...autoBanConfig, max_attempts: e.target.value })}
            onBlur={(e) => handleUpdateConfig({ max_attempts: Number(e.target.value) })}
            className="firewall-number-input"
          />
        </div>

        <div className="firewall-input-group">
          <label className="firewall-label-sub">Fenêtre (secondes) :</label>
          <input 
            type="number" 
            min="1" max="300"
            value={autoBanConfig.window}
            onFocus={() => setIsEditingConfig(true)}
            onChange={(e) => setAutoBanConfig({ ...autoBanConfig, window: e.target.value })}
            onBlur={(e) => handleUpdateConfig({ window: Number(e.target.value) })}
            className="firewall-number-input"
          />
        </div>
      </div>

      {/* Panneau de surveillance : affiche les IP proches du seuil ou l'état vide/désactivé. */}
      <div className="firewall-panel">
        <h4 className="firewall-surveillance-title">⚡ Surveillance du trafic suspect (Rate-limiting en cours)</h4>
        {!autoBanConfig.enabled ? (
          <p className="muted firewall-alert-text">L'auto-ban est actuellement désactivé.</p>
        ) : Object.keys(activeAttempts).length === 0 ? (
          <p className="muted firewall-empty-text">Aucune tentative rapprochée détectée pour le moment.</p>
        ) : (
          <div className="attempts-flex-container">
            {Object.entries(activeAttempts).map(([ip, count], idx) => (
              <div key={idx} className="attempt-badge-card">
                <span className="attempt-ip">{ip}</span>
                <span className="attempt-count-pill">
                  {count} / {autoBanConfig.max_attempts} essais
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Formulaire d'ajout manuel d'une adresse IP au pare-feu système. */}
      <form onSubmit={handleManualBan} className="manual-ban-form">
        <input 
          type="text" 
          required
          placeholder="Ex: 192.168.1.50" 
          value={inputIp} 
          onChange={(e) => setInputIp(e.target.value)}
          className="manual-ip-input"
        />
        <button 
          type="submit" 
          disabled={loading}
          className="btn-manual-ban"
        >
          {loading ? 'Traitement...' : 'Bannir manuellement cette IP 🚫'}
        </button>
        {errorMsg && <span className="firewall-error-msg">{errorMsg}</span>}
      </form>

      {/* Tableau inférieur : type de bannissement, tentatives et action de débannissement. */}
      <h4>Liste des IP Bloquées ({bannedIps.length})</h4>
      <div className="banned-table-container">
        {bannedIps.length === 0 ? (
          <p className="muted">Aucune adresse IP n'est actuellement bannie par le système.</p>
        ) : (
          <table className="cyber-table">
            <thead>
              <tr>
                <th>Adresse IP</th>
                <th>Type de blocage</th>
                <th>Tentatives enregistrées</th>
                <th className="text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {bannedIps.map((ip, idx) => {
                const isAutoBanned = autoBanStats[ip] !== undefined;
                const attemptsCount = autoBanStats[ip];
                
                return (
                  <tr key={idx}>
                    <td className="cell-ip-banned">
                      {ip}
                    </td>
                    <td>
                      {isAutoBanned ? (
                        <span className="badge-autobanned">
                          ⚡ Auto-banni (DDoS/Flood)
                        </span>
                      ) : (
                        <span className="badge-manual">
                          🛡️ Manuel
                        </span>
                      )}
                    </td>
                    <td className="cell-attempts-text">
                      {isAutoBanned ? `${attemptsCount} tentatives` : <span className="muted">-</span>}
                    </td>
                    <td className="text-right">
                      <button 
                        onClick={() => handleUnban(ip)}
                        className="btn-unban"
                      >
                        Débannir 🛡️
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}