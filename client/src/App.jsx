import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, NavLink } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import SessionReplay from './pages/SessionReplay';
import './App.css';

function App() {
  const [attacks, setAttacks] = useState([]);
  const [commands, setCommands] = useState([]);
  const [stats, setStats] = useState(null);
  const [isHoneypotActive, setIsHoneypotActive] = useState(false);
  const [selectedSessions, setSelectedSessions] = useState([]);
  const [currentTime, setCurrentTime] = useState(new Date());

  // Mise à jour de l'horloge globale toutes les secondes
  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  // Récupération globale des données depuis l'API Flask
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

  // Formatage de date partagé
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

  // Gestion de la sélection des sessions
  const handleRowClick = (timestamp) => {
    if (timestamp === null) {
      setSelectedSessions([]);
      return;
    }
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

  const allTimestampsCount = attacks.map(att => att.timestamp).filter(Boolean).length;
  const isAllSelected = allTimestampsCount > 0 && selectedSessions.length === allTimestampsCount;

  return (
    <Router>
      <div className="container">
        {/* En-tête global partagé : Titre, Statut, Navigation et Horloge */}
        <div className="top-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '30px', flexWrap: 'wrap', gap: '15px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '15px', flexWrap: 'wrap' }}>
            <h1 style={{ margin: 0 }}>Winnie The Pooh Dashboard</h1>
            
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', backgroundColor: '#1e293b', padding: '6px 12px', borderRadius: '20px', border: '1px solid #334155' }}>
              <span style={{
                width: '10px', height: '10px', borderRadius: '50%',
                backgroundColor: isHoneypotActive ? '#22c55e' : '#ef4444',
                boxShadow: isHoneypotActive ? '0 0 8px #22c55e' : '0 0 8px #ef4444',
                display: 'inline-block'
              }}></span>
              <span style={{ fontSize: '0.8rem', color: '#94a3b8', fontWeight: '500' }}>
                {isHoneypotActive ? 'Actif' : 'Inactif'}
              </span>
            </div>

            {/* Menu de navigation dynamique avec NavLink */}
            <nav style={{ display: 'flex', backgroundColor: '#1e293b', padding: '4px', borderRadius: '8px', border: '1px solid #334155', gap: '5px' }}>
              <NavLink 
                to="/" 
                style={({ isActive }) => ({
                  backgroundColor: isActive ? '#3b82f6' : 'transparent',
                  color: '#fff',
                  textDecoration: 'none',
                  padding: '6px 14px',
                  borderRadius: '6px',
                  fontSize: '0.9rem',
                  fontWeight: 'bold'
                })}
              >
                Tableau de bord
              </NavLink>
              <NavLink 
                to="/replay" 
                style={({ isActive }) => ({
                  backgroundColor: isActive ? '#3b82f6' : 'transparent',
                  color: '#fff',
                  textDecoration: 'none',
                  padding: '6px 14px',
                  borderRadius: '6px',
                  fontSize: '0.9rem',
                  fontWeight: 'bold'
                })}
              >
                Replay de session
              </NavLink>
            </nav>
          </div>

          <div className="live-clock" style={{ backgroundColor: '#1e293b', padding: '10px 18px', borderRadius: '8px', fontFamily: 'monospace', textAlign: 'right', border: '1px solid #334155' }}>
            <div style={{ fontSize: '1.4rem', fontWeight: 'bold', color: '#38bdf8' }}>
              {currentTime.toLocaleTimeString('fr-FR', { timeZone: 'Europe/Paris' })}
            </div>
            <div style={{ fontSize: '0.8rem', color: '#94a3b8', textTransform: 'capitalize' }}>
              {currentTime.toLocaleDateString('fr-FR', { timeZone: 'Europe/Paris', weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
            </div>
          </div>
        </div>

        {/* Routage des différentes vues */}
        <Routes>
          <Route 
            path="/" 
            element={
              <Dashboard 
                attacks={attacks}
                commands={commands}
                stats={stats}
                selectedSessions={selectedSessions}
                handleRowClick={handleRowClick}
                handleToggleSelectAll={handleToggleSelectAll}
                isAllSelected={isAllSelected}
                formatDate={formatDate}
              />
            } 
          />
          <Route 
            path="/replay" 
            element={
              <SessionReplay 
                attacks={attacks}
                commands={commands}
                formatDate={formatDate}
              />
            } 
          />
        </Routes>
      </div>
    </Router>
  );
}

export default App;