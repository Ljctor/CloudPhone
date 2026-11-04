// Shared visual semantics for live debug and the passive navigation review.
// These styles describe feedback; they never change gesture permissions.
export function zoneStyle(zone) {
  const removal = zone.proposal === 'remove' || zone.removedProposal === true;
  const user = zone.user === true || zone.source === 'user_feedback';
  return {
    dash: removal ? '10 7' : user ? '1 5' : 'none',
    opacity: removal ? .28 : 1,
    linecap: user && !removal ? 'round' : 'butt',
    double: Boolean(zone.conditional) && !user && !removal,
    width: zone.conditional && !user && !removal ? 1 : 2,
  };
}
