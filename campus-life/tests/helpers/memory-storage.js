// Storage double with the same shape the app's adapter produces, so store
// tests and page tests share one contract.
function memoryStorage(initial) {
  const data = new Map(Object.entries(initial || {}));
  return {
    get: (k) => (data.has(k) ? data.get(k) : ''),
    set: (k, v) => { data.set(k, JSON.parse(JSON.stringify(v))); },
    remove: (k) => { data.delete(k); },
    dump: () => Object.fromEntries(data),
  };
}

module.exports = { memoryStorage };
