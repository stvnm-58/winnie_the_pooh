import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '../api';
import './MeshManager.css';

// Écran Mesh : déploie des écouteurs, les regroupe en essaims et gère leurs ports/arrêts.
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

  // Récupère la liste des honeypots actifs affichés dans les cartes.
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

  // Actualise périodiquement les honeypots et nettoie les minuteries au démontage.
  useEffect(() => {
    const initialFetch = setTimeout(fetchHoneypots, 0);
    const interval = setInterval(fetchHoneypots, 4000);
    return () => {
      clearTimeout(initialFetch);
      clearInterval(interval);
    };
  }, []);

  // Valide le port saisi et déploie un honeypot dessus.
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

  // Valide la plage demandée et déploie un groupe de honeypots aléatoires.
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

  // Déploie plusieurs honeypots sur des ports disponibles autour du port de référence.
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

  // Demande confirmation avant d'arrêter le honeypot du port choisi.
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

  // Change le port ; pour un honeypot secondaire, démarre le remplaçant avant l'arrêt.
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

  // Mémorise le port choisi avant de revenir au tableau de bord.
  const handleOpenDashboard = (port) => {
    localStorage.setItem('winnie_last_honeypot', String(port));
    navigate('/');
  };

  return (
    <div className="card">
      <div className="card-header-flex">
        <h3 className="mesh-main-title">Swarm</h3>
      </div>
      <p className="muted mesh-intro">
        Déployez et pilotez vos faux serveurs SSH sur différents ports pour noyer les attaquants dans un essaim de pièges.
      </p>

      {/* En haut : déploiement d'une instance sur un port explicite. */}
      <form onSubmit={handleDeploy} className="mesh-form-row">
        <input 
          type="number" 
          min="1"
          max="65535"
          step="1"
          required
          placeholder="Ex: 2223" 
          value={portInput} 
          onChange={(e) => setPortInput(e.target.value)}
          className="mesh-input"
        />
        <button 
          type="submit" 
          disabled={loading}
          className="mesh-btn-primary"
        >
          {loading ? 'Déploiement...' : 'Déployer un nouveau honeypot'}
        </button>
        {errorMsg && <span className="mesh-error-msg">{errorMsg}</span>}
      </form>

      {/* Essaim aléatoire : nombre d'instances et plage de ports à utiliser. */}
      <form onSubmit={handleDeploySwarm} className="mesh-panel">
        <span className="mesh-panel-title-green">Essaim aléatoire :</span>
        <div className="mesh-field-group">
          <label className="mesh-label">Nombre de Honeypots (max 10) :</label>
          <input 
            type="number" 
            min="1" max="10"
            value={swarmCount} 
            onChange={(e) => setSwarmCount(e.target.value)}
            className="mesh-input-small"
          />
        </div>
        <div className="mesh-field-group">
          <label className="mesh-label">Port de départ :</label>
          <input 
            type="number" 
            min="1" max="65535"
            value={swarmMin} 
            onChange={(e) => setSwarmMin(e.target.value)}
            className="mesh-input-medium"
          />
        </div>
        <div className="mesh-field-group">
          <label className="mesh-label">Port de fin :</label>
          <input 
            type="number" 
            min="1" max="65535"
            value={swarmMax} 
            onChange={(e) => setSwarmMax(e.target.value)}
            className="mesh-input-medium"
          />
        </div>
        <button 
          type="submit" 
          disabled={swarmLoading}
          className="mesh-btn-green"
        >
          {swarmLoading ? 'Génération...' : 'Générer'}
        </button>
        {swarmErrorMsg && <span className="mesh-error-msg full-width">{swarmErrorMsg}</span>}
      </form>

      {/* Essaim de leurres autour d'un port de service de référence. */}
      <form onSubmit={handleDeployReference} className="mesh-panel">
        <span className="mesh-panel-title-purple">Essaim autour d'un service :</span>
        <div className="mesh-field-group">
          <label className="mesh-label">Nombre de Honeypots (max 10) :</label>
          <input 
            type="number" 
            min="1" max="10"
            value={refCount} 
            onChange={(e) => setRefCount(e.target.value)}
            className="mesh-input-small"
          />
        </div>
        <div className="mesh-field-group">
          <label className="mesh-label">Port de référence :</label>
          <input 
            type="number" 
            min="1" max="65535"
            value={refPort} 
            onChange={(e) => setRefPort(e.target.value)}
            className="mesh-input-medium"
          />
        </div>
        <button 
          type="submit" 
          disabled={refLoading}
          className="mesh-btn-purple"
        >
          {refLoading ? 'Génération...' : 'Générer'}
        </button>
        {refErrorMsg && <span className="mesh-error-msg full-width">{refErrorMsg}</span>}
      </form>

      {/* Zone inférieure : cartes des processus actifs, ouverture du dashboard, arrêt et édition du port. */}
      <h4>Instances de Honeypots Actives ({honeypots.length})</h4>
      <div className="mesh-grid">
        {honeypots.length === 0 ? (
          <p className="muted">Aucun honeypot actif pour le moment.</p>
        ) : (
          honeypots.map((h) => (
            <div key={h.pid} className="mesh-honeypot-card">
              
              <div className="mesh-card-top">
                <div 
                  onClick={() => handleOpenDashboard(h.port)}
                  className="mesh-card-clickable"
                  title="Cliquer pour ouvrir le dashboard sur ce port"
                >
                  <div className="mesh-port-title">Port : {h.port}</div>
                  <div className="muted mesh-pid">PID Processus : {h.pid}</div>
                  <div className="mesh-open-link">Ouvrir le dashboard →</div>
                </div>

                <button 
                  onClick={() => handleStop(h.port)}
                  className="mesh-btn-stop"
                >
                  Stopper ✕
                </button>
              </div>

              {/* Section pour changer le port à la volée dans la carte */}
              <div className="mesh-edit-section">
                {editingPort === h.port ? (
                  <div className="mesh-edit-row">
                    <input 
                      type="number"
                      min="1"
                      max="65535"
                      value={newPortInput}
                      onChange={(e) => setNewPortInput(e.target.value)}
                      placeholder="Nouveau port"
                      className="mesh-edit-input"
                    />
                    <button 
                      onClick={() => handleUpdatePort(h.port)}
                      className="mesh-btn-validate"
                    >
                      Valider
                    </button>
                    <button 
                      onClick={() => setEditingPort(null)}
                      className="mesh-btn-cancel"
                    >
                      ✕
                    </button>
                  </div>
                ) : (
                  <button 
                    onClick={() => { setEditingPort(h.port); setNewPortInput(String(h.port)); setEditError(''); }}
                    className="mesh-edit-trigger"
                  >
                    Modifier le port à la volée ⚙️
                  </button>
                )}
                {editingPort === h.port && editError && (
                  <div className="mesh-edit-error">{editError}</div>
                )}
              </div>

            </div>
          ))
        )}
      </div>
    </div>
  );
}