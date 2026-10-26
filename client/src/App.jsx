import { useState, useEffect, useRef, useCallback } from 'react';
import { BrowserRouter as Router, Routes, Route, NavLink } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import SessionReplay from './pages/SessionReplay';
import MeshManager from './pages/MeshManager';
import FirewallManager from './pages/FirewallManager';
import AccountManager from './pages/AccountManager';
import Login from './pages/Login';
import { apiFetch } from './api';
import logo from './assets/HoneypotSwarm.png';
import './App.css';

const API_PAGE_SIZE = 500;

async function fetchJson(path, signal) {
  const response = await apiFetch(path, { signal });
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${path}`);
  }
  return response.json();
}

async function fetchAllRecords(endpoint, signal) {
  const records = [];
  let beforeId;

  while (true) {
    const params = new URLSearchParams({ limit: String(API_PAGE_SIZE) });
    if (beforeId !== undefined) params.set('before_id', String(beforeId));
    const page = await fetchJson(`/${endpoint}?${params}`, signal);
    records.push(...page);

    if (page.length < API_PAGE_SIZE) return records;
    const nextBeforeId = Math.min(...page.map(record => record.id));
    if (beforeId !== undefined && nextBeforeId >= beforeId) {
      throw new Error(`Le curseur de pagination de ${endpoint} n'avance pas.`);
    }
    beforeId = nextBeforeId;
  }
}

async function fetchNewRecords(endpoint, afterId, signal) {
  const records = [];
  let cursor = afterId;

  while (true) {
    const params = new URLSearchParams({
      after_id: String(cursor),
      limit: String(API_PAGE_SIZE)
    });
    const page = await fetchJson(`/${endpoint}?${params}`, signal);
    records.push(...page);

    if (page.length < API_PAGE_SIZE) return records.reverse();
    const nextCursor = Math.max(...page.map(record => record.id));
    if (nextCursor <= cursor) {
      throw new Error(`Le curseur de mise à jour de ${endpoint} n'avance pas.`);
    }
    cursor = nextCursor;
  }
}

function applyCountryUpdates(attacks, updates) {
  if (!updates.length) return attacks;
  const countryByAttackId = new Map(
    updates.map(update => [update.attack_id, update.country])
  );
  return attacks.map(attack => (
    countryByAttackId.has(attack.id)
      ? { ...attack, country: countryByAttackId.get(attack.id) }
      : attack
  ));
}

