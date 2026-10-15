import React, { useState, useEffect } from 'react';
import { BrowserRouter as Router, Routes, Route, NavLink } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import SessionReplay from './pages/SessionReplay';
import MeshManager from './pages/MeshManager';
import FirewallManager from './pages/FirewallManager';
import './App.css';

function App() {
  const [attacks, setAttacks] = useState([]);
  const [commands, setCommands] = useState([]);
  const [stats, setStats] = useState(null);
  const [activeHoneypots, setActiveHoneypots] = useState([]);
  const [selectedSessions, setSelectedSessions] = useState([]);
  const [currentTime, setCurrentTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const fetchData = async () => {
    try {
      const [resAttacks, resCmds, resStats, resHoneypots] = await Promise.all([
        fetch('http://localhost:5000/api/attacks'),
        fetch('http://localhost:5000/api/commands'),
        fetch('http://localhost:5000/api/stats'),
        fetch('http://localhost:5000/api/honeypots')
      ]);

      if (resAttacks.ok) setAttacks(await resAttacks.json());
      if (resCmds.ok) setCommands(await resCmds.json());
      if (resStats.ok) setStats(await resStats.json());
      if (resHoneypots.ok) {
        const honeypotData = await resHoneypots.json();
        setActiveHoneypots(honeypotData.honeypots);
      }
    } catch (err) {
      console.error("Erreur de connexion API :", err);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(() => {
      fetchData();
    }, 3000);
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

  const handleRowClick = (attackId) => {
    if (attackId === null) {
      setSelectedSessions([]);
      return;
    }
    if (selectedSessions.includes(attackId)) {
      setSelectedSessions(selectedSessions.filter(id => id !== attackId));
    } else {
      setSelectedSessions([...selectedSessions, attackId]);
    }
  };

  const handleToggleSelectAll = (attackIds = attacks.map(att => att.id)) => {
    setSelectedSessions(currentSessions => (
      attackIds.every(id => currentSessions.includes(id))
        ? currentSessions.filter(id => !attackIds.includes(id))
        : [...new Set([...currentSessions, ...attackIds])]
    ));
  };

  const navLinkStyle = ({ isActive }) => ({
    backgroundColor: isActive ? '#3b82f6' : 'transparent',
    color: '#fff',
    textDecoration: 'none',
    padding: '6px 14px',
    borderRadius: '6px',
    fontSize: '0.9rem',
    fontWeight: 'bold'
  });

  return (
    <Router>
      <div className="container">
        <div className="top-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '30px', flexWrap: 'wrap', gap: '15px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '15px', flexWrap: 'wrap' }}>
            <h1 style={{ margin: 0 }}>Winnie The Pooh Dashboard</h1>
            
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', backgroundColor: '#1e293b', padding: '6px 12px', borderRadius: '20px', border: '1px solid #334155' }}>
              <span style={{
                width: '10px', height: '10px', borderRadius: '50%',
                backgroundColor: activeHoneypots.length > 0 ? '#22c55e' : '#ef4444',
                boxShadow: activeHoneypots.length > 0 ? '0 0 8px #22c55e' : '0 0 8px #ef4444',
                display: 'inline-block'
              }}></span>
              <span style={{ fontSize: '0.8rem', color: '#94a3b8', fontWeight: '500' }}>
                {activeHoneypots.length > 0 ? `${activeHoneypots.length} actif(s)` : 'Inactif'}
              </span>
            </div>

            <nav style={{ display: 'flex', backgroundColor: '#1e293b', padding: '4px', borderRadius: '8px', border: '1px solid #334155', gap: '5px' }}>
              <NavLink to="/" style={navLinkStyle}>Tableau de bord</NavLink>
              <NavLink to="/mesh" style={navLinkStyle}>Mesh Armada 🕸️</NavLink>
              <NavLink to="/replay" style={navLinkStyle}>Replay</NavLink>
              <NavLink to="/firewall" style={navLinkStyle}>Pare-feu 🛡️</NavLink>
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

        <Routes>
          <Route 
            path="/" 
            element={
              <Dashboard 
                attacks={attacks}
                commands={commands}
                stats={stats}
                activeHoneypots={activeHoneypots}
                selectedSessions={selectedSessions}
                handleRowClick={handleRowClick}
                handleToggleSelectAll={handleToggleSelectAll}
                formatDate={formatDate}
              />
            } 
          />
          <Route 
            path="/mesh" 
            element={<MeshManager />} 
          />
          <Route 
            path="/replay" 
            element={
              <SessionReplay 
                attacks={attacks}
                commands={commands}
                activeHoneypots={activeHoneypots}
                formatDate={formatDate}
              />
            } 
          />
          <Route 
            path="/firewall" 
            element={<FirewallManager />} 
          />
        </Routes>
      </div>
    </Router>
  );
}

export default App;