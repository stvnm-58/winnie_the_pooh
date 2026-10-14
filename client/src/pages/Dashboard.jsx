import React, { useState } from 'react';
import './Dashboard.css';

export default function Dashboard({ 
  attacks, 
  commands, 
  stats, 
  selectedSessions, 
  handleRowClick, 
  handleToggleSelectAll, 
  isAllSelected, 
  formatDate 
}) {
  // État pour la gestion du tri
  const [sortConfig, setSortConfig] = useState({ key: 'timestamp', direction: 'desc' });

  // Helper robuste pour parser les dates de SQLite (YYYY-MM-DD HH:MM:SS)
  const parseDate = (dateString) => {
    if (!dateString) return new Date(0);
    let str = dateString;
    if (!str.endsWith('Z') && !str.includes('+') && !str.includes('T')) {
      str = str.replace(' ', 'T') + 'Z';
    }
    return new Date(str);
  };

  // Fonction de gestion du clic sur les en-têtes pour le tri
  const handleSort = (key) => {
    let direction = 'asc';
    if (sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
  };

  // Tri des attaques selon la configuration actuelle
  const sortedAttacks = [...attacks].sort((a, b) => {
    let aValue = a[sortConfig.key];
    let bValue = b[sortConfig.key];

    if (sortConfig.key === 'timestamp' || sortConfig.key === 'date' || sortConfig.key === 'time') {
      aValue = parseDate(a.timestamp);
      bValue = parseDate(b.timestamp);
    } else {
      aValue = (aValue || '').toString().toLowerCase();
      bValue = (bValue || '').toString().toLowerCase();
    }

    if (aValue < bValue) return sortConfig.direction === 'asc' ? -1 : 1;
    if (aValue > bValue) return sortConfig.direction === 'asc' ? 1 : -1;
    return 0;
  });

  const filteredCommands = commands.filter(cmd => {
    const cmdDate = parseDate(cmd.timestamp);
    return selectedSessions.some(sessionTimestamp => {
      // On utilise sortedAttacks ou attacks de base pour retrouver la session
      const currentAttack = attacks.find(a => a.timestamp === sessionTimestamp);
      if (!currentAttack) return false;
      if (cmd.ip_address !== currentAttack.ip_address) return false;

      const startDate = parseDate(currentAttack.timestamp);
      const nextAttack = sortedAttacks.find(
        a => a.ip_address === currentAttack.ip_address && parseDate(a.timestamp) > startDate
      );
      const endDate = nextAttack ? parseDate(nextAttack.timestamp) : new Date();

      return cmdDate >= startDate && cmdDate < endDate;
    });
  });

  // Tri des commandes de la plus ancienne (haut) à la plus récente (bas)
  const sortedFilteredCommands = [...filteredCommands].sort((a, b) => parseDate(a.timestamp) - parseDate(b.timestamp));

  // Helper pour afficher la flèche de tri
  const getSortIndicator = (key) => {
    if (sortConfig.key !== key) return ' ↕';
    return sortConfig.direction === 'asc' ? ' ▲' : ' ▼';
  };

  return (
    <div>
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
              <th onClick={() => handleSort('timestamp')} style={{ cursor: 'pointer' }}>
                Date{getSortIndicator('timestamp')}
              </th>
              <th onClick={() => handleSort('timestamp')} style={{ cursor: 'pointer' }}>
                Heure{getSortIndicator('timestamp')}
              </th>
              <th onClick={() => handleSort('ip_address')} style={{ cursor: 'pointer' }}>
                IP Attaquante{getSortIndicator('ip_address')}
              </th>
              <th onClick={() => handleSort('username')} style={{ cursor: 'pointer' }}>
                Utilisateur{getSortIndicator('username')}
              </th>
              <th onClick={() => handleSort('password')} style={{ cursor: 'pointer' }}>
                Mot de passe{getSortIndicator('password')}
              </th>
              <th onClick={() => handleSort('country')} style={{ cursor: 'pointer' }}>
                Pays{getSortIndicator('country')}
              </th>
            </tr>
          </thead>
          <tbody>
            {attacks.length === 0 ? (
              <tr>
                <td colSpan="6" className="muted" style={{ textAlign: 'center', padding: '20px' }}>
                  Aucune attaque enregistrée pour le moment...
                </td>
              </tr>
            ) : (
              sortedAttacks.map((att, index) => {
                const sessionKey = att.timestamp;
                const isSelected = selectedSessions.includes(sessionKey);
                
                // Séparation de la date et de l'heure depuis le timestamp (ex: "2026-10-14 12:34:56")
                const [datePart, timePart] = att.timestamp ? att.timestamp.split(' ') : ['', ''];

                return (
                  <tr 
                    key={index} 
                    onClick={() => handleRowClick(sessionKey)}
                    className={`clickable-row ${isSelected ? 'row-selected' : ''}`}
                    title="Cliquer pour afficher/masquer cette session"
                  >
                    <td>{datePart}</td>
                    <td>{timePart}</td>
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
            <button className="btn-reset" onClick={() => handleRowClick(null)}>
              Tout masquer ({selectedSessions.length} session{selectedSessions.length > 1 ? 's' : ''}) ✕
            </button>
          )}
        </div>
        <div className="console">
          {selectedSessions.length === 0 ? (
            <p className="muted">Sélectionne une ou plusieurs sessions ci-dessus pour afficher leurs saisies.</p>
          ) : sortedFilteredCommands.length === 0 ? (
            <p className="muted">Aucune commande enregistrée pour cette/ces session(s).</p>
          ) : (
            sortedFilteredCommands.map((cmd, index) => (
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