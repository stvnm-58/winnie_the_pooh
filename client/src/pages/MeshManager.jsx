import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

export default function MeshManager() {
  const [honeypots, setHoneypots] = useState([]);
  const [portInput, setPortInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  
  // États pour gérer l'édition du port par carte (clé = ancien port)
  const [editingPort, setEditingPort] = useState(null);
  const [newPortInput, setNewPortInput] = useState('');
  const [editError, setEditError] = useState('');

  const navigate = useNavigate();

  const fetchHoneypots = async () => {
    try {
      const res = await fetch('http://localhost:5000/api/honeypots');
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
      const res = await fetch('http://localhost:5000/api/honeypots', {
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

  const handleStop = async (port) => {
    if (!window.confirm(`Voulez-vous vraiment stopper le faux SSH sur le port ${port} ?`)) return;

    try {
      const res = await fetch(`http://localhost:5000/api/honeypots/${port}`, {
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

  // Logique pour modifier le port d'un honeypot actif à la volée
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
      const portRes = await fetch('http://localhost:5000/api/port');
      const portData = await portRes.json();
      if (!portRes.ok) {
        setEditError(portData.error || "Impossible de vérifier le port principal.");
        return;
      }

      if (portData.port === oldPort) {
        const updateRes = await fetch('http://localhost:5000/api/port', {
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

      const startRes = await fetch('http://localhost:5000/api/honeypots', {
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

      const stopRes = await fetch(`http://localhost:5000/api/honeypots/${oldPort}`, {
        method: 'DELETE'
      });
      if (!stopRes.ok) {
        const stopData = await stopRes.json();
        let rollbackMessage;
        try {
          const rollbackRes = await fetch(`http://localhost:5000/api/honeypots/${targetPort}`, {
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
        <h3>🕸️ Gestion de l'Armada (Deception Mesh)</h3>
      </div>
      <p className="muted" style={{ marginBottom: '20px' }}>
        Déployez et pilotez vos faux serveurs SSH sur différents ports pour noyer les attaquants dans une matrice de pièges.
      </p>

      <form onSubmit={handleDeploy} style={{ display: 'flex', gap: '10px', alignItems: 'center', marginBottom: '25px', flexWrap: 'wrap' }}>
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
          {loading ? 'Déploiement...' : 'Déployer un nouveau faux SSH 🚀'}
        </button>
        {errorMsg && <span style={{ color: '#fca5a5', fontSize: '0.85rem' }}>{errorMsg}</span>}
      </form>

      <h4>Instances de Honeypots Actives ({honeypots.length})</h4>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '15px', marginTop: '15px' }}>
        {honeypots.length === 0 ? (
          <p className="muted">Aucun honeypot secondaire actif pour le moment.</p>
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