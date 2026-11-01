import { useEffect, useMemo, useState } from 'react';
import { apiFetch } from '../api';
import {
  countAttacksByPort,
  filterAttacksByPort,
  getAvailablePorts,
  parseDate
} from '../attackUtils';
import useBannedIps from '../hooks/useBannedIps';
import './Dashboard.css';

// Vue de surveillance : statistiques et flux d'attaques à gauche, filtre des honeypots à droite.
export default function Dashboard({ 
  attacks, 
  commands, 
  stats, 
  activeHoneypots,
  selectedSessions, 
  handleRowClick, 
  handleToggleSelectAll, 
  formatDate 
}) {
  // État d'interface : tri, action de pare-feu en cours et port affiché.
  const [sortConfig, setSortConfig] = useState({ key: 'timestamp', direction: 'desc' });
  const [banLoadingIp, setBanLoadingIp] = useState(null);
  const { bannedIps, refreshBannedIps: fetchBannedIps } = useBannedIps();
  
  const [selectedPortFilter, setSelectedPortFilter] = useState(() => {
    return localStorage.getItem('winnie_last_honeypot') || 'ALL';
  });

  useEffect(() => {
    localStorage.setItem('winnie_last_honeypot', selectedPortFilter);
  }, [selectedPortFilter]);

  const handleToggleBan = async (ipAddress) => {
    if (!ipAddress || ipAddress === 'Inconnue' || ipAddress === 'N/A') return;
    
    const isBanned = bannedIps.includes(ipAddress);
    const endpoint = isBanned ? '/unban' : '/ban';
    
    setBanLoadingIp(ipAddress);
    try {
      const res = await apiFetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ip: ipAddress })
      });
      const data = await res.json();
      if (res.ok) {
        await fetchBannedIps();
      } else {
        alert(data.error || "Erreur lors de l'action sur le pare-feu.");
      }
    } catch {
      alert("Erreur de connexion réseau avec l'API Flask.");
    } finally {
      setBanLoadingIp(null);
    }
  };

  // Prépare les ports, attaques, pays et commandes correspondant au filtre sélectionné.
  const availablePorts = useMemo(
    () => getAvailablePorts(activeHoneypots, attacks),
    [activeHoneypots, attacks]
  );

  const filteredByPortAttacks = useMemo(
    () => filterAttacksByPort(attacks, selectedPortFilter),
    [attacks, selectedPortFilter]
  );

  const filteredTopCountries = useMemo(() => Object.entries(
    filteredByPortAttacks.reduce((counts, attack) => {
      if (attack.country) counts[attack.country] = (counts[attack.country] || 0) + 1;
      return counts;
    }, {})
  )
    .map(([country, count]) => ({ country, count }))
    .sort((a, b) => b.count - a.count), [filteredByPortAttacks]);

  const visibleAttackIds = filteredByPortAttacks.map(attack => attack.id);
  const areVisibleAttacksSelected = visibleAttackIds.length > 0
    && visibleAttackIds.every(id => selectedSessions.includes(id));

  const handleSort = (key) => {
    let direction = 'asc';
    if (sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
  };

  const sortedAttacks = useMemo(() => [...filteredByPortAttacks].sort((a, b) => {
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
  }), [filteredByPortAttacks, sortConfig]);

  // Reconstitue les fenêtres de session à partir des attaques successives d'une même IP/port.
  const attacksById = useMemo(
    () => new Map(filteredByPortAttacks.map(attack => [attack.id, attack])),
    [filteredByPortAttacks]
  );

  const nextAttackById = useMemo(() => {
    const groups = new Map();
    for (const attack of filteredByPortAttacks) {
      const key = JSON.stringify([attack.ip_address, attack.port || 2222]);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(attack);
    }

    const nextAttacks = new Map();
    for (const group of groups.values()) {
      group.sort((a, b) => parseDate(a.timestamp) - parseDate(b.timestamp));
      const timestamps = group.map(attack => parseDate(attack.timestamp).getTime());
      let nextIndex = 1;
      for (let index = 0; index < group.length; index += 1) {
        while (nextIndex < group.length && timestamps[nextIndex] <= timestamps[index]) {
          nextIndex += 1;
        }
        if (nextIndex < group.length) {
          nextAttacks.set(group[index].id, group[nextIndex]);
        }
      }
    }
    return nextAttacks;
  }, [filteredByPortAttacks]);

  const sessionWindows = useMemo(() => {
    const windowsBySession = new Map();
    for (const sessionId of selectedSessions) {
      const attack = attacksById.get(sessionId);
      if (!attack) continue;
      const key = JSON.stringify([attack.ip_address, attack.port || 2222]);
      const nextAttack = nextAttackById.get(attack.id);
      const window = {
        start: parseDate(attack.timestamp).getTime(),
        end: nextAttack ? parseDate(nextAttack.timestamp).getTime() : Number.POSITIVE_INFINITY
      };
      if (!windowsBySession.has(key)) windowsBySession.set(key, []);
      windowsBySession.get(key).push(window);
    }
    return windowsBySession;
  }, [attacksById, nextAttackById, selectedSessions]);

  const sortedFilteredCommands = useMemo(() => commands
    .filter(command => {
      const key = JSON.stringify([command.ip_address, command.port || 2222]);
      const windows = sessionWindows.get(key);
      if (!windows) return false;
      const commandTime = parseDate(command.timestamp).getTime();
      return windows.some(window => commandTime >= window.start && commandTime < window.end);
    })
    .sort((a, b) => parseDate(a.timestamp) - parseDate(b.timestamp)),
  [commands, sessionWindows]);

  const attackCountsByPort = useMemo(() => countAttacksByPort(attacks), [attacks]);

  const getSortIndicator = (key) => {
    if (sortConfig.key !== key) return ' ↕';
    return sortConfig.direction === 'asc' ? ' ▲' : ' ▼';
  };

  return (
    <div className="dashboard-main-grid">
      
      {/* COLONNE GAUCHE : STATISTIQUES, TABLEAU & CONSOLE */}
      <div>
        {/* Résumé en haut de la colonne : volume d'attaques et répartition par pays. */}
        <div className="grid-2">
          {/* Carte de volume : total global ou nombre d'attaques sur le port filtré. */}
          <div className="card">
            <h3>{selectedPortFilter === 'ALL' ? 'Attaques Totales' : `Attaques (Port ${selectedPortFilter})`}</h3>
            <p className="big-number">
              {selectedPortFilter === 'ALL'
                ? (stats?.total_attacks ?? attacks.length)
                : filteredByPortAttacks.length}
            </p>
          </div>

          {/* Carte de pays : classement global ou recalculé pour le port sélectionné. */}
          <div className="card">
            <h3>Pays d'origine</h3>
            <div className="country-list-scroll">
              <ul className="list">
                {(selectedPortFilter === 'ALL' ? stats?.top_countries : filteredTopCountries)?.length > 0 ? (
                  (selectedPortFilter === 'ALL' ? stats.top_countries : filteredTopCountries).map((c, i) => (
                    <li key={i}>{c.country} ({c.count} attaques)</li>
                  ))
                ) : (
                  <li>Non spécifié / Local</li>
                )}
              </ul>
            </div>
          </div>
        </div>

        {/* Tableau du flux : tri par colonne, sélection des sessions et action bannir/débannir. */}
        <div className="card">
          <div className="card-header-flex dashboard-header-wrap">
            <h3>Flux Direct {selectedPortFilter !== 'ALL' && `- Focus Port ${selectedPortFilter}`}</h3>
            
            {filteredByPortAttacks.length > 0 && (
              <button className="btn-reset" onClick={() => handleToggleSelectAll(visibleAttackIds)}>
                {areVisibleAttacksSelected ? 'Tout masquer ✕' : 'Tout afficher ✓'}
              </button>
            )}
          </div>

          <div className="dashboard-table-wrapper">
            <table>
              <thead>
                <tr>
                  <th onClick={() => handleSort('timestamp')}>Date & Heure{getSortIndicator('timestamp')}</th>
                  <th onClick={() => handleSort('port')}>Port Piégé{getSortIndicator('port')}</th>
                  <th onClick={() => handleSort('ip_address')}>IP Attaquante{getSortIndicator('ip_address')}</th>
                  <th onClick={() => handleSort('country')}>Pays{getSortIndicator('country')}</th>
                  <th onClick={() => handleSort('username')}>Utilisateur{getSortIndicator('username')}</th>
                  <th onClick={() => handleSort('password')}>Mot de passe{getSortIndicator('password')}</th>
                  <th>Actions Pare-feu</th>
                </tr>
              </thead>
              <tbody>
                {sortedAttacks.length === 0 ? (
                  <tr>
                    <td colSpan="7" className="muted dashboard-empty-cell">
                      Aucune attaque enregistrée pour ce honeypot...
                    </td>
                  </tr>
                ) : (
                  sortedAttacks.map((att) => {
                    const sessionKey = att.id;
                    const isSelected = selectedSessions.includes(sessionKey);
                    const isBanned = bannedIps.includes(att.ip_address);
                    const isThisLoading = banLoadingIp === att.ip_address;
                    const hasValidCountry = att.country && att.country !== 'Unknown' && att.country !== 'Local Network';

                    return (
                      <tr 
                        key={att.id}
                        className={`clickable-row ${isSelected ? 'row-selected' : ''}`}
                      >
                        <td onClick={() => handleRowClick(sessionKey)}>{formatDate(att.timestamp)}</td>
                        <td onClick={() => handleRowClick(sessionKey)}>
                          <span className="dashboard-port-badge">{att.port || 2222}</span>
                        </td>
                        <td onClick={() => handleRowClick(sessionKey)}>
                          <span className="ip-link">{att.ip_address || 'Inconnue'}</span>
                        </td>
                        <td onClick={() => handleRowClick(sessionKey)}>
                          <span className={hasValidCountry ? 'dashboard-country-highlight' : 'muted'}>
                            {att.country || 'Unknown'}
                          </span>
                        </td>
                        <td onClick={() => handleRowClick(sessionKey)}>{att.username}</td>
                        <td onClick={() => handleRowClick(sessionKey)}>{att.password}</td>
                        <td>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              handleToggleBan(att.ip_address);
                            }}
                            disabled={isThisLoading || !att.ip_address || att.ip_address === '127.0.0.1'}
                            className={`dashboard-ban-btn ${isBanned ? 'is-banned' : 'is-active'} ${isThisLoading ? 'is-loading' : ''}`}
                          >
                            {isThisLoading ? '...' : (isBanned ? 'Débannir 🛡️' : 'Bannir 🚫')}
                          </button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Console des commandes enregistrées pour les sessions sélectionnées dans le tableau. */}
        <div className="card">
          <div className="card-header-flex">
            <h3>Commandes saisies dans le Honeypot</h3>
            {selectedSessions.length > 0 && (
              <button className="btn-reset" onClick={() => handleRowClick(null)}>
                Tout masquer ({selectedSessions.length}) ✕
              </button>
            )}
          </div>
          <div className="console">
            {selectedSessions.length === 0 ? (
              <p className="muted">Sélectionnez une ou plusieurs sessions ci-dessus pour afficher leurs saisies.</p>
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

      {/* COLONNE DROITE : PANNEAU LATÉRAL DE SÉLECTION DE HONEYPOT */}
      <div>
        {/* Panneau latéral droit : filtre global ou par port, avec statut et nombre d'attaques. */}
        <div className="card dashboard-sticky-card">
          <h3 className="dashboard-sidebar-title">Swarm</h3>
          <p className="muted dashboard-sidebar-subtitle">
            Sélectionnez une instance pour filtrer le tableau de bord :
          </p>

          <div className="dashboard-sidebar-stack">
            <button
              onClick={() => setSelectedPortFilter('ALL')}
              className={`dashboard-sidebar-btn ${selectedPortFilter === 'ALL' ? 'is-active' : ''}`}
            >
              <span>Vue Globale</span>
              <span className="dashboard-sidebar-count">({attacks.length})</span>
            </button>

            <hr className="dashboard-sidebar-divider" />

            {/* Liste des ports : défile quand il y a beaucoup de honeypots */}
            <div className="dashboard-port-scroll">
              {availablePorts.map((port) => {
                const isLive = (activeHoneypots || []).some(h => h.port === port);
                const count = attackCountsByPort.get(port) || 0;
                const isSelected = selectedPortFilter === String(port);

                return (
                  <button
                    key={port}
                    onClick={() => setSelectedPortFilter(String(port))}
                    className={`dashboard-sidebar-btn dashboard-port-row ${isSelected ? 'is-active' : ''}`}
                  >
                    <div className="dashboard-port-info">
                      <span className={`dashboard-status-dot ${isLive ? 'is-live' : 'is-offline'}`}></span>
                      <span className="dashboard-port-label">Port {port}</span>
                    </div>

                    <span className="dashboard-port-attacks-count">
                      {count} attaque{count > 1 ? 's' : ''}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      </div>

    </div>
  );
}
