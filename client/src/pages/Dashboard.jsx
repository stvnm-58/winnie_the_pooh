import React from 'react';
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
  // Helper robuste pour parser les dates de SQLite (YYYY-MM-DD HH:MM:SS)
  const parseDate = (dateString) => {
    if (!dateString) return new Date(0);
    let str = dateString;
    if (!str.endsWith('Z') && !str.includes('+') && !str.includes('T')) {
      str = str.replace(' ', 'T') + 'Z';
    }
    return new Date(str);
  };

  const sortedAttacks = [...attacks].sort((a, b) => parseDate(a.timestamp) - parseDate(b.timestamp));

  const filteredCommands = commands.filter(cmd => {
    const cmdDate = parseDate(cmd.timestamp);
    return selectedSessions.some(sessionTimestamp => {
      const currentAttack = sortedAttacks.find(a => a.timestamp === sessionTimestamp);
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