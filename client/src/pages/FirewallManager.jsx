import { useState, useEffect } from 'react';
import { apiFetch } from '../api';
import useBannedIps from '../hooks/useBannedIps';

export default function FirewallManager() {
  const { bannedIps, refreshBannedIps: fetchBannedIps } = useBannedIps();
  const [inputIp, setInputIp] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const [autoBanStats, setAutoBanStats] = useState({});
  const [activeAttempts, setActiveAttempts] = useState({});

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
  }, []);

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
      <p className="muted" style={{ marginBottom: '20px' }}>
        Visualisez et gérez l'ensemble des adresses IP bloquées au niveau système et suivez les tentatives suspectes en temps réel (seuil d'auto-ban : 15 essais en 15s).
      </p>

      {/* Encadré de surveillance en temps réel des attaques en cours */}
      <div style={{ backgroundColor: '#1e293b', border: '1px solid #334155', borderRadius: '8px', padding: '15px', marginBottom: '25px' }}>
        <h4 style={{ margin: '0 0 10px 0', fontSize: '1rem', color: '#38bdf8' }}>⚡ Surveillance du trafic suspect (Rate-limiting en cours)</h4>
        {Object.keys(activeAttempts).length === 0 ? (
          <p className="muted" style={{ margin: 0, fontSize: '0.85rem' }}>Aucune tentative rapprochée détectée pour le moment.</p>
        ) : (
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
            {Object.entries(activeAttempts).map(([ip, count], idx) => (
              <div key={idx} style={{ backgroundColor: '#0f172a', border: '1px solid #475569', borderRadius: '6px', padding: '8px 12px', display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span style={{ fontFamily: 'monospace', color: '#f87171', fontWeight: 'bold' }}>{ip}</span>
                <span style={{ backgroundColor: 'rgba(239, 68, 68, 0.2)', color: '#fca5a5', padding: '2px 6px', borderRadius: '4px', fontSize: '0.75rem' }}>
                  {count} / 15 essais
                </span>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Formulaire de bannissement manuel */}
      <form onSubmit={handleManualBan} style={{ display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '25px', flexWrap: 'wrap' }}>
        <input 
          type="text" 
          required
          placeholder="Ex: 192.168.1.50" 
          value={inputIp} 
          onChange={(e) => setInputIp(e.target.value)}
          style={{ backgroundColor: '#0f172a', border: '1px solid #334155', color: '#fff', padding: '8px 12px', borderRadius: '6px', width: '200px' }}
        />
        <button 
          type="submit" 
          disabled={loading}
          style={{ backgroundColor: '#ef4444', color: '#fff', border: 'none', padding: '8px 16px', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold' }}
        >
          {loading ? 'Traitement...' : 'Bannir manuellement cette IP 🚫'}
        </button>
        {errorMsg && <span style={{ color: '#fca5a5', fontSize: '0.85rem' }}>{errorMsg}</span>}
      </form>

      <h4>Liste des IP Bloquées ({bannedIps.length})</h4>
      <div style={{ marginTop: '15px' }}>
        {bannedIps.length === 0 ? (
          <p className="muted">Aucune adresse IP n'est actuellement bannie par le système.</p>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid #334155', textAlign: 'left' }}>
                <th style={{ padding: '10px', color: '#94a3b8' }}>Adresse IP</th>
                <th style={{ padding: '10px', color: '#94a3b8' }}>Type de blocage</th>
                <th style={{ padding: '10px', color: '#94a3b8' }}>Tentatives enregistrées</th>
                <th style={{ padding: '10px', color: '#94a3b8', textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {bannedIps.map((ip, idx) => {
                const isAutoBanned = autoBanStats[ip] !== undefined;
                const attemptsCount = autoBanStats[ip];
                
                return (
                  <tr key={idx} style={{ borderBottom: '1px solid #1e293b' }}>
                    <td style={{ padding: '12px 10px', fontFamily: 'monospace', color: '#fca5a5', fontWeight: 'bold' }}>
                      {ip}
                    </td>
                    <td style={{ padding: '12px 10px' }}>
                      {isAutoBanned ? (
                        <span style={{ backgroundColor: 'rgba(239, 68, 68, 0.15)', color: '#f87171', padding: '4px 8px', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 'bold', border: '1px solid rgba(239, 68, 68, 0.3)' }}>
                          ⚡ Auto-banni (DDoS/Flood)
                        </span>
                      ) : (
                        <span style={{ backgroundColor: 'rgba(59, 130, 246, 0.15)', color: '#60a5fa', padding: '4px 8px', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 'bold', border: '1px solid rgba(59, 130, 246, 0.3)' }}>
                          🛡️ Manuel
                        </span>
                      )}
                    </td>
                    <td style={{ padding: '12px 10px', color: '#cbd5e1', fontSize: '0.9rem' }}>
                      {isAutoBanned ? `${attemptsCount} tentatives` : <span className="muted">-</span>}
                    </td>
                    <td style={{ padding: '12px 10px', textAlign: 'right' }}>
                      <button 
                        onClick={() => handleUnban(ip)}
                        style={{ backgroundColor: '#22c55e', color: '#fff', border: 'none', padding: '6px 12px', borderRadius: '6px', cursor: 'pointer', fontSize: '0.8rem', fontWeight: 'bold' }}
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