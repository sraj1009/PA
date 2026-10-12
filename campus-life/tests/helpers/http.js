// Real transport for the live Ollama suite only: same call shape as wx.request,
// so agent/llm.js is exercised against a running model with no code changes.
const http = require('http');
const { URL } = require('url');

function request(options) {
  const u = new URL(options.url);
  const payload = typeof options.data === 'string' ? options.data : JSON.stringify(options.data || {});

  const req = http.request(
    {
      hostname: u.hostname,
      port: u.port || 80,
      path: u.pathname + u.search,
      method: options.method || 'GET',
      headers: Object.assign({ 'content-type': 'application/json' }, options.header || {}),
    },
    (res) => {
      let body = '';
      res.setEncoding('utf8');
      res.on('data', (c) => { body += c; });
      res.on('end', () => {
        let data = body;
        try {
          data = JSON.parse(body);
        } catch (e) {
          data = body; // a non-JSON body must reach the parser in llm.js unchanged
        }
        if (options.success) options.success({ statusCode: res.statusCode, data });
      });
    },
  );

  req.on('error', (e) => {
    if (options.fail) options.fail({ errMsg: e.message });
  });
  if (options.timeout) {
    req.setTimeout(options.timeout, () => req.destroy(new Error('request timeout')));
  }
  if (payload) req.write(payload);
  req.end();
}

module.exports = { request };
