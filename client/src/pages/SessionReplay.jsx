import { useState, useEffect, useMemo, useRef } from 'react';
import {
  countAttacksByPort,
  filterAttacksByPort,
  getAvailablePorts,
  parseDate
} from '../attackUtils';
import './SessionReplay.css';

// Lecteur de sessions : associe les commandes à une attaque puis les affiche progressivement dans un terminal simulé.
export default function SessionReplay({ attacks, commands, activeHoneypots, formatDate }) {
  // Gère ici la session choisie, la position de lecture et sa vitesse.
  const [selectedReplaySession, setSelectedReplaySession] = useState('');
  const [currentReplayIndex, setCurrentReplayIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [replaySpeed, setReplaySpeed] = useState(1);
  
  // Persistance de la sélection du port pour le Replay
  const [selectedPortFilter, setSelectedPortFilter] = useState(() => {
    return localStorage.getItem('winnie_replay_last_honeypot') || 'ALL';
  });

  const terminalRef = useRef(null);

  // Mémorise le filtre de port lors des changements de page.
  useEffect(() => {
    localStorage.setItem('winnie_replay_last_honeypot', selectedPortFilter);
  }, [selectedPortFilter]);

  // Réunit les ports actifs et ceux présents dans l'historique des attaques.
  const availablePorts = useMemo(
    () => getAvailablePorts(activeHoneypots, attacks),
    [activeHoneypots, attacks]
  );

  // Filtre les sessions par port, sauf si l'affichage global est sélectionné.
  const filteredAttacks = useMemo(
    () => filterAttacksByPort(attacks, selectedPortFilter),
    [attacks, selectedPortFilter]
  );

  // Retrouve l'attaque choisie pour déterminer l'intervalle de commandes associé.
  const targetAttack = useMemo(() => attacks.find(a =>
    String(a.id) === String(selectedReplaySession) || a.timestamp === selectedReplaySession
  ), [attacks, selectedReplaySession]);

  const sortedAttacks = useMemo(
    () => [...attacks].sort((a, b) => parseDate(a.timestamp) - parseDate(b.timestamp)),
    [attacks]
  );

  const sessionCommands = useMemo(() => {
    if (!selectedReplaySession || !targetAttack) return [];
    const startDate = parseDate(targetAttack.timestamp);
    const targetPort = targetAttack.port || 2222;

    // La prochaine attaque de la même IP et du même port marque la fin de la session.
    const nextAttack = sortedAttacks.find(
      a => a.ip_address === targetAttack.ip_address 
        && (a.port || 2222) === targetPort
        && parseDate(a.timestamp) > startDate
    );
    const endDate = nextAttack ? parseDate(nextAttack.timestamp) : new Date();

    // Les commandes n'ont pas d'identifiant d'attaque : l'association repose sur l'IP, le port et la date.
    const filtered = commands.filter(cmd => {
      const cmdDate = parseDate(cmd.timestamp);
      const cmdPort = cmd.port || 2222;
      return cmd.ip_address === targetAttack.ip_address 
        && cmdPort === targetPort
        && cmdDate >= startDate 
        && cmdDate < endDate;
    });

    const sortedFilteredCommands = filtered.sort((a, b) => parseDate(a.timestamp) - parseDate(b.timestamp));
    return sortedFilteredCommands;
  }, [selectedReplaySession, targetAttack, sortedAttacks, commands]);

  const handleSessionChange = (sessionId) => {
    // Repart de zéro et arrête la lecture lorsqu'une autre session est sélectionnée.
    setSelectedReplaySession(sessionId);
    setIsPlaying(false);
    setCurrentReplayIndex(0);
  };

  const handlePortFilterChange = (port) => {
    // Efface la session courante, qui peut ne pas correspondre au nouveau port.
    setSelectedPortFilter(port);
    handleSessionChange('');
  };

  // Affiche les commandes une par une et arrête la lecture à la fin de la session.
  useEffect(() => {
    let interval;
    if (isPlaying) {
      interval = setInterval(() => {
        setCurrentReplayIndex(prev => {
          if (prev < sessionCommands.length) {
            const nextIndex = prev + 1;
            if (nextIndex >= sessionCommands.length) {
              setIsPlaying(false);
              return sessionCommands.length;
            }
            return nextIndex;
          } else {
            setIsPlaying(false);
            clearInterval(interval);
            return prev;
          }
        });
      }, 1500 / replaySpeed);
    }
    return () => clearInterval(interval);
  }, [isPlaying, sessionCommands.length, replaySpeed]);

  useEffect(() => {
    // Garde la dernière commande affichée visible pendant la lecture.
    const terminal = terminalRef.current;
    if (terminal) {
      // Modification directe de scrollTop pour bloquer le scroll à l'interne du terminal
      terminal.scrollTop = terminal.scrollHeight;
    }
  }, [currentReplayIndex]);

  // Calcule les totaux par port utilisés dans le sélecteur latéral.
  const attackCountsByPort = useMemo(() => countAttacksByPort(attacks), [attacks]);

  return (
    <div className="replay-grid-layout">
      
      {/* Colonne gauche : sélection de session, commandes de lecture, terminal et progression. */}
      <div className="card">
        <div className="replay-header">
          <h3 className="replay-title">
            Lecteur du Replay {selectedPortFilter !== 'ALL' && `- Port ${selectedPortFilter}`}
          </h3>
          
          <div className="replay-select-container">
            <label className="replay-select-label">Choisir une session :</label>
            <select 
              value={selectedReplaySession} 
              onChange={(e) => handleSessionChange(e.target.value)}
              className="replay-select"
            >
              <option value="">-- Sélectionner une session ({filteredAttacks.length}) --</option>
              {filteredAttacks.map((att, idx) => (
                <option key={idx} value={att.id !== undefined ? att.id : att.timestamp}>
                  {formatDate(att.timestamp)} | Port {att.port || 2222} | IP: {att.ip_address} ({att.username})
                </option>
              ))}
            </select>
          </div>
        </div>

        {!selectedReplaySession ? (
          <div className="replay-empty-state">
            <p>Veuillez sélectionner une session dans le menu déroulant ci-dessus ou filtrer par honeypot à droite.</p>
          </div>
        ) : (
          <div>
            {/* Contrôles de lecture */}
            <div className="replay-controls">
              <div className="replay-btn-group">
                <button 
                  onClick={() => setIsPlaying(!isPlaying)}
                  className={`btn-play ${isPlaying ? 'playing' : 'paused'}`}
                >
                  {isPlaying ? '⏸ Pause' : (currentReplayIndex >= sessionCommands.length ? '▶ Rejouer' : '▶ Lecture')}
                </button>
                <button 
                  onClick={() => { setIsPlaying(false); setCurrentReplayIndex(0); }}
                  className="btn-reset-replay"
                  title="Recommencer au début"
                >
                  🔄 Reset
                </button>
              </div>

              <div className="replay-btn-group">
                <span className="replay-speed-label">Vitesse :</span>
                {[1, 2, 5].map(s => (
                  <button
                    key={s}
                    onClick={() => setReplaySpeed(s)}
                    className={`speed-btn ${replaySpeed === s ? 'active' : 'inactive'}`}
                  >
                    {s}x
                  </button>
                ))}
              </div>
            </div>

            {/* Terminal interactif */}
            <div className="console replay-terminal" ref={terminalRef}>
              <div className="replay-terminal-system">
                [SYSTEM] Session sélectionnée sur le port {targetAttack?.port || 2222} (IP: {targetAttack?.ip_address}) - Connexion SSH simulée rétablie...
              </div>

              {sessionCommands.length === 0 ? (
                <p className="muted">Aucune commande enregistrée pour cette session spécifique.</p>
              ) : (
                sessionCommands.slice(0, currentReplayIndex).map((cmd, idx) => (
                  <div key={idx} className="replay-cmd-block">
                    <div className="replay-cmd-line">
                      <span className="replay-prompt">root@ubuntu:~#</span>
                      <span className="replay-command-text">{cmd.command}</span>
                    </div>
                    {cmd.response && (
                      <div className="replay-response-text">
                        {cmd.response}
                      </div>
                    )}
                  </div>
                ))
              )}
            </div>

            {/* Barre de progression */}
            <div className="replay-progress-container">
              <span className="replay-progress-label">
                Action {currentReplayIndex} / {sessionCommands.length}
              </span>
              <input 
                type="range" 
                min="0" 
                max={sessionCommands.length} 
                value={currentReplayIndex}
                onChange={(e) => {
                  setIsPlaying(false);
                  setCurrentReplayIndex(Number(e.target.value));
                }}
                className="replay-progress-bar"
              />
            </div>
          </div>
        )}
      </div>

      {/* Panneau latéral droit : filtre tous les replays ou ceux d'un port précis. */}
      <div>
        <div className="card replay-sidebar-card">
          <h3 className="replay-sidebar-title">Swarm</h3>
          <p className="muted replay-sidebar-subtitle">
            Sélectionnez une instance pour filtrer les replays :
          </p>

          <div className="replay-sidebar-list">
            {/* Bouton Vue Globale */}
            <button
              onClick={() => handlePortFilterChange('ALL')}
              className={`replay-sidebar-btn ${selectedPortFilter === 'ALL' ? 'is-selected' : ''}`}
            >
              <span>Tous les Replays</span>
              <span className="replay-sidebar-count">({attacks.length})</span>
            </button>

            <hr className="replay-sidebar-divider" />

            {/* Liste des ports défilante, comme celle du panneau Swarm du tableau de bord. */}
            <div className="replay-port-scroll">
              {availablePorts.map((port) => {
                const isLive = (activeHoneypots || []).some(h => h.port === port);
                const count = attackCountsByPort.get(port) || 0;
                const isSelected = selectedPortFilter === String(port);

                return (
                  <button
                    key={port}
                    onClick={() => handlePortFilterChange(String(port))}
                    className={`replay-sidebar-btn replay-port-btn ${isSelected ? 'is-selected' : ''}`}
                  >
                    <div className="replay-port-info">
                      <span className={`replay-status-dot ${isLive ? 'is-live' : 'is-offline'}`}></span>
                      <span className="replay-port-label">Port {port}</span>
                    </div>

                    <span className="replay-port-count">
                      {count} session{count > 1 ? 's' : ''}
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
