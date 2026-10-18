import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const root = fileURLToPath(new URL('../', import.meta.url));
const candidates = [process.env.TITAN_PYTHON, path.join(root, '.venv/bin/python'), path.join(root, '.venv/Scripts/python.exe'), '/workspace/.titan-venv/bin/python'];
const python = candidates.find(candidate => candidate && existsSync(candidate)) || 'python3';
const children = new Set();
let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  for (const child of children) child.kill('SIGTERM');
  process.exitCode = code;
  setTimeout(() => { for (const child of children) child.kill('SIGKILL'); }, 2000).unref();
}
function run(command, args) {
  const child = spawn(command, args, { cwd: root, stdio: 'inherit', env: process.env });
  children.add(child);
  child.on('error', error => { console.error(error.message); stop(1); });
  child.on('exit', code => { children.delete(child); if (!stopping) stop(code || 1); });
  return child;
}
for (const signal of ['SIGINT', 'SIGTERM']) process.on(signal, () => stop());

try {
  // Never adopt or stop an unrelated process occupying the API port.
  let occupied = false;
  try { const response = await fetch('http://127.0.0.1:8000/api/health', { signal: AbortSignal.timeout(1000) }); occupied = response.ok; } catch { /* Start our own backend. */ }
  if (occupied) throw new Error('Port 8000 is already in use. Stop the existing backend, or run npm run dev:ui to reuse it.');
  run(python, ['-m', 'uvicorn', 'backend.app:app', '--host', '127.0.0.1', '--port', '8000']);
  let ready = false;
  for (let attempt = 0; attempt < 80 && !stopping; attempt++) {
    try {
      const response = await fetch('http://127.0.0.1:8000/api/health', { signal: AbortSignal.timeout(500) });
      const health = await response.json();
      if (health.ready) { ready = true; break; }
      if (health.error) throw new Error(health.error);
    } catch (error) {
      if (error instanceof Error && !['TypeError', 'TimeoutError'].includes(error.name)) throw error;
    }
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  if (!ready) throw new Error('The app server did not become ready. Run setup first and inspect the error above.');
  console.log('\nApp server ready. Starting Space Studio.\n');
  run(process.execPath, [path.join(root, 'node_modules/vite/bin/vite.js'), '--host', '0.0.0.0']);
} catch (error) { console.error(`\n${error.message}\n`); stop(1); }
