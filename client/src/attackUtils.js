export function parseDate(dateString) {
  if (!dateString) return new Date(0);
  let str = dateString;
  if (!str.endsWith('Z') && !str.includes('+') && !str.includes('T')) {
    str = str.replace(' ', 'T') + 'Z';
  }
  return new Date(str);
}

export function countAttacksByPort(attacks) {
  return attacks.reduce((counts, attack) => {
    const port = attack.port || 2222;
    counts.set(port, (counts.get(port) || 0) + 1);
    return counts;
  }, new Map());
}

export function getAvailablePorts(activeHoneypots, attacks) {
  return [...new Set([
    ...(activeHoneypots || []).map(honeypot => honeypot.port),
    ...attacks.map(attack => attack.port || 2222)
  ])].sort((a, b) => a - b);
}

export function filterAttacksByPort(attacks, selectedPortFilter) {
  return attacks.filter(attack => (
    selectedPortFilter === 'ALL'
    || (attack.port || 2222) === Number(selectedPortFilter)
  ));
}
