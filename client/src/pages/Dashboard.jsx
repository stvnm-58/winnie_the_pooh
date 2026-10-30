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
  // Construit le tableau des attaques, les commandes de session et les actions du pare-feu.
  const [sortConfig, setSortConfig] = useState({ key: 'timestamp', direction: 'desc' });
  const [banLoadingIp, setBanLoadingIp] = useState(null);
  const { bannedIps, refreshBannedIps: fetchBannedIps } = useBannedIps();
  
  // Persistance du dernier honeypot sélectionné dans le localStorage
  const [selectedPortFilter, setSelectedPortFilter] = useState(() => {
    return localStorage.getItem('winnie_last_honeypot') || 'ALL';
  });

  // Mémorise le filtre de port sélectionné entre les visites de la page.
  useEffect(() => {
    localStorage.setItem('winnie_last_honeypot', selectedPortFilter);
  }, [selectedPortFilter]);

  const handleToggleBan = async (ipAddress) => {
    // Bascule le bannissement de l'adresse et recharge la liste après la modification.
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

  // Liste globale des ports (armada active + historique)
  const availablePorts = useMemo(
    () => getAvailablePorts(activeHoneypots, attacks),
    [activeHoneypots, attacks]
  );

  // Filtrage des attaques par port
  const filteredByPortAttacks = useMemo(
    () => filterAttacksByPort(attacks, selectedPortFilter),
    [attacks, selectedPortFilter]
  );

  // Recalcule localement les pays affichés quand un seul port est sélectionné.
  const filteredTopCountries = useMemo(() => Object.entries(
    filteredByPortAttacks.reduce((counts, attack) => {
      if (attack.country) counts[attack.country] = (counts[attack.country] || 0) + 1;
      return counts;
    }, {})
  )
    .map(([country, count]) => ({ country, count }))
    .sort((a, b) => b.count - a.count)
    .slice(0, 5), [filteredByPortAttacks]);

  const visibleAttackIds = filteredByPortAttacks.map(attack => attack.id);
  const areVisibleAttacksSelected = visibleAttackIds.length > 0
    && visibleAttackIds.every(id => selectedSessions.includes(id));

  const handleSort = (key) => {
    // Trie une nouvelle colonne par ordre croissant, puis inverse le sens au clic suivant.
    let direction = 'asc';
    if (sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
  };

  // Trie une copie pour ne modifier ni l'état React ni la liste d'attaques d'origine.
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

  const attacksById = useMemo(
    () => new Map(filteredByPortAttacks.map(attack => [attack.id, attack])),
    [filteredByPortAttacks]
  );

  // Associe chaque attaque à la tentative suivante de la même IP et du même port.
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

  // Transforme les attaques sélectionnées en intervalles pour retrouver leurs commandes.
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

  // Affiche dans l'ordre chronologique les commandes comprises dans les sessions sélectionnées.
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
    // Indique la colonne triée et le sens du tri dans l'en-tête du tableau.
    if (sortConfig.key !== key) return ' ↕';
    return sortConfig.direction === 'asc' ? ' ▲' : ' ▼';
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: '20px' }}>
      
      {/* COLONNE GAUCHE : STATISTIQUES, TABLEAU & CONSOLE */}
      <div>
        <div className="grid-2">
          <div className="card">
            <h3>{selectedPortFilter === 'ALL' ? 'Attaques Totales' : `Attaques (Port ${selectedPortFilter})`}</h3>
            <p className="big-number">
              {selectedPortFilter === 'ALL'
                ? (stats?.total_attacks ?? attacks.length)
                : filteredByPortAttacks.length}
            </p>
          </div>

          <div className="card">
            <h3>Pays d'origine</h3>
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

        <div className="card">
          <div className="card-header-flex" style={{ flexWrap: 'wrap', gap: '15px' }}>
            <h3>Flux Direct {selectedPortFilter !== 'ALL' && `- Focus Port ${selectedPortFilter}`}</h3>
            
            {filteredByPortAttacks.length > 0 && (
              <button className="btn-reset" onClick={() => handleToggleSelectAll(visibleAttackIds)}>
                {areVisibleAttacksSelected ? 'Tout masquer ✕' : 'Tout afficher ✓'}
              </button>
            )}
          </div>

          {/* Conteneur défilant pour limiter l'affichage vertical */}
          <div style={{ maxHeight: '420px', overflowY: 'auto', overflowX: 'auto', border: '1px solid #1e293b', borderRadius: '6px' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead style={{ position: 'sticky', top: 0, backgroundColor: '#0f172a', zIndex: 1 }}>
                <tr>
                  <th onClick={() => handleSort('timestamp')} style={{ cursor: 'pointer' }}>Date & Heure{getSortIndicator('timestamp')}</th>
                  <th onClick={() => handleSort('port')} style={{ cursor: 'pointer' }}>Port Piégé{getSortIndicator('port')}</th>
                  <th onClick={() => handleSort('ip_address')} style={{ cursor: 'pointer' }}>IP Attaquante{getSortIndicator('ip_address')}</th>
                  <th onClick={() => handleSort('country')} style={{ cursor: 'pointer' }}>Pays{getSortIndicator('country')}</th>
                  <th onClick={() => handleSort('username')} style={{ cursor: 'pointer' }}>Utilisateur{getSortIndicator('username')}</th>
                  <th onClick={() => handleSort('password')} style={{ cursor: 'pointer' }}>Mot de passe{getSortIndicator('password')}</th>
                  <th>Actions Pare-feu</th>
                </tr>
              </thead>
              <tbody>
                {sortedAttacks.length === 0 ? (
                  <tr>
                    <td colSpan="7" className="muted" style={{ textAlign: 'center', padding: '20px' }}>
                      Aucune attaque enregistrée pour ce honeypot...
                    </td>
                  </tr>
                ) : (
                  sortedAttacks.map((att) => {
                    const sessionKey = att.id;
                    const isSelected = selectedSessions.includes(sessionKey);
                    const isBanned = bannedIps.includes(att.ip_address);
                    const isThisLoading = banLoadingIp === att.ip_address;

                    return (
                      <tr 
                        key={att.id}
                        className={`clickable-row ${isSelected ? 'row-selected' : ''}`}
                      >
                        <td onClick={() => handleRowClick(sessionKey)}>{formatDate(att.timestamp)}</td>
                        <td onClick={() => handleRowClick(sessionKey)}><span style={{ backgroundColor: '#1e293b', padding: '2px 8px', borderRadius: '4px', color: '#38bdf8', fontWeight: 'bold' }}>{att.port || 2222}</span></td>
                        <td onClick={() => handleRowClick(sessionKey)}><span className="ip-link">{att.ip_address || 'Inconnue'}</span></td>
                        <td onClick={() => handleRowClick(sessionKey)}>
                          <span style={{ color: att.country && att.country !== 'Unknown' && att.country !== 'Local Network' ? '#38bdf8' : '#94a3b8' }}>
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
                            style={{
                              backgroundColor: isBanned ? '#22c55e' : '#ef4444',
                              color: '#fff',
                              border: 'none',
                              padding: '4px 8px',
                              borderRadius: '4px',
                              cursor: 'pointer',
                              fontSize: '0.75rem',
                              fontWeight: 'bold',
                              opacity: isThisLoading ? 0.6 : 1
                            }}
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

      {/* COLONNE DROITE : PANNEAU LATÉRAL DE SÉLECTION DE HONEYPOT UNIQUEMENT */}
      <div>
        <div className="card" style={{ position: 'sticky', top: '20px' }}>
          <h3 style={{ marginBottom: '15px' }}>Swarm</h3>
          <p className="muted" style={{ fontSize: '0.8rem', marginBottom: '15px' }}>
            Sélectionnez une instance pour filtrer le tableau de bord :
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <button
              onClick={() => setSelectedPortFilter('ALL')}
              style={{
                display: 'flex',
                justify: 'space-between',
                alignItems: 'center',
                padding: '10px 14px',
                borderRadius: '8px',
                border: '1px solid #334155',
                backgroundColor: selectedPortFilter === 'ALL' ? '#3b82f6' : '#0f172a',
                color: '#fff',
                cursor: 'pointer',
                fontWeight: 'bold',
                textAlign: 'left',
                width: '100%',
                boxSizing: 'border-box'
              }}
            >
              <span>🌐 Vue Globale</span>
              <span style={{ fontSize: '0.85rem', opacity: 0.9, marginLeft: '10px' }}>({attacks.length})</span>
            </button>

            <hr style={{ border: 'none', borderTop: '1px solid #334155', margin: '5px 0' }} />

            {availablePorts.map((port) => {
              const isLive = (activeHoneypots || []).some(h => h.port === port);
              const count = attackCountsByPort.get(port) || 0;
              const isSelected = selectedPortFilter === String(port);

              return (
                <button
                  key={port}
                  onClick={() => setSelectedPortFilter(String(port))}
                  style={{
                    display: 'flex',
                    justify: 'space-between',
                    alignItems: 'center',
                    padding: '10px 14px',
                    borderRadius: '8px',
                    border: '1px solid #334155',
                    backgroundColor: isSelected ? '#3b82f6' : '#0f172a',
                    color: '#fff',
                    cursor: 'pointer',
                    textAlign: 'left',
                    width: '100%',
                    boxSizing: 'border-box',
                    gap: '15px'
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: 1 }}>
                    <span style={{
                      width: '8px',
                      height: '8px',
                      borderRadius: '50%',
                      backgroundColor: isLive ? '#22c55e' : '#64748b',
                      flexShrink: 0
                    }}></span>
                    <span style={{ fontWeight: 'bold', whiteSpace: 'nowrap' }}>Port {port}</span>
                  </div>

                  <span style={{ 
                    fontSize: '0.80rem', 
                    color: isSelected ? '#ffffff' : '#94a3b8',
                    whiteSpace: 'nowrap',
                    marginLeft: 'auto'
                  }}>
                    {count} attaque{count > 1 ? 's' : ''}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

    </div>
  );
}