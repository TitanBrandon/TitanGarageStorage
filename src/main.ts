import './style.css';
import Viewer from './viewer';

const icons: Record<string, string> = {
  cube: '<path d="m12 3 9 5v8l-9 5-9-5V8l9-5Z"/><path d="m3 8 9 5 9-5M12 13v8M7.5 5.5l9 5"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
  arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m21 15-6-6-12 12"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
  walk: '<circle cx="14" cy="4" r="2"/><path d="m7 21 4-7 3 3v5M6 12l3-4 4 1 3 4h4M11 9v6"/>',
  orbit: '<ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(-30 12 12)"/><circle cx="12" cy="12" r="2"/>',
  reset: '<path d="M3 10a9 9 0 1 1 1 7M3 4v6h6"/>',
  expand: '<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',
  layers: '<path d="m12 3 10 5-10 5L2 8l10-5ZM2 12l10 5 10-5M2 16l10 5 10-5"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1 1m12 12 1 1M5 19l1-1M18 6l1-1"/>',
  external: '<path d="M14 3h7v7m0-7L10 14M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5"/>',
};
function icon(name: string) { return `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.cube}</svg>`; }

document.querySelector<HTMLDivElement>('#app')!.innerHTML = `
  <header class="topbar">
    <a class="brand" href="/" aria-label="Titan Space Studio home"><span class="brand-mark">T</span><span class="brand-word">TITAN<span>GARAGE STORAGE</span></span></a>
    <span class="brand-divider"></span><span class="studio-name">Space Studio <span class="beta">LAB</span></span>
    <button class="help-button" id="help">${icon('info')} <span>How it works</span></button>
  </header>
  <main>
    <section class="page-heading"><div><div class="eyebrow"><span></span> SEE YOUR SPACE IN A NEW WAY</div><h1>Your photo. A place to step into.</h1><p>Create a photorealistic, AI-generated scene you can look around and explore.</p></div><span class="private-badge">${icon('layers')} Powered by World Labs</span></section>
    <section class="workspace" aria-label="3D workspace">
      <aside class="sidebar">
        <div class="sidebar-heading"><span class="section-number">01</span><h2>Start with your space</h2></div>
        <p class="sidebar-description">Bring a real photo. Build a new perspective.<br>A garage, a showroom, your next project.</p>
        <input id="photo-input" type="file" accept="image/jpeg,image/png,image/webp" hidden />
        <button class="upload-zone" id="upload-zone"><span class="upload-icon">${icon('upload')}</span><strong>Drop your photo here</strong><span>or <u>browse files</u></span><small>JPG, PNG or WebP · Up to 15 MB</small></button>
        <div id="photo-card" class="photo-card" hidden><img id="photo-preview" alt="Your selected space" /><div><strong id="photo-name"></strong><span id="photo-size"></span></div><button id="remove-photo" class="icon-button" aria-label="Remove selected photo">${icon('close')}</button></div>
        <label class="quality-label" for="quality">Generation quality</label>
        <select id="quality"><option value="plus">Plus · Best quality</option><option value="mini">Mini · Quick preview</option></select>
        <p class="quality-note" id="quality-note">More detail for your first full walkthrough.</p>
        <div class="provider-card" id="provider-card" role="status"><span class="provider-dot"></span><div><strong id="provider-title">Checking connection…</strong><p id="provider-description">Connecting to your development server.</p><a id="provider-link" href="https://platform.worldlabs.ai/" target="_blank" rel="noopener noreferrer" hidden>Open World Labs ${icon('external')}</a><button id="provider-refresh" class="text-button" hidden>Check connection again</button></div></div>
        <p class="billing-notice">Uses your World Labs credits. Your photo is sent to World Labs. Hidden areas are AI-generated.</p>
        <button id="generate" class="primary-button" disabled>${icon('cube')} <span>Generate with World Labs</span>${icon('arrow')}</button>
        <div id="processing" class="processing" role="status" hidden><span class="spinner"></span><span id="processing-text">Creating your world. This can take a few minutes.</span></div>
        <button id="stop-checking" class="text-button waiting-button" hidden>Stop checking</button>
        <button id="resume-checking" class="secondary-button" hidden>Resume checking this generation</button>
        <button id="resolve-request" class="text-button" hidden>I checked World Labs · Clear unresolved request</button>
        <p id="error" class="error-message" role="alert" hidden></p>
        <div class="tip">${icon('sun')}<p><strong>Start with a clear, wide photo.</strong><br>Good light and visible floor space help create a convincing scene.</p></div>
        <div class="sidebar-divider"><span>ALREADY HAVE A 3D SCENE?</span></div>
        <input id="splat-input" type="file" accept=".spz,.ply,.splat" hidden />
        <button id="import-scene" class="secondary-button">${icon('upload')} Open a 3D export</button>
        <p class="import-note">SPZ, PLY or SPLAT · Opens on this device.<br>No World Labs credits needed to view a file.</p>
        <div class="expectation-card">${icon('info')}<div><strong>Realistic appearance. Estimated space.</strong><p>AI creates unseen surfaces from one photo. It can change objects and layouts. For an accurate record of a real space, capture overlapping photos or a spatial scan.</p></div></div>
      </aside>
      <div class="viewer-panel">
        <div class="viewer-topbar"><div class="viewer-title">${icon('cube')}<strong id="scene-name">Your next perspective</strong><span id="scene-badge" class="scene-badge">PHOTO TO WORLD</span></div><button id="fullscreen" class="icon-button" aria-label="Toggle full screen">${icon('expand')}</button></div>
        <div class="canvas-wrap" id="canvas-wrap"><div id="viewer"></div>
          <img id="original-photo" class="original-photo" alt="Your original photo, before 3D generation" hidden />
          <div id="empty-state" class="empty-state"><span class="empty-symbol">${icon('cube')}</span><span class="eyebrow">A NEW PERSPECTIVE STARTS HERE</span><h2>Bring your space to life.</h2><p>Upload a photo to begin.<br>Your real image will appear here first.</p><button id="empty-upload" class="secondary-button">${icon('upload')} Choose a photo</button><span class="empty-rule"></span><small>Your generated world will open in this space.</small></div>
          <div class="view-status"><span></span><span id="view-status">Waiting for your photo</span></div>
          <div id="original-label" class="original-label" hidden>${icon('image')} Original photo <span>3D scene not generated yet</span></div>
          <div class="viewer-hint" id="viewer-hint" hidden>${icon('orbit')} Drag to look around <span>·</span> Scroll to move closer</div>
          <div id="scene-error" class="scene-error" role="alert" hidden></div>
          <div class="direction-pad" id="direction-pad" hidden><button data-move="forward" aria-label="Move forward">↑</button><button data-move="left" aria-label="Move left">←</button><button data-move="backward" aria-label="Move backward">↓</button><button data-move="right" aria-label="Move right">→</button></div>
        </div>
        <div class="viewer-toolbar"><div class="mode-toggle" role="group" aria-label="Camera mode"><button id="orbit-mode" class="active" aria-pressed="true" disabled>${icon('orbit')} Orbit</button><button id="walk-mode" aria-pressed="false" disabled>${icon('walk')} Walk through</button></div><div class="toolbar-right"><a id="open-marble" class="toolbar-button" target="_blank" rel="noopener noreferrer" hidden>${icon('external')}<span>Open Marble viewer</span></a><button id="flip-world" class="toolbar-button" hidden>${icon('reset')}<span>Flip upright</span></button><button id="reset" class="toolbar-button" disabled>${icon('reset')}<span>Reset view</span></button></div></div>
        <p class="scene-disclaimer" id="scene-disclaimer">One photo is the starting point. AI fills in what the camera couldn’t see.</p>
      </div>
    </section>
    <section class="workflow" aria-label="How it works"><div><span>01</span><p><strong>Bring a real photo</strong>A clear view of the space you want to explore.</p></div>${icon('chevron')}<div><span>02</span><p><strong>Generate your world</strong>World Labs creates a photorealistic 3D scene.</p></div>${icon('chevron')}<div><span>03</span><p><strong>Step into a new perspective</strong>Look around, move through, and check the details.</p></div></section>
  </main>
  <footer><span>Built for the spaces with potential.</span><span>TITAN GARAGE STORAGE <span class="footer-dot">·</span> SPACE STUDIO</span></footer>
  <dialog id="help-dialog"><button id="close-help" class="icon-button dialog-close" aria-label="Close help">${icon('close')}</button><span class="eyebrow">FROM PHOTO TO WORLD</span><h2>A real photo.<br>A new way to explore.</h2><p>Upload your photo, choose a quality, then select <strong>Generate with World Labs</strong>. The photo goes to World Labs to generate a photorealistic scene. Generation uses the credits on your World Labs account and can take several minutes.</p><p>When it’s ready, try <strong>Orbit</strong> to drag around the scene, or <strong>Walk through</strong> to look around and move with W, A, S, D or the arrow keys. Press Escape to release the mouse. You can also open the result in the Marble viewer.</p><div class="help-note"><strong>A convincing scene isn’t a measured scan.</strong><p>A single photo can’t show the backs of cars, hidden walls or adjacent rooms. AI invents these details and may change visible objects too. Verify the result against your original photo. For an accurate walkthrough, use a multi-view capture or spatial scan.</p></div><p class="help-privacy">Your API key stays on the server. Selected photos are sent to World Labs only when you choose to generate. An imported 3D export opens locally in your browser. Stopping the progress check does not cancel generation or undo provider charges.</p><button id="got-it" class="primary-button">Let’s explore ${icon('arrow')}</button></dialog>
`;

