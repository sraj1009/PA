// 离线模式语言引擎：纯本地词库启发式，不联网、不调用模型、不随机。
// 它被要求"真的能用"而不是占位：分类要能读懂否定和程度，匹配要能给出理由，
// 聊天要能接住情绪并回指用户说过的内容。所有结果对同一输入必须完全一致。
const L = require('./lexicon');
const { mmhh } = require('../core/planner');

const STRONG = {
  焦虑: 1.3, 紧张: 1.1, 开心: 1.2, 高兴: 1.1, 难过: 1.2, 伤心: 1.2,
  生气: 1.2, 愤怒: 1.3, 崩溃: 1.4, 失眠: 1.2, 压力: 1.1, 平静: 0.9,
  还行: 0.8, 一般: 0.7, 淡定: 0.8,
};

const MOODS = ['joy', 'low', 'anxious', 'angry', 'calm'];

function weightOf(mood, word) {
  if (STRONG[word] != null) return STRONG[word];
  return mood === 'calm' ? 0.85 : 1;
}

/** Text before a hit, clipped at the last punctuation so 不 in an earlier clause cannot leak. */
function beforeFragment(t, i) {
  let frag = t.slice(Math.max(0, i - 4), i);
  L.SEPARATORS.forEach((s) => {
    const k = frag.lastIndexOf(s);
    if (k >= 0) frag = frag.slice(k + 1);
  });
  return frag;
}

function negated(t, i) {
  const frag = beforeFragment(t, i);
  return L.NEGATIONS.some((n) => frag.indexOf(n) >= 0);
}

function multiplier(t, i, word) {
  const around = t.slice(Math.max(0, i - 3), i) + word + t.slice(i + word.length, i + word.length + 3);
  let count = 0;
  L.INTENSIFIERS.forEach((x) => {
    if (around.indexOf(x) >= 0) count += 1;
  });
  return Math.min(2.2, 1 + 0.35 * count);
}

/** Every lexicon occurrence, with longer words claiming overlapping spans first. */
function hits(text) {
  const t = (text || '').toLowerCase();
  const found = [];
  MOODS.forEach((mood) => {
    L.MOOD_WORDS[mood].forEach((word) => {
      const w = word.trim().toLowerCase();
      if (!w) return;
      let from = 0;
      for (;;) {
        const i = t.indexOf(w, from);
        if (i < 0) break;
        found.push({ mood, word: w, index: i, end: i + w.length });
        from = i + 1;
      }
    });
  });

  found.sort((a, b) => a.index - b.index || b.word.length - a.word.length);
  const kept = [];
  found.forEach((h) => {
    if (kept.some((k) => k.index < h.end && h.index < k.end)) return;
    kept.push(h);
  });
  return kept;
}

function classify(text) {
  const score = { joy: 0, low: 0, anxious: 0, angry: 0, calm: 0 };
  const t = (text || '').toLowerCase();

  hits(text).forEach((h) => {
    const neg = negated(t, h.index);
    const target = neg ? L.NEGATED_TARGET[h.mood] : h.mood;
    const mult = multiplier(t, h.index, h.word) * (neg ? 0.8 : 1);
    score[target] += weightOf(h.mood, h.word) * mult;
  });

  const bangs = (t.match(/[!！]/g) || []).length;
  const punct = Math.min(0.3, 0.1 * bangs);

  let mood = 'calm';
  MOODS.forEach((m) => {
    if (score[m] > score[mood]) mood = m;
  });
  const top = score[mood];
  if (top <= 0) return { mood: 'calm', intensity: 0 };

  const intensity = Math.max(0, Math.min(1, top / 2.5 + punct));
  return { mood, intensity: Math.round(intensity * 100) / 100 };
}

function bigrams(s) {
  const t = (s || '').trim().toLowerCase();
  if (t.length < 2) return t ? [t] : [];
  const out = [];
  for (let i = 0; i < t.length - 1; i += 1) out.push(t.slice(i, i + 2));
  return out;
}

function idfFactory(pool) {
  const df = {};
  pool.forEach((g) => {
    new Set(g.tags || []).forEach((tag) => { df[tag] = (df[tag] || 0) + 1; });
  });
  return (tag) => Math.log(1 + pool.length / (1 + (df[tag] || 0)));
}

/**
 * 关键词 + IDF + 共现打分：可解释、可复现，且不需要任何模型。
 * （向量模型在本机上实测对中文匹配不可靠，已明确不再使用。）
 */
