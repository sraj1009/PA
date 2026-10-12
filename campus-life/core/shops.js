// Pure shop filtering/sorting. Distances come in as numbers so the caller decides
// whether they came from GPS or from the seeded sample data.

function toRad(deg) {
  return (deg * Math.PI) / 180;
}

/** Great-circle km between {lat,lng} points. */
function haversineKm(a, b) {
  const R = 6371;
  const dLat = toRad(b.lat - a.lat);
  const dLng = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const h =
    Math.sin(dLat / 2) * Math.sin(dLat / 2) +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)));
}

function isOpen(shop, at) {
  const range = shop.open;
  if (!range || range.length < 2) return true;
  const start = range[0];
  const end = range[1];
  if (start <= end) return at >= start && at < end;
  return at >= start || at < end;
}

/** Conjunctive: a shop must satisfy every criterion that was actually set. */
function filter(list, opts) {
  const o = opts || {};
  const q = (o.q || '').trim().toLowerCase();
  const cats = o.cats || [];
  const at = o.at == null ? new Date().getHours() : o.at;

  return (list || []).filter((shop) => {
    if (q) {
      // catText is the human-readable category label the caller attaches, so a
      // student can type 咖啡 and hit a shop tagged coffee.
      const hay = (shop.name + ' ' + (shop.cats || []).join(' ') + ' ' + (shop.catText || '') + ' ' + (shop.desc || '')).toLowerCase();
      if (hay.indexOf(q) < 0) return false;
    }
    if (cats.length && !cats.some((c) => (shop.cats || []).indexOf(c) >= 0)) return false;
    if (o.openNow && !isOpen(shop, at)) return false;
    if (o.maxDist != null && shop.dist > o.maxDist) return false;
    return true;
  });
}

const COMPARATORS = {
  distance: (a, b) => a.dist - b.dist,
  rating: (a, b) => b.rating - a.rating,
  price: (a, b) => a.price - b.price,
};

/** Returns a new array; the caller's list is never reordered. */
function sortBy(list, key) {
  const cmp = COMPARATORS[key];
  if (!cmp) return (list || []).slice();
  return (list || []).slice().sort(cmp);
}

function toggleFav(favs, id) {
  const current = favs || [];
  return current.indexOf(id) >= 0 ? current.filter((x) => x !== id) : current.concat([id]);
}

module.exports = { filter, sortBy, haversineKm, toggleFav, isOpen };
