import './style.css';
import Viewer from './viewer';

const icons: Record<string, string> = {
  cube: '<path d="m12 3 9 5v8l-9 5-9-5V8l9-5Z"/><path d="m3 8 9 5 9-5M12 13v8M7.5 5.5l9 5"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
  arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m21 15-6-6-12 12"/>',
  check: '<path d="m5 12 4 4L19 6"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
  walk: '<circle cx="14" cy="4" r="2"/><path d="m7 21 4-7 3 3v5M6 12l3-4 4 1 3 4h4M11 9v6"/>',
  orbit: '<ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(-30 12 12)"/><circle cx="12" cy="12" r="2"/>',
  reset: '<path d="M3 10a9 9 0 1 1 1 7M3 4v6h6"/>',
  expand: '<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',
  grid: '<path d="M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z"/>',
  layers: '<path d="m12 3 10 5-10 5L2 8l10-5ZM2 12l10 5 10-5M2 16l10 5 10-5"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1 1m12 12 1 1M5 19l1-1M18 6l1-1"/>',
};
function icon(name: string, cls = '') { return `<svg class="icon ${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${icons[name] || icons.cube}</svg>`; }

document.querySelector<HTMLDivElement>('#app')!.innerHTML = `
  <header class="topbar">
    <a class="brand" href="/" aria-label="Titan Space Studio home"><span class="brand-mark">T</span><span class="brand-word">TITAN<span>GARAGE STORAGE</span></span></a>
    <span class="brand-divider"></span><span class="studio-name">Space Studio <span class="beta">LAB</span></span>
    <button class="help-button" id="help">${icon('info')} <span>How it works</span></button>
  </header>
  <main>
    <section class="page-heading"><div><div class="eyebrow"><span></span> A NEW WAY TO SEE YOUR SPACE</div><h1>Your space. A new perspective.</h1><p>Turn a photo into a place you can explore.</p></div><span class="private-badge">${icon('layers')} Photo to 3D experiment</span></section>
    <section class="workspace" aria-label="3D workspace">
      <aside class="sidebar">
        <div class="sidebar-heading"><span class="section-number">01</span><h2>Start with your space</h2></div>
        <p class="sidebar-description">A garage. A showroom. Your next project.<br>See what a different perspective reveals.</p>
        <input id="photo-input" type="file" accept="image/jpeg,image/png,image/webp" hidden />
        <button class="upload-zone" id="upload-zone"><span class="upload-icon">${icon('upload')}</span><strong>Drop your photo here</strong><span>or <u>browse files</u></span><small>JPG, PNG or WebP · Up to 15 MB</small></button>
        <div id="photo-card" class="photo-card" hidden><img id="photo-preview" alt="Your selected space" /><div><strong id="photo-name"></strong><span id="photo-size"></span></div><button id="remove-photo" class="icon-button" aria-label="Remove selected photo">${icon('close')}</button></div>
        <button id="generate" class="primary-button" disabled>${icon('cube')} <span>Create 3D view</span>${icon('arrow')}</button>
        <div id="processing" class="processing" role="status" hidden><span class="spinner"></span><span>Estimating depth. This can take a moment.</span></div>
        <p id="upload-error" class="error-message" role="alert" hidden></p>
        <div class="tip">${icon('sun')}<p><strong>A little light goes a long way.</strong><br>Use a wide, well-lit photo with the floor and walls in view.</p></div>
        <div class="sidebar-divider"><span>OR GET A FEEL FOR IT</span></div>
        <button id="example" class="example-card selected"><span class="example-art"><span class="art-roof"></span><span class="art-column"></span><span class="art-car"></span><span class="art-car two"></span></span><span class="example-copy"><strong>Covered showroom</strong><small>Walk through the sample</small></span><span class="example-check">${icon('check')}</span></button>
        <span class="sample-disclaimer">Hand-built 3D sample · No photo needed</span>
        <div class="expectation-card">${icon('info')}<div><strong>A starting point, not a survey.</strong><p>One photo captures one viewpoint. AI estimates visible depth; hidden areas and real measurements aren’t captured.</p></div></div>
      </aside>
      <div class="viewer-panel">
        <div class="viewer-topbar"><div class="viewer-title">${icon('cube')}<strong id="scene-name">Covered showroom</strong><span id="scene-badge" class="scene-badge">SAMPLE SPACE</span></div><button id="fullscreen" class="icon-button" aria-label="Toggle full screen">${icon('expand')}</button></div>
        <div class="canvas-wrap" id="canvas-wrap"><div id="viewer"></div>
          <div class="view-status"><span></span><span id="view-status">Interactive 3D scene</span></div>
          <div class="view-label" id="view-label">A little room to imagine.</div>
          <div class="viewer-hint" id="viewer-hint">${icon('orbit')} Drag to look around <span>·</span> Scroll to move closer</div>
          <div id="scene-error" class="scene-error" hidden></div>
          <div class="direction-pad" id="direction-pad" hidden><button data-move="forward" aria-label="Move forward">↑</button><button data-move="left" aria-label="Move left">←</button><button data-move="backward" aria-label="Move backward">↓</button><button data-move="right" aria-label="Move right">→</button></div>
          <div class="compass"><span>N</span><svg viewBox="0 0 36 36" aria-hidden="true"><circle cx="18" cy="18" r="16"/><path d="m18 8 5 15-5-3-5 3Z"/></svg></div>
        </div>
        <div class="viewer-toolbar"><div class="mode-toggle" role="group" aria-label="Camera mode"><button id="orbit-mode" class="active" aria-pressed="true">${icon('orbit')} Orbit</button><button id="walk-mode" aria-pressed="false">${icon('walk')} Walk through</button></div><div class="toolbar-right"><button id="point-cloud" class="toolbar-button" aria-pressed="false" title="Upload a photo to explore its point cloud" disabled>${icon('grid')}<span>Point cloud</span></button><span class="toolbar-divider"></span><button id="reset" class="toolbar-button">${icon('reset')}<span>Reset view</span></button></div></div>
      </div>
    </section>
    <section class="workflow" aria-label="How it works"><div><span>01</span><p><strong>Bring your space</strong>Upload a photo you want to explore.</p></div>${icon('chevron')}<div><span>02</span><p><strong>Find a new dimension</strong>AI estimates depth from your image.</p></div>${icon('chevron')}<div><span>03</span><p><strong>Take a look around</strong>Move through the visible 3D surfaces.</p></div></section>
  </main>
  <footer><span>Built for the spaces with potential.</span><span>TITAN GARAGE STORAGE <span class="footer-dot">·</span> SPACE STUDIO</span></footer>
  <dialog id="help-dialog"><button id="close-help" class="icon-button dialog-close" aria-label="Close help">${icon('close')}</button><span class="eyebrow">THE FIRST EXPERIMENT</span><h2>A photo. A little depth.<br>A different perspective.</h2><p>Choose a photo and select <strong>Create 3D view</strong>. A depth estimation model runs on this development server, and your photo is projected onto a 3D surface in your browser.</p><p>Try <strong>Orbit</strong> to drag around the scene, or <strong>Walk through</strong> to look around and move with W, A, S, D or the arrow keys. Press Escape to release the mouse.</p><div class="help-note"><strong>What one photo can tell us</strong><p>This is an experimental depth reconstruction. It captures the surfaces visible in your photo. Looking behind objects reveals missing information; scale and hidden rooms cannot be recovered reliably. For an accurate full walkthrough, we’ll need overlapping photos, video or a spatial scan.</p></div><p class="help-privacy">Photos are processed by this development server and aren’t saved by the application. The sample is a separately modeled 3D scene.</p><button id="got-it" class="primary-button">Let’s explore ${icon('arrow')}</button></dialog>
`;