const el = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
type Pending = { operationId?: string; name: string; startedAt: number };
type World = { worldId?: string; worldUrl?: string; splatUrl?: string; name?: string };
const PENDING_KEY = 'titan.worlds.pending.v1';
const WORLD_KEY = 'titan.worlds.latest.v1';
const readSaved = <T>(key: string): T | null => { try { return JSON.parse(localStorage.getItem(key) || 'null') as T | null; } catch { return null; } };
function save(key: string, value: unknown) { try { if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, JSON.stringify(value)); } catch { /* Local storage can be unavailable. */ } }
let viewer: Viewer | null = null;
let file: File | null = null;
let previewUrl: string | null = null;
let importUrl: string | null = null;
let providerConfigured = false;
let isWorking = false;
let isSubmitting = false;
let worldLoaded = false;
let pollController: AbortController | null = null;
let pending = readSaved<Pending>(PENDING_KEY);
if (pending && (!Number.isFinite(pending.startedAt) || typeof pending.name !== 'string' || (pending.operationId !== undefined && typeof pending.operationId !== 'string'))) { pending = null; save(PENDING_KEY, null); }

function showError(message: string) { el('error').textContent = message; el('error').hidden = false; }
function safeUrl(value?: string): string | null { try { const url = new URL(value || ''); return ['https:', 'http:'].includes(url.protocol) ? url.href : null; } catch { return null; } }
function setStatus(message: string) { el('view-status').textContent = message; }
try {
  viewer = new Viewer(el('viewer'), setStatus);
  viewer.showEmpty();
} catch {
  showError('The embedded 3D viewer needs WebGL2. Enable hardware acceleration or use the Marble viewer link after generation.');
}
setStatus('Waiting for your photo');

