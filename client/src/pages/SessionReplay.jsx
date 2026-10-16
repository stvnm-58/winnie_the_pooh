import { useState, useEffect, useMemo, useRef } from 'react';
import './SessionReplay.css';

function parseDate(dateString) {
  if (!dateString) return new Date(0);
  let str = dateString;
  if (!str.endsWith('Z') && !str.includes('+') && !str.includes('T')) {
    str = str.replace(' ', 'T') + 'Z';
  }
  return new Date(str);
}

export default function SessionReplay({ attacks, commands, activeHoneypots, formatDate }) {
  const [selectedReplaySession, setSelectedReplaySession] = useState('');
  const [currentReplayIndex, setCurrentReplayIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [replaySpeed, setReplaySpeed] = useState(1);
  
  // Persistance de la sélection du port pour le Replay
  const [selectedPortFilter, setSelectedPortFilter] = useState(() => {
    return localStorage.getItem('winnie_replay_last_honeypot') || 'ALL';
  });

  const terminalEndRef = useRef(null);

  useEffect(() => {
    localStorage.setItem('winnie_replay_last_honeypot', selectedPortFilter);
  }, [selectedPortFilter]);

  // Liste globale des ports (armada active + historique d'attaques)
  const availablePorts = useMemo(() => [...new Set([
    ...(activeHoneypots || []).map(h => h.port),
    ...attacks.map(a => a.port || 2222)
  ])].sort((a, b) => a - b), [activeHoneypots, attacks]);

  // Filtrage des attaques selon le port sélectionné dans le panneau
  const filteredAttacks = useMemo(() => attacks.filter(att => {
    if (selectedPortFilter === 'ALL') return true;
    return (att.port || 2222) === Number(selectedPortFilter);
  }), [attacks, selectedPortFilter]);

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

    // Prochaine attaque de la même IP sur le même port pour délimiter la fin de session
    const nextAttack = sortedAttacks.find(
      a => a.ip_address === targetAttack.ip_address 
        && (a.port || 2222) === targetPort
        && parseDate(a.timestamp) > startDate
    );
    const endDate = nextAttack ? parseDate(nextAttack.timestamp) : new Date();

    // Filtrage précis des commandes correspondantes
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
    setSelectedReplaySession(sessionId);
    setIsPlaying(false);
    setCurrentReplayIndex(0);
  };

  const handlePortFilterChange = (port) => {
    setSelectedPortFilter(port);
    handleSessionChange('');
  };

  // Logique de lecture automatique
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
    terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [currentReplayIndex]);

  const activeTargetAttack = targetAttack;

  const attackCountsByPort = useMemo(() => attacks.reduce((counts, attack) => {
    const port = attack.port || 2222;
    counts.set(port, (counts.get(port) || 0) + 1);
    return counts;
  }, new Map()), [attacks]);

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: '20px' }}>
      
      {/* COLONNE GAUCHE : REPLAY TERMINAL */}
      <div className="card">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px', flexWrap: 'nowrap', gap: '15px' }}>
          <h3 style={{ margin: 0, whiteSpace: 'nowrap' }}>
            Lecteur du Replay {selectedPortFilter !== 'ALL' && `- Port ${selectedPortFilter}`}
          </h3>
          
          <div className="replay-select-container" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <label style={{ fontSize: '0.9rem', color: '#94a3b8', whiteSpace: 'nowrap' }}>Choisir une session :</label>
            <select 
              value={selectedReplaySession} 
              onChange={(e) => handleSessionChange(e.target.value)}
              className="replay-select"
              style={{ 
                backgroundColor: '#0f172a', 
                color: '#fff', 
                border: '1px solid #334155', 
                padding: '6px 10px', 
                borderRadius: '6px',
                width: '320px',
                maxWidth: '100%',
                boxSizing: 'border-box'
              }}
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
          <div style={{ textAlign: 'center', padding: '50px', color: '#64748b' }}>
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
                <span style={{ fontSize: '0.85rem', color: '#94a3b8' }}>Vitesse :</span>
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
            <div className="console replay-terminal">
              <div style={{ color: '#475569', fontSize: '0.80rem', marginBottom: '15px' }}>
                [SYSTEM] Session sélectionnée sur le port {activeTargetAttack?.port || 2222} (IP: {activeTargetAttack?.ip_address}) - Connexion SSH simulée rétablie...
              </div>

              {sessionCommands.length === 0 ? (
                <p className="muted">Aucune commande enregistrée pour cette session spécifique.</p>
              ) : (
                sessionCommands.slice(0, currentReplayIndex).map((cmd, idx) => (
                  <div key={idx} style={{ marginBottom: '14px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#38bdf8' }}>
                      <span style={{ color: '#64748b' }}>root@ubuntu:~#</span>
                      <span style={{ fontWeight: 'bold' }}>{cmd.command}</span>
                    </div>
                    {cmd.response && (
                      <div style={{ color: '#cbd5e1', paddingLeft: '15px', marginTop: '4px', whiteSpace: 'pre-wrap', fontSize: '0.9rem', fontFamily: 'monospace' }}>
                        {cmd.response}
                      </div>
                    )}
                  </div>
                ))
              )}
              <div ref={terminalEndRef} />
            </div>

            {/* Barre de progression */}
            <div className="replay-progress-container">
              <span style={{ fontSize: '0.85rem', color: '#94a3b8', minWidth: '120px' }}>
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

      {/* COLONNE DROITE : PANNEAU LATÉRAL DE SÉLECTION DU HONEYPOT */}
      <div>
        <div className="card" style={{ position: 'sticky', top: '20px' }}>
          <h3 style={{ marginBottom: '15px' }}>🕸️ Deception Mesh</h3>
          <p className="muted" style={{ fontSize: '0.8rem', marginBottom: '15px' }}>
            Sélectionnez une instance pour filtrer les replays :
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
            {/* Bouton Vue Globale */}
            <button
              onClick={() => handlePortFilterChange('ALL')}
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
              <span>🌐 Tous les Replays</span>
              <span style={{ fontSize: '0.85rem', opacity: 0.9, marginLeft: '10px' }}>({attacks.length})</span>
            </button>

            <hr style={{ border: 'none', borderTop: '1px solid #334155', margin: '5px 0' }} />

            {/* Liste dynamique des ports */}
            {availablePorts.map((port) => {
              const isLive = (activeHoneypots || []).some(h => h.port === port);
              const count = attackCountsByPort.get(port) || 0;
              const isSelected = selectedPortFilter === String(port);

              return (
                <button
                  key={port}
                  onClick={() => handlePortFilterChange(String(port))}
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
                    fontSize: '0.8rem', 
                    color: isSelected ? '#ffffff' : '#94a3b8',
                    whiteSpace: 'nowrap',
                    marginLeft: 'auto'
                  }}>
                    {count} session{count > 1 ? 's' : ''}
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