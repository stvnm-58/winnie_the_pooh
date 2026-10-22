import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../api';

export default function MeshManager() {
  const [honeypots, setHoneypots] = useState([]);
  const [portInput, setPortInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  // États pour le déploiement en essaim (Swarm aléatoire) - Limité à 10 max
  const [swarmCount, setSwarmCount] = useState('3');
  const [swarmMin, setSwarmMin] = useState('3000');
  const [swarmMax, setSwarmMax] = useState('3010');
  const [swarmLoading, setSwarmLoading] = useState(false);
  const [swarmErrorMsg, setSwarmErrorMsg] = useState('');

  // États pour le déploiement basé sur un port de référence - Limité à 10 max
  const [refCount, setRefCount] = useState('3');
  const [refPort, setRefPort] = useState('3306');
  const [refLoading, setRefLoading] = useState(false);
  const [refErrorMsg, setRefErrorMsg] = useState('');
  
  // États pour gérer l'édition du port par carte (clé = ancien port)
  const [editingPort, setEditingPort] = useState(null);
  const [newPortInput, setNewPortInput] = useState('');
  const [editError, setEditError] = useState('');

  const navigate = useNavigate();

  const fetchHoneypots = async () => {
    try {
      const res = await apiFetch('/honeypots');
      if (res.ok) {
        const data = await res.json();
        setHoneypots(data.honeypots);
      }
    } catch (err) {
      console.error("Erreur lors de la récupération du mesh :", err);
    }
  };

  useEffect(() => {
    const initialFetch = setTimeout(fetchHoneypots, 0);
    const interval = setInterval(fetchHoneypots, 4000);
    return () => {
      clearTimeout(initialFetch);
      clearInterval(interval);
    };
  }, []);

  const handleDeploy = async (e) => {
    e.preventDefault();
    const portNum = Number(portInput);
    if (!Number.isInteger(portNum) || portNum < 1 || portNum > 65535) {
      setErrorMsg('Veuillez saisir un port valide entre 1 et 65535.');
      return;
    }

    setLoading(true);
    setErrorMsg('');
    try {
      const res = await apiFetch('/honeypots', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ port: portNum })
      });
      const data = await res.json();
      if (res.ok) {
        setPortInput('');
        await fetchHoneypots();
      } else {
        setErrorMsg(data.error || 'Erreur lors du déploiement.');
      }
    } catch {
      setErrorMsg("Impossible de joindre l'API Flask.");
    } finally {
      setLoading(false);
    }
  };

  const handleDeploySwarm = async (e) => {
    e.preventDefault();
    const count = Number(swarmCount);
    const port_min = Number(swarmMin);
    const port_max = Number(swarmMax);

    if (!Number.isInteger(count) || count < 1 || count > 10) {
      setSwarmErrorMsg('Le nombre de honeypots doit être entre 1 et 10.');
      return;
    }
    if (!Number.isInteger(port_min) || !Number.isInteger(port_max) || port_min > port_max || port_min < 1 || port_max > 65535) {
      setSwarmErrorMsg('Plage de ports invalide (1-65535).');
      return;
    }

    setSwarmLoading(true);
    setSwarmErrorMsg('');
    try {
      const res = await apiFetch('/honeypots/swarm', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ count, port_min, port_max })
      });
      const data = await res.json();
      if (res.ok) {
        await fetchHoneypots();
      } else {
        setSwarmErrorMsg(data.error || 'Erreur lors du déploiement en essaim.');
      }
    } catch {
      setSwarmErrorMsg("Impossible de joindre l'API Flask.");
    } finally {
      setSwarmLoading(false);
    }
  };

  const handleDeployReference = async (e) => {
    e.preventDefault();
    const count = Number(refCount);
    const reference_port = Number(refPort);

    if (!Number.isInteger(count) || count < 1 || count > 10) {
      setRefErrorMsg('Le nombre de honeypots doit être entre 1 et 10.');
      return;
    }
    if (!Number.isInteger(reference_port) || reference_port < 1 || reference_port > 65535) {
      setRefErrorMsg('Port de service invalide (1-65535).');
      return;
    }

    setRefLoading(true);
    setRefErrorMsg('');
    try {
      const res = await apiFetch('/honeypots/swarm-reference', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ count, reference_port })
      });
      const data = await res.json();
      if (res.ok) {
        await fetchHoneypots();
      } else {
        setRefErrorMsg(data.error || 'Erreur lors du déploiement autour du service.');
      }
    } catch {
      setRefErrorMsg("Impossible de joindre l'API Flask.");
    } finally {
      setRefLoading(false);
    }
  };

  const handleStop = async (port) => {
    if (!window.confirm(`Voulez-vous vraiment stopper le faux SSH sur le port ${port} ?`)) return;

    try {
      const res = await apiFetch(`/honeypots/${port}`, {
        method: 'DELETE'
      });
      if (res.ok) {
        fetchHoneypots();
      } else {
        const data = await res.json();
        alert(data.error || "Erreur lors de l'arrêt.");
      }
    } catch {
      alert("Erreur réseau.");
    }
  };

  const handleUpdatePort = async (oldPort) => {
    const targetPort = Number(newPortInput);
    if (!Number.isInteger(targetPort) || targetPort < 1 || targetPort > 65535) {
      setEditError('Port invalide (1-65535).');
      return;
    }

    if (targetPort === oldPort) {
      setEditingPort(null);
      return;
    }

    setEditError('');
    try {
      const portRes = await apiFetch('/port');
      const portData = await portRes.json();
      if (!portRes.ok) {
        setEditError(portData.error || "Impossible de vérifier le port principal.");
        return;
      }

      if (portData.port === oldPort) {
        const updateRes = await apiFetch('/port', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ port: targetPort })
        });
        const updateData = await updateRes.json();
        if (!updateRes.ok) {
          setEditError(updateData.error || "Erreur lors du changement du port principal.");
          return;
        }

        setEditingPort(null);
        setNewPortInput('');
        await fetchHoneypots();
        return;
      }

      const startRes = await apiFetch('/honeypots', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ port: targetPort })
      });
      const startData = await startRes.json();
      if (!startRes.ok) {
        const errData = startData;
        setEditError(errData.error || "Erreur lors du déploiement sur le nouveau port.");
        return;
      }

      const stopRes = await apiFetch(`/honeypots/${oldPort}`, {
        method: 'DELETE'
      });
      if (!stopRes.ok) {
        const stopData = await stopRes.json();
        let rollbackMessage;
        try {
          const rollbackRes = await apiFetch(`/honeypots/${targetPort}`, {
            method: 'DELETE'
          });
          const rollbackData = rollbackRes.ok ? null : await rollbackRes.json();
          rollbackMessage = rollbackData
            ? `Le nouveau honeypot reste actif sur le port ${targetPort} : ${
                rollbackData.error || 'impossible de l’arrêter.'
              }`
            : 'Le nouveau honeypot a été arrêté.';
        } catch {
          rollbackMessage = `Impossible de confirmer l’arrêt du nouveau honeypot sur le port ${targetPort}.`;
        }
        setEditError(
          `${stopData.error || "Erreur lors de l'arrêt de l'ancien port."} ${rollbackMessage}`
        );
        await fetchHoneypots();
        return;
      }

      setEditingPort(null);
      setNewPortInput('');
      await fetchHoneypots();
    } catch {
      setEditError("Erreur réseau lors du changement de port.");
    }
  };

  const handleOpenDashboard = (port) => {
    localStorage.setItem('winnie_last_honeypot', String(port));
    navigate('/');
  };

  return (
    <div className="card">
      <div className="card-header-flex">
        <h3 style={{ fontSize: '1.8rem', color: '#f8fafc', margin: 0 }}>Swarm</h3>
      </div>
      <p className="muted" style={{ marginBottom: '20px' }}>
        Déployez et pilotez vos faux serveurs SSH sur différents ports pour noyer les attaquants dans un essaim de pièges.
      </p>

      {/* Déploiement unitaire */}
      <form onSubmit={handleDeploy} style={{ display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '15px', flexWrap: 'wrap' }}>
        <input 
          type="number" 
          min="1"
          max="65535"
          step="1"
          required
          placeholder="Ex: 2223" 
          value={portInput} 
          onChange={(e) => setPortInput(e.target.value)}
          style={{ backgroundColor: '#0f172a', border: '1px solid #334155', color: '#fff', padding: '8px 12px', borderRadius: '6px', width: '150px' }}
        />
        <button 
          type="submit" 
          disabled={loading}
          style={{ backgroundColor: '#3b82f6', color: '#fff', border: 'none', padding: '8px 16px', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold' }}
        >
          {loading ? 'Déploiement...' : 'Déployer un nouveau honeypot'}
        </button>
        {errorMsg && <span style={{ color: '#fca5a5', fontSize: '0.85rem' }}>{errorMsg}</span>}
      </form>

      {/* Déploiement en essaim (Swarm aléatoire) */}
      <form onSubmit={handleDeploySwarm} style={{ display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '15px', flexWrap: 'wrap', backgroundColor: '#1e293b', padding: '12px', borderRadius: '8px', border: '1px solid #334155' }}>
        <span style={{ fontSize: '0.9rem', color: '#38bdf8', fontWeight: 'bold' }}>Essaim aléatoire :</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <label style={{ fontSize: '0.8rem', color: '#94a3b8' }}>Nombre de Honeypots (max 10) :</label>
          <input 
            type="number" 
            min="1" max="10"
            value={swarmCount} 
            onChange={(e) => setSwarmCount(e.target.value)}
            style={{ backgroundColor: '#0f172a', border: '1px solid #334155', color: '#fff', padding: '6px 8px', borderRadius: '6px', width: '70px' }}
          />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <label style={{ fontSize: '0.8rem', color: '#94a3b8' }}>Port de départ :</label>
          <input 
            type="number" 
            min="1" max="65535"
            value={swarmMin} 
            onChange={(e) => setSwarmMin(e.target.value)}
            style={{ backgroundColor: '#0f172a', border: '1px solid #334155', color: '#fff', padding: '6px 8px', borderRadius: '6px', width: '90px' }}
          />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <label style={{ fontSize: '0.8rem', color: '#94a3b8' }}>Port de fin :</label>
          <input 
            type="number" 
            min="1" max="65535"
            value={swarmMax} 
            onChange={(e) => setSwarmMax(e.target.value)}
            style={{ backgroundColor: '#0f172a', border: '1px solid #334155', color: '#fff', padding: '6px 8px', borderRadius: '6px', width: '90px' }}
          />
        </div>
        <button 
          type="submit" 
          disabled={swarmLoading}
          style={{ backgroundColor: '#10b981', color: '#fff', border: 'none', padding: '8px 16px', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold' }}
        >
          {swarmLoading ? 'Génération...' : 'Générer'}
        </button>
        {swarmErrorMsg && <span style={{ color: '#fca5a5', fontSize: '0.85rem', width: '100%' }}>{swarmErrorMsg}</span>}
      </form>

      {/* Déploiement autour d'un port de référence */}
      <form onSubmit={handleDeployReference} style={{ display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '25px', flexWrap: 'wrap', backgroundColor: '#1e293b', padding: '12px', borderRadius: '8px', border: '1px solid #334155' }}>
        <span style={{ fontSize: '0.9rem', color: '#a855f7', fontWeight: 'bold' }}>Essaim autour d'un service :</span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <label style={{ fontSize: '0.8rem', color: '#94a3b8' }}>Nombre de Honeypots (max 10) :</label>
          <input 
            type="number" 
            min="1" max="10"
            value={refCount} 
            onChange={(e) => setRefCount(e.target.value)}
            style={{ backgroundColor: '#0f172a', border: '1px solid #334155', color: '#fff', padding: '6px 8px', borderRadius: '6px', width: '70px' }}
          />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <label style={{ fontSize: '0.8rem', color: '#94a3b8' }}>Port de référence :</label>
          <input 
            type="number" 
            min="1" max="65535"
            value={refPort} 
            onChange={(e) => setRefPort(e.target.value)}
            style={{ backgroundColor: '#0f172a', border: '1px solid #334155', color: '#fff', padding: '6px 8px', borderRadius: '6px', width: '90px' }}
          />
        </div>
        <button 
          type="submit" 
          disabled={refLoading}
          style={{ backgroundColor: '#8b5cf6', color: '#fff', border: 'none', padding: '8px 16px', borderRadius: '6px', cursor: 'pointer', fontWeight: 'bold' }}
        >
          {refLoading ? 'Génération...' : 'Générer'}
        </button>
        {refErrorMsg && <span style={{ color: '#fca5a5', fontSize: '0.85rem', width: '100%' }}>{refErrorMsg}</span>}
      </form>

      <h4>Instances de Honeypots Actives ({honeypots.length})</h4>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '15px', marginTop: '15px' }}>
        {honeypots.length === 0 ? (
          <p className="muted">Aucun honeypot actif pour le moment.</p>
        ) : (
          honeypots.map((h) => (
            <div key={h.pid} style={{ backgroundColor: '#0f172a', border: '1px solid #334155', borderRadius: '8px', padding: '15px', display: 'flex', flexDirection: 'column', gap: '12px' }}>
              
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                <div 
                  onClick={() => handleOpenDashboard(h.port)}
                  style={{ cursor: 'pointer', flex: 1 }}
                  title="Cliquer pour ouvrir le dashboard sur ce port"
                >
                  <div style={{ fontSize: '1.1rem', fontWeight: 'bold', color: '#38bdf8' }}>Port : {h.port}</div>
                  <div className="muted" style={{ fontSize: '0.8rem' }}>PID Processus : {h.pid}</div>
                  <div style={{ color: '#94a3b8', fontSize: '0.8rem', marginTop: '6px' }}>Ouvrir le dashboard →</div>
                </div>

                <button 
                  onClick={() => handleStop(h.port)}
                  style={{ backgroundColor: '#ef4444', color: '#fff', border: 'none', padding: '6px 10px', borderRadius: '6px', cursor: 'pointer', fontSize: '0.8rem', fontWeight: 'bold' }}
                >
                  Stopper ✕
                </button>
              </div>

              {/* Section pour changer le port à la volée dans la carte */}
              <div style={{ borderTop: '1px solid #1e293b', paddingTop: '10px' }}>
                {editingPort === h.port ? (
                  <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                    <input 
                      type="number"
                      min="1"
                      max="65535"
                      value={newPortInput}
                      onChange={(e) => setNewPortInput(e.target.value)}
                      placeholder="Nouveau port"
                      style={{ backgroundColor: '#1e293b', border: '1px solid #334155', color: '#fff', padding: '4px 8px', borderRadius: '4px', width: '100px', fontSize: '0.85rem' }}
                    />
                    <button 
                      onClick={() => handleUpdatePort(h.port)}
                      style={{ backgroundColor: '#22c55e', color: '#fff', border: 'none', padding: '5px 8px', borderRadius: '4px', cursor: 'pointer', fontSize: '0.8rem', fontWeight: 'bold' }}
                    >
                      Valider
                    </button>
                    <button 
                      onClick={() => setEditingPort(null)}
                      style={{ backgroundColor: '#64748b', color: '#fff', border: 'none', padding: '5px 8px', borderRadius: '4px', cursor: 'pointer', fontSize: '0.8rem' }}
                    >
                      ✕
                    </button>
                  </div>
                ) : (
                  <button 
                    onClick={() => { setEditingPort(h.port); setNewPortInput(String(h.port)); setEditError(''); }}
                    style={{ background: 'transparent', border: 'none', color: '#38bdf8', padding: 0, fontSize: '0.8rem', cursor: 'pointer', textDecoration: 'underline' }}
                  >
                    Modifier le port à la volée ⚙️
                  </button>
                )}
                {editingPort === h.port && editError && (
                  <div style={{ color: '#fca5a5', fontSize: '0.75rem', marginTop: '4px' }}>{editError}</div>
                )}
              </div>

            </div>
          ))
        )}
      </div>
    </div>
  );
}