function updateControls() {
  const locked = isWorking || !!pending;
  el<HTMLButtonElement>('generate').disabled = !file || !providerConfigured || locked;
  el<HTMLButtonElement>('upload-zone').disabled = locked;
  el<HTMLButtonElement>('empty-upload').disabled = locked;
  el<HTMLInputElement>('photo-input').disabled = locked;
  el<HTMLButtonElement>('remove-photo').disabled = locked;
  el<HTMLSelectElement>('quality').disabled = locked;
  el<HTMLButtonElement>('import-scene').disabled = locked;
  el('processing').hidden = !isWorking;
  el('stop-checking').hidden = !isWorking || isSubmitting || !pending?.operationId;
  el('resume-checking').hidden = isWorking || !pending?.operationId;
  el('resolve-request').hidden = isWorking || !pending || !!pending.operationId;
  el('generate').querySelector('span')!.textContent = isSubmitting ? 'Sending photo…' : isWorking ? 'Generating your world…' : 'Generate with World Labs';
  for (const id of ['orbit-mode', 'walk-mode', 'reset']) el<HTMLButtonElement>(id).disabled = !worldLoaded;
}

async function checkProvider() {
  el<HTMLButtonElement>('provider-refresh').disabled = true;
  try {
    const response = await fetch('/api/worlds/status');
    if (!response.ok) throw new Error();
    const data = await response.json();
    providerConfigured = data.configured === true;
    el('provider-card').classList.toggle('connected', providerConfigured);
    el('provider-title').textContent = providerConfigured ? 'World Labs API key configured' : 'Connect World Labs';
    el('provider-description').textContent = providerConfigured ? 'Requests use your account’s credits. Account access is checked when you generate.' : 'Create a World Labs account with credits. Your API key must be configured on the server.';
    el('provider-link').hidden = false;
    el('provider-refresh').hidden = false;
    if (typeof data.activeOperationId === 'string' && data.activeOperationId && !pending?.operationId) {
      pending = { operationId: data.activeOperationId, name: pending?.name || 'Your generated world', startedAt: pending?.startedAt || Date.now() };
      save(PENDING_KEY, pending);
      if (!isWorking) void pollOperation();
    }
  } catch {
    providerConfigured = false;
    el('provider-card').classList.remove('connected');
    el('provider-title').textContent = 'Server connection unavailable';
    el('provider-description').textContent = 'Start the Space Studio server, then check the connection again.';
    el('provider-refresh').hidden = false;
    el('provider-link').hidden = true;
  } finally { el<HTMLButtonElement>('provider-refresh').disabled = false; updateControls(); }
}
el('provider-refresh').addEventListener('click', checkProvider);
el<HTMLSelectElement>('quality').addEventListener('change', () => { el('quality-note').textContent = el<HTMLSelectElement>('quality').value === 'mini' ? 'A faster first look with less detail. Uses World Labs credits.' : 'More detail for your first full walkthrough.'; });

