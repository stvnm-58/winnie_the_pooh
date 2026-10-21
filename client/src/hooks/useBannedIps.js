import { useCallback, useEffect, useState } from 'react';
import { apiFetch } from '../api';

export default function useBannedIps() {
  const [bannedIps, setBannedIps] = useState([]);

  const refreshBannedIps = useCallback(async () => {
    try {
      const response = await apiFetch('/banned-ips');
      if (response.ok) {
        const data = await response.json();
        setBannedIps(data.ips || []);
      }
    } catch (error) {
      console.error('Erreur lors de la récupération des IP bannies :', error);
    }
  }, []);

  useEffect(() => {
    const initialFetch = setTimeout(refreshBannedIps, 0);
    const interval = setInterval(refreshBannedIps, 5000);
    return () => {
      clearTimeout(initialFetch);
      clearInterval(interval);
    };
  }, [refreshBannedIps]);

  return { bannedIps, refreshBannedIps };
}
