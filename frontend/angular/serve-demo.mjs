/** Loopback-only static preview + streaming proxy. No credentials are served to browsers. */
import { createServer, request as httpRequest } from 'node:http';
import { createReadStream, existsSync, statSync } from 'node:fs';
import { resolve, extname, sep } from 'node:path';
import { pipeline } from 'node:stream';

const root = resolve(process.env['UI_DIST'] || 'dist/expertai/browser');
const port = Number(process.env['UI_PORT'] || 8126);
const backend = new URL(process.env['EXPERT_BACKEND'] || 'http://127.0.0.1:8127');
if (backend.protocol !== 'http:' || !['127.0.0.1', '[::1]'].includes(backend.hostname)) throw new Error('Preview backend must be loopback HTTP.');
if (!existsSync(resolve(root, 'index.html'))) throw new Error('Build the Angular frontend first.');
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };
const csp = "default-src 'none'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'self'; frame-ancestors 'self'; form-action 'none'";
createServer((req, res) => {
  res.setHeader('X-Content-Type-Options', 'nosniff');
  res.setHeader('Referrer-Policy', 'no-referrer');
  res.setHeader('Content-Security-Policy', csp);
  res.setHeader('Permissions-Policy', 'camera=(), microphone=(), geolocation=()');
  if (!/^(127\.0\.0\.1|localhost)(:\d+)?$/.test(req.headers.host || '')) { res.writeHead(403).end('Loopback preview only.'); return; }
  const url = new URL(req.url, 'http://127.0.0.1');
  if (url.pathname.startsWith('/api/')) {
    if (req.method !== 'GET' && req.headers.origin && req.headers.origin !== `http://${req.headers.host}`) { res.writeHead(403).end('Same-origin requests only.'); return; }
    if (!/^\/api\/v2\/(chat\/stream|catalogue|status|sessions\/[^/]+|recommendation-events)$/.test(url.pathname)) {
      res.writeHead(404).end('Not available in this preview.'); return;
    }
    const headers = { ...req.headers, host: backend.host };
    // The validated browser origin becomes this trusted same-origin proxy hop.
    if (headers.origin) headers.origin = backend.origin;
    delete headers.connection;
    const upstream = httpRequest(new URL(url.pathname + url.search, backend), { method: req.method, headers }, response => {
      res.writeHead(response.statusCode || 502, { 'Content-Type': response.headers['content-type'] || 'application/json', 'Cache-Control': 'no-store', 'X-Accel-Buffering': 'no' });
      pipeline(response, res, () => {});
    });
    upstream.setTimeout(180_000, () => upstream.destroy());
    upstream.on('error', () => { if (!res.headersSent) res.writeHead(502, { 'Content-Type': 'application/problem+json' }).end(JSON.stringify({ title: 'The private preview backend is unavailable.' })); else res.destroy(); });
    res.on('close', () => upstream.destroy());
    pipeline(req, upstream, () => {});
    return;
  }
  if (!['GET', 'HEAD'].includes(req.method)) { res.writeHead(405).end(); return; }
  let pathname;
  try { pathname = decodeURIComponent(url.pathname); } catch { res.writeHead(400).end(); return; }
  const file = resolve(root, '.' + pathname);
  if (!file.startsWith(root + sep) && file !== root) { res.writeHead(403).end(); return; }
  const target = existsSync(file) && statSync(file).isFile() ? file : pathname === '/' ? resolve(root, 'index.html') : null;
  if (!target) { res.writeHead(404).end('Not found'); return; }
  res.setHeader('Content-Type', types[extname(target)] || 'application/octet-stream');
  res.setHeader('Cache-Control', extname(target) === '.html' ? 'no-cache' : 'public, max-age=3600');
  const compressed = /\bgzip\b/.test(req.headers['accept-encoding'] || '') && existsSync(target + '.gz');
  res.setHeader('Vary', 'Accept-Encoding');
  if (compressed) res.setHeader('Content-Encoding', 'gzip');
  if (req.method === 'HEAD') res.end(); else pipeline(createReadStream(compressed ? target + '.gz' : target), res, () => {});
}).listen(port, '127.0.0.1', () => console.log(`ExpertAI private UI at http://127.0.0.1:${port}`));