function showOriginal() {
  el('flip-world').hidden = true;
  worldLoaded = false;
  viewer?.showEmpty();
  el('viewer').classList.remove('world-ready');
  el('viewer-hint').hidden = true;
  el('direction-pad').hidden = true;
  el('scene-error').hidden = true;
  el('original-photo').hidden = !previewUrl;
  el('original-label').hidden = !previewUrl;
  el('empty-state').hidden = !!previewUrl;
  if (previewUrl) el<HTMLImageElement>('original-photo').src = previewUrl;
  el('scene-name').textContent = file?.name.replace(/\.[^.]+$/, '') || 'Your next perspective';
  el('scene-badge').textContent = previewUrl ? 'ORIGINAL PHOTO' : 'PHOTO TO WORLD';
  el('open-marble').hidden = true;
  el('scene-disclaimer').textContent = 'One photo is the starting point. AI fills in what the camera couldn’t see.';
  setStatus(previewUrl ? 'Original photo · Ready to generate' : 'Waiting for your photo');
  updateControls();
}
function selectFile(selected?: File) {
  if (!selected || isWorking || pending) return;
  el('error').hidden = true;
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(selected.type)) { showError('Choose a JPG, PNG or WebP image.'); return; }
  if (selected.size > 15 * 1024 * 1024) { showError('This photo is over 15 MB. Choose a smaller image.'); return; }
  if (!selected.size) { showError('This image file is empty. Choose another photo.'); return; }
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  file = selected;
  previewUrl = URL.createObjectURL(file);
  el<HTMLImageElement>('photo-preview').src = previewUrl;
  el('photo-name').textContent = file.name;
  el('photo-size').textContent = `${(file.size / 1024 / 1024).toFixed(1)} MB · Original photo`;
  el('photo-card').hidden = false;
  el('upload-zone').classList.add('compact');
  showOriginal();
}
el('upload-zone').addEventListener('click', () => el<HTMLInputElement>('photo-input').click());
el('empty-upload').addEventListener('click', () => el<HTMLInputElement>('photo-input').click());
el<HTMLInputElement>('photo-input').addEventListener('change', event => selectFile((event.target as HTMLInputElement).files?.[0]));
for (const type of ['dragenter', 'dragover']) el('upload-zone').addEventListener(type, event => { event.preventDefault(); if (!isWorking && !pending) el('upload-zone').classList.add('dragging'); });
for (const type of ['dragleave', 'drop']) el('upload-zone').addEventListener(type, event => { event.preventDefault(); el('upload-zone').classList.remove('dragging'); });
el('upload-zone').addEventListener('drop', event => selectFile((event as DragEvent).dataTransfer?.files?.[0]));
el('remove-photo').addEventListener('click', () => {
  if (isWorking || pending) return;
  file = null;
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = null;
  el<HTMLInputElement>('photo-input').value = '';
  el('photo-card').hidden = true;
  el('upload-zone').classList.remove('compact');
  showOriginal();
});

