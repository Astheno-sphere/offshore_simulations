#!/usr/bin/env node
// Screenshot a built Pocket City in headless Chrome, to check it without opening a browser.
//   node render.mjs pocket-city.html --out shots/ [--season winter] [--view iso,bird] [--size 1440x900] [--zoom 3]
// Writes one PNG per view (and per season if you give several, comma separated) and prints any page errors.
// Needs Google Chrome or Chromium (set CHROME=/path/to/chrome if it is somewhere unusual). Node 18+ (built-in WebSocket
// from Node 22; on older Node it falls back to the "ws" package if installed).
import { spawn } from 'node:child_process'; import fs from 'node:fs'; import path from 'node:path'; import os from 'node:os';
const args = process.argv.slice(2), file = args.find(a => !a.startsWith('--') && /\.html?$/.test(a));
const opt = k => { const i = args.indexOf('--' + k); return i >= 0 ? args[i + 1] : null; };
if (!file) { console.log('usage: node render.mjs page.html --out shots/ [--season id,id] [--view id,id] [--size WxH] [--zoom k]'); process.exit(1); }
const out = opt('out') || 'shots', [W, H] = (opt('size') || '1440x900').split('x').map(Number);
const seasons = (opt('season') || '').split(',').filter(Boolean), views = (opt('view') || 'iso').split(',');
const zoom = opt('zoom') ? +opt('zoom') : null;
fs.mkdirSync(out, { recursive: true });
const candidates = [process.env.CHROME, '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome', '/Applications/Chromium.app/Contents/MacOS/Chromium',
  '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser', '/snap/bin/chromium',
  'C:/Program Files/Google/Chrome/Application/chrome.exe'].filter(Boolean);
const chromePath = candidates.find(p => { try { return fs.statSync(p).isFile(); } catch { return false; } });
if (!chromePath) { console.log('No Chrome found. Set CHROME=/path/to/chrome, or open the page in a browser to check it.'); process.exit(2); }
const port = 9300 + Math.floor(Math.random() * 400), dir = fs.mkdtempSync(path.join(os.tmpdir(), 'pc-'));
const chrome = spawn(chromePath, ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${dir}`, '--no-first-run', '--hide-scrollbars', `--window-size=${W},${H}`, 'about:blank'], { stdio: 'ignore' });
const sleep = ms => new Promise(r => setTimeout(r, ms));
let WS = globalThis.WebSocket; if (!WS) { try { WS = (await import('ws')).default; } catch { console.log('Node 22+ needed (or npm i ws).'); process.exit(2); } }
let ws; for (let i = 0; i < 100 && !ws; i++) { await sleep(150); try { const t = (await (await fetch(`http://127.0.0.1:${port}/json/list`)).json()).find(t => t.type === 'page'); if (t) ws = new WS(t.webSocketDebuggerUrl); } catch {} }
if (!ws) { console.log('Chrome did not start.'); chrome.kill(); process.exit(2); }
await new Promise(r => ws.addEventListener ? ws.addEventListener('open', r, { once: true }) : ws.on('open', r));
let id = 0; const pend = new Map(), errors = [];
const onMsg = e => { const m = JSON.parse(e.data ?? e); if (m.id && pend.has(m.id)) { pend.get(m.id)(m); pend.delete(m.id); }
  if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
  if (m.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(m.params.type)) errors.push(m.params.args.map(a => a.value ?? a.description).join(' ')); };
ws.addEventListener ? ws.addEventListener('message', onMsg) : ws.on('message', onMsg);
const send = (method, params = {}) => new Promise(r => { const i = ++id; pend.set(i, r); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async x => (await send('Runtime.evaluate', { expression: x, awaitPromise: true, returnByValue: true })).result?.result?.value;
await send('Runtime.enable'); await send('Page.enable');
await send('Emulation.setDeviceMetricsOverride', { width: W, height: H, deviceScaleFactor: 1, mobile: W < 700 });
await send('Page.navigate', { url: 'file://' + path.resolve(file) });
const ready = async () => { for (let i = 0; i < 240; i++) { await sleep(250); if (await ev(`document.getElementById('loading')?.hidden`)) return true; } return false; };
if (!await ready()) errors.push('The drawing did not appear within 60 s.');
const shots = [];
for (const s of seasons.length ? seasons : [null]) {
  if (s) { await ev(`selectSeason(${JSON.stringify(s)})`); await sleep(1500); }
  for (const v of views) {
    await ev(`setView(${JSON.stringify(v)});camera={...goal}${zoom ? `;goal.zoom=camera.zoom=iso.zoom*${zoom}` : ''};redraw()`);
    await sleep(2600);
    const shot = await send('Page.captureScreenshot', { format: 'png' });
    const name = path.join(out, `${path.basename(file, '.html')}${s ? '-' + s : ''}-${v}${zoom ? '-x' + zoom : ''}.png`);
    fs.writeFileSync(name, Buffer.from(shot.result.data, 'base64')); shots.push(name);
  }
}
console.log('Saved', shots.join(', '));
if (errors.length) { console.log('Page errors:'); for (const e of [...new Set(errors)].slice(0, 12)) console.log('  ' + String(e).slice(0, 400)); }
chrome.kill(); await sleep(400); try { fs.rmSync(dir, { recursive: true, force: true }); } catch {}
process.exit(errors.length ? 1 : 0);
