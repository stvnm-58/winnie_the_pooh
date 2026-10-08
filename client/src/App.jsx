import React, { useState, useEffect } from 'react';
import './App.css';

function App() {
  const [attacks, setAttacks] = useState([]);
  const [commands, setCommands] = useState([]);
  const [stats, setStats] = useState(null);
  const [isHoneypotActive, setIsHoneypotActive] = useState(false);
  const [selectedSessions, setSelectedSessions] = useState([]);
  const [currentTime, setCurrentTime] = useState(new Date());

  // Mise à jour de l'horloge toutes les secondes
  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const fetchData = async () => {
    try {
      const [resAttacks, resCmds, resStats, resStatus] = await Promise.all([
        fetch('http://localhost:5000/api/attacks'),
        fetch('http://localhost:5000/api/commands'),
        fetch('http://localhost:5000/api/stats'),
        fetch('http://localhost:5000/api/status')
      ]);

      if (resAttacks.ok) setAttacks(await resAttacks.json());
      if (resCmds.ok) setCommands(await resCmds.json());
      if (resStats.ok) setStats(await resStats.json());
      if (resStatus.ok) {
        const statusData = await resStatus.json();
        setIsHoneypotActive(statusData.active);
      }
    } catch (err) {
      console.error("Erreur de connexion API :", err);
      setIsHoneypotActive(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 3000);
    return () => clearInterval(interval);
  }, []);

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    
    let formattedString = dateString;
    if (!dateString.endsWith('Z') && !dateString.includes('+') && !dateString.includes('-', 10)) {
      formattedString = dateString + 'Z'; 
    }

    const date = new Date(formattedString);
    if (isNaN(date.getTime())) return dateString;

    return date.toLocaleString('fr-FR', {
      timeZone: 'Europe/Paris',
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit'
    });
  };

  const handleRowClick = (timestamp) => {
    if (selectedSessions.includes(timestamp)) {
      setSelectedSessions(selectedSessions.filter(t => t !== timestamp));
    } else {
      setSelectedSessions([...selectedSessions, timestamp]);
    }
  };

  const handleToggleSelectAll = () => {
    const allTimestamps = attacks.map(att => att.timestamp).filter(Boolean);
    if (selectedSessions.length === allTimestamps.length) {
      setSelectedSessions([]);
    } else {
      setSelectedSessions(allTimestamps);
    }
  };

  const sortedAttacks = [...attacks].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));

  const filteredCommands = commands.filter(cmd => {
    const cmdDate = new Date(cmd.timestamp);

    return selectedSessions.some(sessionTimestamp => {
      const currentAttack = sortedAttacks.find(a => a.timestamp === sessionTimestamp);
      if (!currentAttack) return false;

      if (cmd.ip_address !== currentAttack.ip_address) return false;

      const startDate = new Date(currentAttack.timestamp);
      const nextAttack = sortedAttacks.find(
        a => a.ip_address === currentAttack.ip_address && new Date(a.timestamp) > startDate
      );
      const endDate = nextAttack ? new Date(nextAttack.timestamp) : new Date();

      return cmdDate >= startDate && cmdDate < endDate;
    });
  });

  const allTimestampsCount = attacks.map(att => att.timestamp).filter(Boolean).length;
  const isAllSelected = allTimestampsCount > 0 && selectedSessions.length === allTimestampsCount;

  return (
    <div className="container">
      {/* En-tête flex : Titre + Pastille à gauche, Horloge tout en haut à droite */}
      <div className="top-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '30px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
          <h1 style={{ margin: 0 }}>Winnie The Pooh Dashboard</h1>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', backgroundColor: '#1e293b', padding: '6px 12px', borderRadius: '20px', border: '1px solid #334155' }}>
            <span 
              style={{
                width: '10px',
                height: '10px',
                borderRadius: '50%',
                backgroundColor: isHoneypotActive ? '#22c55e' : '#ef4444',
                boxShadow: isHoneypotActive ? '0 0 8px #22c55e' : '0 0 8px #ef4444',
                display: 'inline-block'
              }}
            ></span>
            <span style={{ fontSize: '0.8rem', color: '#94a3b8', fontWeight: '500' }}>
              {isHoneypotActive ? 'Actif' : 'Inactif'}
            </span>
          </div>
        </div>

        <div className="live-clock" style={{ backgroundColor: '#1e293b', padding: '10px 18px', borderRadius: '8px', fontFamily: 'monospace', textAlign: 'right', border: '1px solid #334155', boxShadow: '0 4px 6px -1px rgba(0, 0, 0, 0.1)' }}>
          <div className="clock-time" style={{ fontSize: '1.4rem', fontWeight: 'bold', color: '#38bdf8' }}>
            {currentTime.toLocaleTimeString('fr-FR', { timeZone: 'Europe/Paris' })}
          </div>
          <div className="clock-date" style={{ fontSize: '0.8rem', color: '#94a3b8', textTransform: 'capitalize' }}>
            {currentTime.toLocaleDateString('fr-FR', { 
              timeZone: 'Europe/Paris',
              weekday: 'long', 
              year: 'numeric', 
              month: 'long', 
              day: 'numeric' 
            })}
          </div>
        </div>
      </div>

      <div className="grid-2">
        <div className="card">
          <h3>Attaques Totales</h3>
          <p className="big-number">{stats?.total_attacks || attacks.length}</p>
        </div>

        <div className="card">
          <h3>Pays d'origine</h3>
          <ul className="list">
            {stats?.top_countries && stats.top_countries.length > 0 ? (
              stats.top_countries.map((c, i) => (
                <li key={i}>{c.country} ({c.count} attaques)</li>
              ))
            ) : (
              <li>Non spécifié / Local</li>
            )}
          </ul>
        </div>
      </div>

      <div className="card">
        <div className="card-header-flex">
          <h3>Flux Direct</h3>
          {attacks.length > 0 && (
            <button className="btn-reset" onClick={handleToggleSelectAll}>
              {isAllSelected ? 'Tout masquer ✕' : 'Tout afficher ✓'}
            </button>
          )}
        </div>
        <table>
          <thead>
            <tr>
              <th>Heure</th>
              <th>IP Attaquante</th>
              <th>Utilisateur</th>
              <th>Mot de passe</th>
              <th>Pays</th>
            </tr>
          </thead>
          <tbody>
            {attacks.length === 0 ? (
              <tr>
                <td colSpan="5" className="muted" style={{ textAlign: 'center', padding: '20px' }}>
                  Aucune attaque enregistrée pour le moment...
                </td>
              </tr>
            ) : (
              attacks.map((att, index) => {
                const sessionKey = att.timestamp;
                const isSelected = selectedSessions.includes(sessionKey);
                return (
                  <tr 
                    key={index} 
                    onClick={() => handleRowClick(sessionKey)}
                    className={`clickable-row ${isSelected ? 'row-selected' : ''}`}
                    title="Cliquer pour afficher/masquer cette session"
                  >
                    <td>{formatDate(att.timestamp)}</td>
                    <td>
                      <span className="ip-link">{att.ip_address || 'Inconnue'}</span>
                    </td>
                    <td>{att.username}</td>
                    <td>{att.password}</td>
                    <td>{att.country || 'N/A'}</td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="card">
        <div className="card-header-flex">
          <h3>Commandes saisies dans le Honeypot</h3>
          {selectedSessions.length > 0 && (
            <button className="btn-reset" onClick={() => setSelectedSessions([])}>
              Tout masquer ({selectedSessions.length} session{selectedSessions.length > 1 ? 's' : ''}) ✕
            </button>
          )}
        </div>
        <div className="console">
          {selectedSessions.length === 0 ? (
            <p className="muted">Sélectionne une ou plusieurs sessions ci-dessus pour afficher leurs saisies.</p>
          ) : filteredCommands.length === 0 ? (
            <p className="muted">Aucune commande enregistrée pour cette/ces session(s).</p>
          ) : (
            filteredCommands.map((cmd, index) => (
              <div key={index} className="console-line">
                <span className="muted">[{formatDate(cmd.timestamp)}]</span>
                <span className="ip-highlight">{cmd.ip_address}</span>
                <span className="cmd">$ {cmd.command}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

export default App;