function setMode(mode: 'walk' | 'orbit') {
  if (!worldLoaded) return;
  viewer?.setMode(mode);
  for (const item of ['walk', 'orbit']) { el(`${item}-mode`).classList.toggle('active', item === mode); el(`${item}-mode`).setAttribute('aria-pressed', String(item === mode)); }
  const touch = window.matchMedia('(pointer: coarse)').matches || window.innerWidth <= 760;
  el('viewer-hint').innerHTML = mode === 'walk' ? touch ? `${icon('walk')} Drag to look <span>·</span> Hold arrows to move` : `${icon('walk')} Click scene to look <span>·</span> WASD / arrows to move <span>·</span> Esc to release` : `${icon('orbit')} Drag to look around <span>·</span> Scroll to move closer`;
  el('direction-pad').hidden = mode !== 'walk';
}
async function displayWorld(world: World) {
  el('flip-world').hidden = true;
  const worldUrl = safeUrl(world.worldUrl);
  const splatUrl = safeUrl(world.splatUrl);
  el('scene-name').textContent = world.name || pending?.name || 'Your generated world';
  el('scene-badge').textContent = 'AI-GENERATED WORLD';
  el('scene-disclaimer').textContent = 'AI-generated scene from your photo; check details against the original.';
  el('original-label').hidden = true;
  el('scene-error').hidden = true;
  el('open-marble').hidden = !worldUrl;
  if (worldUrl) { el<HTMLAnchorElement>('open-marble').href = worldUrl; el('open-marble').querySelector('span')!.textContent = 'Open Marble viewer'; }
  setStatus('World generated · Loading the 3D scene');
  if (!splatUrl || !viewer) {
    setStatus('World generated · Open the Marble viewer to explore');
    el('scene-error').textContent = worldUrl ? 'Your world is ready. Select “Open Marble viewer” below to explore it.' : 'The world was generated, but no viewable scene link was returned. Check your World Labs account.';
    el('scene-error').hidden = false;
    return;
  }
  try {
    await viewer.loadWorld(splatUrl);
    worldLoaded = true;
    el('viewer').classList.add('world-ready');
    el('original-photo').hidden = true;
    el('empty-state').hidden = true;
    el('viewer-hint').hidden = false;
    setMode('orbit');
    setStatus('Photorealistic AI scene · Ready to explore');
  } catch {
    worldLoaded = false;
    setStatus('World generated · Embedded viewer unavailable');
    el('scene-error').textContent = worldUrl ? 'This browser couldn’t display the 3D file. Select “Open Marble viewer” below to explore your generated world.' : 'This browser couldn’t display the 3D file. Try a current browser with hardware acceleration enabled.';
    el('scene-error').hidden = false;
  }
  updateControls();
}
function waitForPoll(signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const stop = () => { clearTimeout(timer); reject(new DOMException('Stopped checking', 'AbortError')); };
    const timer = window.setTimeout(() => { signal.removeEventListener('abort', stop); resolve(); }, 3000);
    signal.addEventListener('abort', stop, { once: true });
    if (signal.aborted) stop();
  });
}
async function pollOperation() {
  if (!pending?.operationId || isWorking) return;
  const saved = pending;
  const operationId = saved.operationId!;
  isWorking = true;
  el('error').hidden = true;
  el('processing-text').textContent = 'Creating your world. This can take several minutes.';
  el('scene-name').textContent = saved.name;
  el('scene-badge').textContent = 'GENERATING WORLD';
  setStatus('World Labs is generating your scene');
  const controller = new AbortController();
  pollController = controller;
  const startedChecking = Date.now();
  updateControls();
  try {
    while (!controller.signal.aborted) {
      const response = await fetch(`/api/worlds/operations/${encodeURIComponent(operationId)}`, { signal: controller.signal });
      if (!response.ok) throw new Error('Couldn’t check this generation. Resume checking when the server is available. No new generation was submitted.');
      const result = await response.json();
      if (result.state === 'failed') {
        pending = null;
        save(PENDING_KEY, null);
        setStatus('World generation failed');
        el('scene-badge').textContent = 'GENERATION FAILED';
        throw new Error(typeof result.message === 'string' ? result.message : 'World Labs could not generate this scene. Check your provider account for details and credit usage.');
      }
      if (result.state === 'ready') {
        const world: World = { worldId: result.worldId, worldUrl: result.worldUrl, splatUrl: result.splatUrl, name: saved.name };
        if (!world.worldUrl && !world.splatUrl) throw new Error('The operation completed without a scene link. Check your World Labs account before starting another generation.');
        save(WORLD_KEY, world);
        pending = null;
        save(PENDING_KEY, null);
        el('processing-text').textContent = 'Your world is ready. Loading the 3D scene…';
        updateControls();
        await displayWorld(world);
        return;
      }
      if (Date.now() - startedChecking > 20 * 60_000) throw new Error('This generation is taking longer than usual. You can resume checking later. It may still be running at World Labs; don’t submit it again.');
      await waitForPoll(controller.signal);
    }
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') setStatus('Progress check paused · Generation may still be running');
    else { showError(error instanceof Error ? error.message : 'Couldn’t check this generation. Resume checking later; no new generation was submitted.'); if (pending) setStatus('Progress check interrupted · Resume checking below'); }
  } finally { if (pollController === controller) pollController = null; isWorking = false; updateControls(); }
}
el('generate').addEventListener('click', async () => {
  if (!file || !providerConfigured || isWorking || pending) return;
  const selected = file;
  isWorking = true;
  isSubmitting = true;
  pending = { name: selected.name.replace(/\.[^.]+$/, ''), startedAt: Date.now() };
  save(PENDING_KEY, pending);
  el('error').hidden = true;
  el('processing-text').textContent = 'Sending your photo to World Labs…';
  setStatus('Submitting your photo to World Labs');
  updateControls();
  try {
    const form = new FormData();
    form.append('photo', selected);
    form.append('quality', el<HTMLSelectElement>('quality').value);
    const response = await fetch('/api/worlds', { method: 'POST', body: form });
    const result = await response.json().catch(() => null);
    if (!response.ok) {
      if ([400, 401, 402, 403, 413, 415, 422, 429, 503].includes(response.status)) { pending = null; save(PENDING_KEY, null); }
      throw new Error(typeof result?.detail === 'string' ? result.detail : 'The generation request could not be completed.');
    }
    if (typeof result?.operationId !== 'string' || !result.operationId) throw new Error('The server did not return a generation ID.');
    pending.operationId = result.operationId;
    save(PENDING_KEY, pending);
    isWorking = false;
    isSubmitting = false;
    await pollOperation();
  } catch (error) {
    const message = error instanceof Error ? error.message : 'The server connection was interrupted.';
    showError(pending ? `${message} The request may already be running and using credits. Check your World Labs account before starting another generation. Reloading this page will not submit it again.` : message);
    setStatus(pending ? 'Request status unknown · Check your World Labs account' : 'Photo ready · Generation did not start');
  } finally { isWorking = false; isSubmitting = false; updateControls(); }
});
el('stop-checking').addEventListener('click', () => { pollController?.abort(); showError('Progress checks are paused. World Labs may still finish the scene and charge credits. Resume checking to retrieve this same generation.'); });
el('resume-checking').addEventListener('click', pollOperation);
el('resolve-request').addEventListener('click', () => {
  if (isWorking || !pending || pending.operationId) return;
  pending = null;
  save(PENDING_KEY, null);
  el('error').hidden = true;
  setStatus('Unresolved request cleared · No generation submitted');
  updateControls();
});
el('import-scene').addEventListener('click', () => el<HTMLInputElement>('splat-input').click());
el<HTMLInputElement>('splat-input').addEventListener('change', async event => {
  const selected = (event.target as HTMLInputElement).files?.[0];
  if (!selected || isWorking || pending) return;
  el('error').hidden = true;
  if (!/\.(spz|ply|splat)$/i.test(selected.name) || !selected.size) { showError('Choose a non-empty SPZ, PLY or SPLAT file.'); return; }
  if (!viewer) { showError('This browser cannot display 3D exports. Enable hardware acceleration and reload.'); return; }
  isWorking = true;
  el('processing-text').textContent = 'Opening your 3D export on this device…';
  updateControls();
  const url = URL.createObjectURL(selected);
  try {
    await viewer.loadWorld(url, selected.name);
    if (importUrl) URL.revokeObjectURL(importUrl);
    importUrl = url;
    worldLoaded = true;
    el('viewer').classList.add('world-ready');
    for (const id of ['original-photo', 'original-label', 'empty-state', 'scene-error', 'open-marble']) el(id).hidden = true;
    el('viewer-hint').hidden = false;
    el('scene-name').textContent = selected.name.replace(/\.[^.]+$/, '');
    el('scene-badge').textContent = 'IMPORTED 3D SCENE';
    el('flip-world').hidden = false;
    el('scene-disclaimer').textContent = 'Imported 3D scene · This file is being viewed locally on your device.';
    setMode('orbit');
    setStatus('Imported 3D scene · Ready to explore');
  } catch { URL.revokeObjectURL(url); showOriginal(); showError('This 3D export could not be opened. Use an SPZ, PLY or SPLAT scene and a browser with hardware acceleration enabled.'); }
  finally { isWorking = false; updateControls(); }
});

