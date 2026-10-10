import React, { useState, useEffect, useRef } from 'react';
import './SessionReplay.css';

export default function SessionReplay({ attacks, commands, formatDate }) {
  const [selectedReplaySession, setSelectedReplaySession] = useState('');
  const [sessionCommands, setSessionCommands] = useState([]);
  const [currentReplayIndex, setCurrentReplayIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [replaySpeed, setReplaySpeed] = useState(1);
  
  const terminalEndRef = useRef(null);

  // Helper robuste pour parser les dates de SQLite (YYYY-MM-DD HH:MM:SS)
  const parseDate = (dateString) => {
    if (!dateString) return new Date(0);
    let str = dateString;
    if (!str.endsWith('Z') && !str.includes('+') && !str.includes('T')) {
      str = str.replace(' ', 'T') + 'Z';
    }
    return new Date(str);
  };

  // Chargement des commandes de la session
  useEffect(() => {
    if (!selectedReplaySession) {
      setSessionCommands([]);
      setCurrentReplayIndex(0);
      setIsPlaying(false);
      return;
    }

    const targetAttack = attacks.find(a => a.timestamp === selectedReplaySession);
    if (!targetAttack) return;

    const sortedAttacks = [...attacks].sort((a, b) => parseDate(a.timestamp) - parseDate(b.timestamp));
    const startDate = parseDate(targetAttack.timestamp);
    const nextAttack = sortedAttacks.find(
      a => a.ip_address === targetAttack.ip_address && parseDate(a.timestamp) > startDate
    );
    const endDate = nextAttack ? parseDate(nextAttack.timestamp) : new Date();

    const filtered = commands.filter(cmd => {
      const cmdDate = parseDate(cmd.timestamp);
      return cmd.ip_address === targetAttack.ip_address && cmdDate >= startDate && cmdDate < endDate;
    });

    const sortedFilteredCommands = filtered.sort((a, b) => parseDate(a.timestamp) - parseDate(b.timestamp));

    setSessionCommands(sortedFilteredCommands);
  }, [selectedReplaySession, attacks, commands]);

  // Réinitialiser uniquement lorsqu'on choisit une autre session,
  // pas lors du rafraîchissement périodique des données.
  useEffect(() => {
    setIsPlaying(false);
    setCurrentReplayIndex(0);
  }, [selectedReplaySession]);

  // Logique de lecture automatique : s'arrête à la fin sans réinitialiser l'index
  useEffect(() => {
    let interval;
    if (isPlaying) {
      interval = setInterval(() => {
        setCurrentReplayIndex(prev => {
          if (prev < sessionCommands.length) {
            const nextIndex = prev + 1;
            if (nextIndex >= sessionCommands.length) {
              setIsPlaying(false); // On stoppe la lecture
              return sessionCommands.length; // On bloque l'index au maximum pour tout afficher
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

  return (
    <div className="card">
      <div className="card-header-flex replay-header">
        <h3>Lecteur de Rejeu d'Attaque</h3>
        
        <div className="replay-select-container">
          <label style={{ fontSize: '0.9rem', color: '#94a3b8' }}>Choisir une session :</label>
          <select 
            value={selectedReplaySession} 
            onChange={(e) => setSelectedReplaySession(e.target.value)}
            className="replay-select"
          >
            <option value="">-- Sélectionner une session d'attaque --</option>
            {attacks.map((att, idx) => (
              <option key={idx} value={att.timestamp}>
                {formatDate(att.timestamp)} - IP: {att.ip_address} (User: {att.username})
              </option>
            ))}
          </select>
        </div>
      </div>

      {!selectedReplaySession ? (
        <div style={{ textAlign: 'center', padding: '50px', color: '#64748b' }}>
          <p>Veuillez sélectionner une session dans le menu déroulant ci-dessus pour lancer le rejeu du terminal.</p>
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

          {/* Terminal interactif étape par étape */}
          <div className="console replay-terminal">
            <div style={{ color: '#475569', fontSize: '0.80rem', marginBottom: '15px' }}>
              [SYSTEM] Connexion SSH simulée établie avec succès - Début du rejeu de session...
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

          {/* Barre de progression interactive */}
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
  );
}