function match(profile, pool) {
  const docs = pool || [];
  const interests = ((profile && profile.interests) || []).map((x) => String(x).trim()).filter(Boolean);
  const idf = idfFactory(docs);

  const rows = docs.map((g, idx) => {
    const reasons = [];
    let score = 0;
    const touched = [];

    interests.forEach((need) => {
      let best = 0;
      let why = '';
      (g.tags || []).forEach((tag) => {
        let w = 0;
        let whyTag = '';
        if (tag === need) {
          w = 1;
          whyTag = '你要的「' + need + '」正好是它的标签';
        } else if (tag.indexOf(need) >= 0 || need.indexOf(tag) >= 0) {
          w = 0.9;
          whyTag = '你要的「' + need + '」和它的「' + tag + '」是同一类';
        } else {
          const a = bigrams(need);
          const b = bigrams(tag);
          const shared = a.filter((x) => b.indexOf(x) >= 0).length;
          const ov = a.length ? shared / a.length : 0;
          if (ov > 0) {
            w = ov * 0.7;
            whyTag = '你要的「' + need + '」和它的「' + tag + '」有共同的用字';
          }
        }
        if (w > best) {
          best = w;
          why = whyTag;
        }
      });
      if (best >= 0.3) {
        score += best * idf(tagOf(g, need));
        reasons.push(why);
        touched.push(need);
      }
    });

    if (touched.length > 1) score += 0.3 * (touched.length - 1);

    return {
      id: g.id,
      name: g.name,
      tags: g.tags,
      score: Math.round(Math.max(0, score) * 1000) / 1000,
      reasons,
      idx,
    };
  });

  return rows.sort((a, b) => b.score - a.score || a.idx - b.idx).map((r) => {
    const out = { id: r.id, name: r.name, tags: r.tags, score: r.score, reasons: r.reasons };
    return out;
  });
}

// The tag that actually carried the match, so IDF is applied to the right term.
function tagOf(group, need) {
  const tags = group.tags || [];
  const exact = tags.find((t) => t === need);
  if (exact) return exact;
  const partial = tags.find((t) => t.indexOf(need) >= 0 || need.indexOf(t) >= 0);
  if (partial) return partial;
  const nb = bigrams(need);
  return tags.find((t) => bigrams(t).some((x) => nb.indexOf(x) >= 0)) || need;
}

function pickTopic(text) {
  const runs = (text || '').match(/[一-龥]{2,}/g) || [];
  const pieces = [];
  runs.forEach((run) => {
    let cur = run;
    L.TOPIC_STOP.forEach((s) => {
      cur = cur.split(s).join('\u0001');
    });
    cur.split('\u0001').forEach((p) => {
      if (p.length >= 2) pieces.push(p);
    });
  });
  if (!pieces.length) return L.FALLBACK_TOPIC;
  const longest = pieces.reduce((a, b) => (b.length > a.length ? b : a), pieces[0]);
  return longest.slice(0, 6);
}

function bankFor(mood, persona) {
  const set = L.REPLIES[mood] || L.REPLIES.calm;
  return set[persona] || set.warm;
}

function tailFor(persona, round) {
  const tails = {
    warm: ['', ' 想多说说吗，我在听。', ' 不用急着给结论。'],
    curious: ['', ' 能再说具体一点吗？', ' 我好奇的是中间那步。'],
    playful: ['', ' 别藏着，细节呢。', ' 这事儿我记下了。'],
  };
  const list = tails[persona] || tails.warm;
  return list[round % list.length];
}

/** 回复按轮次循环选模板并回指用户内容：同一句输入、同一轮次必然得到同一句回复。 */
function chat(turns, userText, persona) {
  const tone = persona === 'playful' || persona === 'curious' ? persona : 'warm';
  const c = classify(userText);
  const bank = bankFor(c.mood, tone);
  const turn = (turns || []).length;
  const base = bank[turn % bank.length];
  const round = Math.floor(turn / bank.length);
  const topic = pickTopic(userText);
  return { text: base.split('{topic}').join(topic) + tailFor(tone, round), mood: c.mood };
}

function explain(plan) {
  const slots = (plan && plan.slots) || [];
  const over = (plan && plan.unscheduled) || [];
  if (!slots.length) {
    return over.length
      ? '今天的时间已经排满，' + over.join('、') + ' 只能顺延到明天。'
      : '今天还没有待办事项，先加一条再排。';
  }
  const head = slots
    .map((s) => mmhh(s.start) + ' - ' + mmhh(s.end) + ' ' + s.title)
    .join('；');
  const tail = over.length
    ? '。今天放不下：' + over.join('、') + '。'
    : '。全部排得下，收尾还留有空闲。';
  return '今天安排 ' + slots.length + ' 段：' + head + tail;
}

module.exports = { classify, match, chat, explain, hits, pickTopic, bigrams };
