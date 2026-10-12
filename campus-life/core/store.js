const { KEY, migrate, schema } = require('./schema');

class QuotaError extends Error {
  constructor(message) {
    super(message || '本地存储空间已满');
    this.name = 'QuotaError';
  }
}

const clone = (v) => JSON.parse(JSON.stringify(v));

// Keep the newest messages of every chat session.
function pruneChatMessages(state) {
  const next = clone(state);
  next.chats = next.chats.map((c) => {
    const msgs = c.messages || [];
    return msgs.length > 20 ? Object.assign({}, c, { messages: msgs.slice(-20) }) : c;
  });
  return next;
}

// Drop the oldest already-closed tree-hole posts.
function dropClosedPosts(state) {
  const next = clone(state);
  const open = next.posts.filter((p) => !p.closed);
  const closed = next.posts.filter((p) => p.closed).sort((a, b) => (b.ts || 0) - (a.ts || 0));
  next.posts = open.concat(closed.slice(0, Math.max(0, closed.length - 1)));
  return next;
}

/**
 * The only module that talks to storage. `storage` is shaped like
 * { get(key), set(key, value), remove(key) } — wx adapter in the app,
 * memoryStorage() in tests.
 */
function createStore(storage, options) {
  const key = (options && options.key) || KEY;
  let cache = null;

  function load() {
    let raw;
    try {
      raw = storage.get(key);
    } catch (e) {
      raw = null;
    }
    cache = migrate(raw);
    return cache;
  }

  function read() {
    return clone(cache === null ? load() : cache);
  }

  function persist(next) {
    const attempts = [next, pruneChatMessages(next)];
    attempts.push(dropClosedPosts(attempts[1]));
    let saved = null;
    for (let i = 0; i < attempts.length; i += 1) {
      try {
        storage.set(key, attempts[i]);
        saved = attempts[i];
        break;
      } catch (e) {
        if (i === attempts.length - 1) throw new QuotaError();
      }
    }
    cache = saved;
    return clone(saved);
  }

  function write(mutator) {
    const next = read();
    mutator(next);
    next.updatedAt = Date.now();
    return persist(next);
  }

  function reset() {
    cache = schema();
    return persist(clone(cache));
  }

  return { read, write, reset, raw: () => cache, key };
}

module.exports = { createStore, QuotaError, pruneChatMessages, dropClosedPosts };
