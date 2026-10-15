import React, { useState, useEffect } from 'react';

export default function FirewallManager() {
  const [bannedIps, setBannedIps] = useState([]);
  const [inputIp, setInputIp] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const fetchBannedIps = async () => {
    try {
      const res = await fetch('http://localhost:5000/api/banned-ips');
      if (res.ok) {
        const data = await res.json();
        setBannedIps(data.ips || []);
      }
    } catch (err) {
      console.error("Erreur lors de la récupération des IP bannies :", err);
    }
  };

  useEffect(() => {
    fetchBannedIps();
    const interval = setInterval(fetchBannedIps, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleManualBan = async (e) => {
    e.preventDefault();
    if (!inputIp.trim()) return;

    setLoading(true);
    setErrorMsg('');
    try {
      const res = await fetch('http://localhost:5000/api/ban', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ip: inputIp.trim() })
      });
      const data = await res.json();
      if (res.ok) {
        setInputIp('');
        await fetchBannedIps();
      } else {
        setErrorMsg(data.error || "Erreur lors du bannissement de l'IP.");
      }
    } catch (err) {
      setErrorMsg("Impossible de joindre l'API Flask.");
    } finally {
      setLoading(false);
    }
  };

  const handleUnban = async (ipAddress) => {
    try {
      const res = await fetch('http://localhost:5000/api/unban', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ip: ipAddress })
      });
      if (res.ok) {
        await fetchBannedIps();
      } else {
        const data = await res.json();
        alert(data.error || "Erreur lors du débannissement.");
      }
    } catch (err) {
      alert("Erreur réseau.");
    }
  };

  return (
    <div className="card">
      <div className="card-header-flex">
        <h3>🛡️ Gestion du Pare-feu (IPs Bloquées)</h3>
      </div>
      <p className="muted" style={{ marginBottom: '20px' }}>
        Visualisez et gérez l'ensemble des adresses IP bloquées au niveau système par le pare-feu du serveur.
      </p>

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
                <th style={{ padding: '10px', color: '#94a3b8', textAlign: 'right' }}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {bannedIps.map((ip, idx) => (
                <tr key={idx} style={{ borderBottom: '1px solid #1e293b' }}>
                  <td style={{ padding: '12px 10px', fontFamily: 'monospace', color: '#fca5a5', fontWeight: 'bold' }}>{ip}</td>
                  <td style={{ padding: '12px 10px', textAlign: 'right' }}>
                    <button 
                      onClick={() => handleUnban(ip)}
                      style={{ backgroundColor: '#22c55e', color: '#fff', border: 'none', padding: '6px 12px', borderRadius: '6px', cursor: 'pointer', fontSize: '0.8rem', fontWeight: 'bold' }}
                    >
                      Débannir 🛡️
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}