function App() {
  const isPasswordResetFlow = new URLSearchParams(window.location.search).has('token');
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [isCheckingSession, setIsCheckingSession] = useState(!isPasswordResetFlow);

  const [attacks, setAttacks] = useState([]);
  const [commands, setCommands] = useState([]);
  const [stats, setStats] = useState(null);
  const [activeHoneypots, setActiveHoneypots] = useState([]);
  const [selectedSessions, setSelectedSessions] = useState([]);
  const [currentTime, setCurrentTime] = useState(new Date());
  
  const attacksCursor = useRef(0);
  const commandsCursor = useRef(0);
  const countryUpdatesCursor = useRef(0);
  const hasLoadedData = useRef(false);
  const lastStatsFetch = useRef(0);

  const resetSessionData = useCallback(() => {
    hasLoadedData.current = false;
    attacksCursor.current = 0;
    commandsCursor.current = 0;
    countryUpdatesCursor.current = 0;
    lastStatsFetch.current = 0;
    setAttacks([]);
    setCommands([]);
    setStats(null);
    setActiveHoneypots([]);
    setSelectedSessions([]);
  }, []);

  const handleLoginSuccess = () => {
    resetSessionData();
    setIsAuthenticated(true);
  };

  const handleLogout = useCallback(async () => {
    try {
      await apiFetch('/logout', { method: 'POST' });
    } catch (error) {
      console.error('Impossible de terminer la session côté serveur :', error);
    } finally {
      resetSessionData();
      setIsAuthenticated(false);
    }
  }, [resetSessionData]);

  useEffect(() => {
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (isPasswordResetFlow) return undefined;

    let cancelled = false;
    apiFetch('/session')
      .then(response => {
        if (response.status !== 401 && response.status !== 503 && !response.ok) {
          throw new Error(`API ${response.status}: /session`);
        }
        return response.ok;
      })
      .catch(error => {
        console.error('Impossible de vérifier la session :', error);
        return false;
      })
      .then(authenticated => {
        if (!cancelled) {
          setIsAuthenticated(authenticated);
          setIsCheckingSession(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [isPasswordResetFlow]);

  useEffect(() => {
    if (!isAuthenticated) return;

    const controller = new AbortController();
    let timer;
    let cancelled = false;

    const fetchData = async () => {
      try {
        const isInitialLoad = !hasLoadedData.current;
        if (isInitialLoad) {
          const latestCountryUpdate = await fetchJson(
            '/country-updates/latest',
            controller.signal
          );
          countryUpdatesCursor.current = latestCountryUpdate.id;
        }
        const attacksRequest = isInitialLoad
          ? fetchAllRecords('attacks', controller.signal)
          : fetchNewRecords('attacks', attacksCursor.current, controller.signal);
        const commandsRequest = isInitialLoad
          ? fetchAllRecords('commands', controller.signal)
          : fetchNewRecords('commands', commandsCursor.current, controller.signal);
        const countryUpdatesRequest = fetchNewRecords(
          'country-updates',
          countryUpdatesCursor.current,
          controller.signal
        );
        const shouldRefreshStats = isInitialLoad || Date.now() - lastStatsFetch.current >= 15000;
        const [newAttacks, newCommands, countryUpdates, newStats, honeypotData] = await Promise.all([
          attacksRequest,
          commandsRequest,
          countryUpdatesRequest,
          shouldRefreshStats
            ? fetchJson('/stats', controller.signal)
            : Promise.resolve(null),
          fetchJson('/honeypots', controller.signal)
        ]);

        if (cancelled) return;

        if (isInitialLoad) {
          setAttacks(applyCountryUpdates(newAttacks, countryUpdates));
          setCommands(newCommands);
          hasLoadedData.current = true;
        } else {
          if (newAttacks.length || countryUpdates.length) {
            setAttacks(current => applyCountryUpdates(
              [...newAttacks, ...current],
              countryUpdates
            ));
          }
          if (newCommands.length) setCommands(current => [...newCommands, ...current]);
        }

        attacksCursor.current = newAttacks.reduce(
          (maxId, attack) => Math.max(maxId, attack.id),
          attacksCursor.current
        );
        commandsCursor.current = newCommands.reduce(
          (maxId, command) => Math.max(maxId, command.id),
          commandsCursor.current
        );
        countryUpdatesCursor.current = countryUpdates.reduce(
          (maxId, update) => Math.max(maxId, update.id),
          countryUpdatesCursor.current
        );
        if (newStats) {
          setStats(newStats);
          lastStatsFetch.current = Date.now();
        }
        setActiveHoneypots(honeypotData.honeypots);
      } catch (err) {
        if (!cancelled && err.name !== 'AbortError') {
          console.error("Erreur de connexion API :", err);
          if (err.message.includes('API 401:')) {
            handleLogout();
          }
        }
      } finally {
        if (!cancelled) timer = setTimeout(fetchData, 5000);
      }
    };

    fetchData();
    return () => {
      cancelled = true;
      controller.abort();
      clearTimeout(timer);
    };
  }, [isAuthenticated, handleLogout]);

  if (isCheckingSession) return null;

  if (!isAuthenticated) {
    return (
      <Router>
        <Routes>
          <Route path="*" element={<Login onLoginSuccess={handleLoginSuccess} />} />
        </Routes>
      </Router>
    );
  }

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
      setSelectedSessions(current => current.filter(id => id !== attackId));
    } else {
      setSelectedSessions(current => [...current, attackId]);
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
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <img 
                src={logo} 
                alt="Honeypot Swarm Logo" 
                style={{ width: '32px', height: '32px', objectFit: 'contain' }} 
              />
              <h1 style={{ margin: 0, fontSize: '1.8rem', color: '#f8fafc', fontWeight: 'bold' }}>
                Honeypot Swarm Dashboard
              </h1>
            </div>
            
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
              <NavLink to="/mesh" style={navLinkStyle}>Swarm Controller</NavLink>
              <NavLink to="/replay" style={navLinkStyle}>Replay</NavLink>
              <NavLink to="/firewall" style={navLinkStyle}>Pare-feu 🛡️</NavLink>
              <NavLink to="/account" style={navLinkStyle}>Compte</NavLink>
            </nav>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
            <div className="live-clock" style={{ backgroundColor: '#1e293b', padding: '10px 18px', borderRadius: '8px', fontFamily: 'monospace', textAlign: 'right', border: '1px solid #334155' }}>
              <div style={{ fontSize: '1.4rem', fontWeight: 'bold', color: '#38bdf8' }}>
                {currentTime.toLocaleTimeString('fr-FR', { timeZone: 'Europe/Paris' })}
              </div>
              <div style={{ fontSize: '0.8rem', color: '#94a3b8', textTransform: 'capitalize' }}>
                {currentTime.toLocaleDateString('fr-FR', { timeZone: 'Europe/Paris', weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' })}
              </div>
            </div>

            <button
              onClick={handleLogout}
              title="Se déconnecter"
              style={{
                backgroundColor: '#ef4444',
                color: '#fff',
                border: 'none',
                padding: '10px 14px',
                borderRadius: '8px',
                fontWeight: 'bold',
                cursor: 'pointer',
                fontSize: '0.85rem'
              }}
            >
              Déconnexion
            </button>
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
          <Route
            path="/account"
            element={<AccountManager />}
          />
        </Routes>
      </div>
    </Router>
  );
}

export default App;