const el = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
let viewer: Viewer | null = null;
try {
  viewer = new Viewer(el('viewer'), message => { el('view-status').textContent = message; });
} catch (error) {
  el('scene-error').hidden = false;
  el('scene-error').textContent = 'The 3D viewer needs WebGL. Try a browser with hardware acceleration enabled.';
  console.error(error);
}
let file: File | null = null;
let previewUrl: string | null = null;
let isWorking = false;
let request: AbortController | null = null;
let cloud = false;

function showError(message: string) { el('upload-error').textContent = message; el('upload-error').hidden = false; }
function selectFile(selected?: File) {
  if (!selected || isWorking) return;
  el('upload-error').hidden = true;
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(selected.type)) { showError('Choose a JPG, PNG or WebP image.'); return; }
  if (selected.size > 15 * 1024 * 1024) { showError('This photo is over 15 MB. Choose a smaller image.'); return; }
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  file = selected;
  previewUrl = URL.createObjectURL(file);
  el<HTMLImageElement>('photo-preview').src = previewUrl;
  el('photo-name').textContent = file.name;
  el('photo-size').textContent = `${(file.size / 1024 / 1024).toFixed(1)} MB · Ready to create`;
  el('photo-card').hidden = false;
  el<HTMLButtonElement>('generate').disabled = !viewer;
  el('upload-zone').classList.add('compact');
}
el('upload-zone').addEventListener('click', () => el<HTMLInputElement>('photo-input').click());
el<HTMLInputElement>('photo-input').addEventListener('change', event => selectFile((event.target as HTMLInputElement).files?.[0]));
for (const type of ['dragenter', 'dragover']) el('upload-zone').addEventListener(type, event => { event.preventDefault(); el('upload-zone').classList.add('dragging'); });
for (const type of ['dragleave', 'drop']) el('upload-zone').addEventListener(type, event => { event.preventDefault(); el('upload-zone').classList.remove('dragging'); });
el('upload-zone').addEventListener('drop', event => selectFile((event as DragEvent).dataTransfer?.files?.[0]));
el('remove-photo').addEventListener('click', () => {
  if (isWorking) return;
  file = null;
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = null;
  el<HTMLInputElement>('photo-input').value = '';
  el('photo-card').hidden = true;
  el<HTMLButtonElement>('generate').disabled = true;
  el('upload-zone').classList.remove('compact');
});
function loadImage(src: string): Promise<HTMLImageElement> { return new Promise((resolve, reject) => { const img = new Image(); img.onload = () => resolve(img); img.onerror = () => reject(new Error('The image could not be decoded. Choose another photo.')); img.src = src; }); }
el('generate').addEventListener('click', async () => {
  if (!file || !previewUrl || !viewer || isWorking) return;
  const selectedFile = file;
  const selectedUrl = previewUrl;
  isWorking = true;
  el<HTMLButtonElement>('generate').disabled = true;
  el('processing').hidden = false;
  el('upload-error').hidden = true;
  el('generate').querySelector('span')!.textContent = 'Creating your view…';
  request = new AbortController();
  const timeout = window.setTimeout(() => request?.abort(), 180_000);
  try {
    const photo = await loadImage(selectedUrl);
    if (photo.width < 128 || photo.height < 128) throw new Error('Use a photo at least 128 × 128 pixels.');
    const form = new FormData();
    form.append('photo', selectedFile);
    const response = await fetch('/api/depth', { method: 'POST', body: form, signal: request.signal });
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      throw new Error(typeof data?.detail === 'string' ? data.detail : 'Depth processing is unavailable. Make sure the Python backend is running, then try again.');
    }
    const result = await response.json();
    if (!result.depth) throw new Error('The depth service returned an incomplete image. Please try again.');
    const depth = await loadImage(result.depth.startsWith('data:') ? result.depth : `data:image/png;base64,${result.depth}`);
    viewer.loadPhoto(photo, depth);
    el('scene-name').textContent = selectedFile.name.replace(/\.[^.]+$/, '');
    el('scene-badge').textContent = 'ESTIMATED DEPTH';
    el('scene-badge').classList.add('estimated');
    el('view-label').hidden = true;
    el('example').classList.remove('selected');
    el('photo-size').textContent = 'Depth generated · Visible surfaces only';
    cloud = false;
    el<HTMLButtonElement>('point-cloud').disabled = false;
    el('point-cloud').title = 'Toggle point cloud';
    el('point-cloud').setAttribute('aria-pressed', 'false');
    el('point-cloud').classList.remove('active');
    setMode('orbit');
    if (window.innerWidth <= 760) el('canvas-wrap').scrollIntoView({ behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'center' });
  } catch (error) {
    showError(error instanceof Error && error.name === 'AbortError' ? 'Processing timed out. Try a smaller photo or check that the depth server is running.' : error instanceof Error ? error.message : 'Something went wrong. Please try again.');
  } finally {
    clearTimeout(timeout);
    request = null;
    isWorking = false;
    el('processing').hidden = true;
    el<HTMLButtonElement>('generate').disabled = !file || !viewer;
    el('generate').querySelector('span')!.textContent = 'Create 3D view';
  }
});
function setMode(mode: 'walk' | 'orbit') {
  viewer?.setMode(mode);
  for (const item of ['walk', 'orbit']) { el(`${item}-mode`).classList.toggle('active', item === mode); el(`${item}-mode`).setAttribute('aria-pressed', String(item === mode)); }
  const touchHint = window.matchMedia('(pointer: coarse)').matches || window.innerWidth <= 760;
  el('viewer-hint').innerHTML = mode === 'walk' ? touchHint ? `${icon('walk')} Drag to look <span>·</span> Hold arrows to move` : `${icon('walk')} Click scene to look <span>·</span> WASD / arrows to move <span>·</span> Esc to release` : `${icon('orbit')} Drag to look around <span>·</span> Scroll to move closer`;
  el('view-label').hidden = mode === 'walk' || el('scene-badge').textContent === 'ESTIMATED DEPTH';
  el('direction-pad').hidden = mode !== 'walk';
}
el('walk-mode').addEventListener('click', () => setMode('walk'));
el('orbit-mode').addEventListener('click', () => setMode('orbit'));
el('reset').addEventListener('click', () => viewer?.reset());
el('example').addEventListener('click', () => {
  if (isWorking) return;
  viewer?.showExample();
  el('scene-name').textContent = 'Covered showroom';
  el('scene-badge').textContent = 'SAMPLE SPACE';
  el('scene-badge').classList.remove('estimated');
  el('view-label').hidden = false;
  el('example').classList.add('selected');
  cloud = false;
  el<HTMLButtonElement>('point-cloud').disabled = true;
  el('point-cloud').title = 'Upload a photo to explore its point cloud';
  el('point-cloud').setAttribute('aria-pressed', 'false');
  el('point-cloud').classList.remove('active');
  setMode('orbit');
});
el('point-cloud').addEventListener('click', () => { cloud = !cloud; viewer?.setPointCloud(cloud); el('point-cloud').setAttribute('aria-pressed', String(cloud)); el('point-cloud').classList.toggle('active', cloud); });
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
window.addEventListener('beforeunload', () => { request?.abort(); viewer?.dispose(); if (previewUrl) URL.revokeObjectURL(previewUrl); });
