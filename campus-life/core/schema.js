const KEY = 'cl:v1';
const VERSION = 1;

function schema() {
  return {
    version: VERSION,
    updatedAt: 0,
    profile: { nickname: '', interests: [] },
    settings: { agentMode: 'auto' },
    moods: [],
    posts: [],
    chats: [],
    checkins: [],
    tasks: [],
    plans: [],
    favourites: { shops: [], groups: [] },
  };
}

// Accepts anything read from storage and returns a complete, valid state.
// A mini program must never white-screen because a key was half-written.
function migrate(raw) {
  const base = schema();
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return base;
  const out = Object.assign({}, base, raw);
  out.version = VERSION;
  out.profile = Object.assign({}, base.profile, raw.profile);
  out.settings = Object.assign({}, base.settings, raw.settings);
  out.favourites = Object.assign({}, base.favourites, raw.favourites);
  ['moods', 'posts', 'chats', 'checkins', 'tasks', 'plans'].forEach((k) => {
    if (!Array.isArray(out[k])) out[k] = [];
  });
  out.chats = out.chats.map((c) => Object.assign({ messages: [] }, c));
  return out;
}

module.exports = { KEY, VERSION, schema, migrate };