el('walk-mode').addEventListener('click', () => setMode('walk'));
el('orbit-mode').addEventListener('click', () => setMode('orbit'));
el('reset').addEventListener('click', () => viewer?.reset());
el('flip-world').addEventListener('click', () => viewer?.flipOrientation());
el('fullscreen').addEventListener('click', async () => { try { if (document.fullscreenElement) await document.exitFullscreen(); else await el('canvas-wrap').requestFullscreen(); } catch { showError('Full screen isn’t available in this browser.'); } });
document.querySelectorAll<HTMLButtonElement>('[data-move]').forEach(button => {
  const direction = button.dataset.move as 'forward' | 'backward' | 'left' | 'right';
  button.addEventListener('pointerdown', event => { event.preventDefault(); button.setPointerCapture(event.pointerId); viewer?.move(direction, true); });
  for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) button.addEventListener(event, () => viewer?.move(direction, false));
});
const dialog = el<HTMLDialogElement>('help-dialog');
el('help').addEventListener('click', () => dialog.showModal());
for (const id of ['close-help', 'got-it']) el(id).addEventListener('click', () => dialog.close());
dialog.addEventListener('click', event => { if (event.target === dialog) { const rect = dialog.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close(); } });
async function restoreWorld() {
  if (pending?.operationId) { await pollOperation(); return; }
  if (pending) {
    showError('A previous generation request has an unknown status. Check your World Labs account for its result before starting another paid generation. This page will not submit the photo again.');
    setStatus('Previous request status unknown · Check World Labs');
    updateControls();
    return;
  }
  const saved = readSaved<World>(WORLD_KEY);
  if (!saved || (!saved.worldId && !saved.worldUrl && !saved.splatUrl)) return;
  try {
    let world = saved;
    if (saved.worldId) { const response = await fetch(`/api/worlds/${encodeURIComponent(saved.worldId)}`); if (response.ok) world = { ...saved, ...await response.json(), name: saved.name }; }
    if (!file && !isWorking && !pending) await displayWorld(world);
  } catch { showError('The last scene couldn’t be restored. Check your World Labs account to reopen it. No generation was submitted.'); }
}
void (async () => { await checkProvider(); await restoreWorld(); })();
window.addEventListener('beforeunload', () => { pollController?.abort(); viewer?.dispose(); if (previewUrl) URL.revokeObjectURL(previewUrl); if (importUrl) URL.revokeObjectURL(importUrl); });
