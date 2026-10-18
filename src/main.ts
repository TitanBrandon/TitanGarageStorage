import './style.css';
import Viewer, { type SceneDescriptor } from './viewer';

const paths: Record<string, string> = {
  cube: '<path d="m12 3 9 5v8l-9 5-9-5V8l9-5Z"/><path d="m3 8 9 5 9-5M12 13v8"/>',
  upload: '<path d="M12 16V3m-5 5 5-5 5 5M4 16v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
  arrow: '<path d="M5 12h14m-5-5 5 5-5 5"/>',
  image: '<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m21 15-6-6-12 12"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7h.01"/>',
  walk: '<circle cx="14" cy="4" r="2"/><path d="m7 21 4-7 3 3v5M6 12l3-4 4 1 3 4h4M11 9v6"/>',
  orbit: '<ellipse cx="12" cy="12" rx="10" ry="4" transform="rotate(-30 12 12)"/><circle cx="12" cy="12" r="2"/>',
  reset: '<path d="M3 10a9 9 0 1 1 1 7M3 4v6h6"/>',
  expand: '<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',
  close: '<path d="m6 6 12 12M6 18 18 6"/>',
  chevron: '<path d="m9 5 7 7-7 7"/>',
  external: '<path d="M14 3h7v7m0-7L10 14M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5"/>',
  download: '<path d="M12 3v12m-5-5 5 5 5-5M4 17v4h16v-4"/>',
};
const icon = (name: string) => `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${paths[name] || paths.cube}</svg>`;
document.querySelector<HTMLDivElement>('#app')!.innerHTML = `
<header class="topbar"><a class="brand" href="/" aria-label="Titan Space Studio home"><span class="brand-mark">T</span><span class="brand-word">TITAN<span>GARAGE STORAGE</span></span></a><span class="brand-divider"></span><span class="studio-name">Space Studio <span class="beta">LAB</span></span><button class="help-button" id="help">${icon('info')}<span>How it works</span></button></header>
<main>
  <section class="page-heading"><div><div class="eyebrow"><span></span> A NEW PERSPECTIVE ON YOUR SPACE</div><h1>Walk into your next idea.</h1><p>Upload an interior photo. Reconstruct its visible surfaces in Blender. Explore in 3D.</p></div><span class="private-badge">${icon('cube')} Photo to Blender</span></section>
  <section class="workspace" aria-label="3D reconstruction workspace">
    <aside class="sidebar">
      <div class="sidebar-heading"><span class="section-number">01</span><h2>Start with your space</h2></div>
      <p class="sidebar-description">A garage, a room, your next project.<br>Begin with a clear, wide interior photo.</p>
      <input id="photo-input" type="file" accept="image/jpeg,image/png,image/webp" hidden />
      <button class="upload-zone" id="upload-zone"><span class="upload-icon">${icon('upload')}</span><strong>Drop your photo here</strong><span>or <u>browse files</u></span><small>JPG, PNG or WebP · Up to 15 MB</small></button>
      <div id="photo-card" class="photo-card" hidden><img id="photo-preview" alt="Selected original photo" /><div><strong id="photo-name"></strong><span id="photo-size"></span></div><button id="remove-photo" class="icon-button" aria-label="Remove selected photo">${icon('close')}</button></div>
      <div class="provider-card worker-card" id="worker-card" role="status"><span class="provider-dot"></span><div><strong id="worker-title">Checking reconstruction worker…</strong><p id="worker-description">Connecting to the processing service.</p><a id="worker-setup" href="https://github.com/TitanBrandon/TitanGarageStorage/blob/main/DEPLOY.md" target="_blank" rel="noopener noreferrer" hidden>Worker setup instructions ${icon('external')}</a><button id="worker-refresh" class="text-button">Check connection again</button></div></div>
      <button id="generate" class="primary-button" disabled>${icon('cube')}<span>Create 3D walkthrough</span>${icon('arrow')}</button>
      <p class="local-processing-note">Your photo is processed by the configured reconstruction worker. No paid scene-generation service is used.</p>
      <div id="processing" class="job-progress" role="status" hidden><div class="processing"><span class="spinner"></span><strong id="processing-text">Waiting for the worker</strong></div><progress id="job-progress" max="100" value="0" aria-label="Reconstruction progress"></progress><div class="progress-meta"><span id="stage-label"></span><span id="progress-percent"></span></div></div>
      <button id="cancel-job" class="secondary-button cancel-button" hidden>Cancel reconstruction</button>
      <button id="retry-job" class="secondary-button" hidden>Retry reconstruction</button>
      <p id="error" class="error-message" role="alert" hidden></p>
      <div class="sidebar-divider"><span>YOUR SAVED SPACES</span></div>
      <div class="project-list-heading"><h3>Projects</h3><button id="refresh-projects" class="text-button">Refresh</button></div>
      <div id="project-list" class="project-list" aria-label="Saved projects"><p class="project-placeholder">Loading saved projects…</p></div>
      <div class="expectation-card">${icon('info')}<div><strong>A reconstruction, with room to refine.</strong><p>One photo can’t establish exact dimensions or hidden details. Review the source comparison and confidence notes, then adjust the model if needed.</p></div></div>
    </aside>
    <div class="viewer-panel">
      <div class="viewer-topbar"><div class="viewer-title">${icon('cube')}<strong id="scene-name">Your next perspective</strong><span id="scene-badge" class="scene-badge">PHOTO TO BLENDER</span></div><button id="fullscreen" class="icon-button" aria-label="Toggle full screen">${icon('expand')}</button></div>
      <div class="canvas-wrap" id="canvas-wrap"><div id="viewer"></div><img id="original-photo" class="original-photo" alt="Your original uploaded photo" hidden />
        <div id="empty-state" class="empty-state"><span class="empty-symbol">${icon('cube')}</span><span class="eyebrow">BUILT FROM YOUR POINT OF VIEW</span><h2>Bring your space to life.</h2><p>Start with a garage or interior photo.<br>Your original image will appear here first.</p><button id="empty-upload" class="secondary-button">${icon('upload')} Choose a photo</button><span class="empty-rule"></span><small>Actual room meshes. A perspective you can explore.</small></div>
        <div id="compare-original" class="compare-original" hidden><img id="comparison-photo" alt="Original reference photo for comparison"/><span>Original photo</span></div>
        <img id="blender-preview" class="blender-preview" alt="Source-camera preview rendered by Blender" hidden />
        <span id="compare-model-label" class="compare-model-label" hidden>Reconstructed source view</span>
        <div class="view-status"><span></span><span id="view-status">Waiting for your photo</span></div>
        <div id="original-label" class="original-label" hidden>${icon('image')} Original photo <span>Reconstruction has not finished</span></div>
        <div id="viewer-hint" class="viewer-hint" hidden></div><div id="scene-error" class="scene-error" role="alert" hidden></div>
        <div class="direction-pad" id="direction-pad" hidden><button data-move="forward" aria-label="Move forward">↑</button><button data-move="left" aria-label="Move left">←</button><button data-move="backward" aria-label="Move backward">↓</button><button data-move="right" aria-label="Move right">→</button></div>
      </div>
      <div class="viewer-toolbar"><div class="mode-toggle" role="group" aria-label="Camera mode"><button id="orbit-mode" class="active" aria-pressed="true" disabled>${icon('orbit')} Orbit</button><button id="walk-mode" aria-pressed="false" disabled>${icon('walk')} Walk through</button><button id="source-mode" aria-pressed="false" disabled>${icon('image')} Compare photo</button></div><div class="toolbar-right"><button id="preview-toggle" class="toolbar-button" aria-pressed="false" hidden>Blender preview</button><button id="reset" class="toolbar-button" disabled>${icon('reset')}<span>Reset view</span></button></div></div>
      <p class="scene-disclaimer" id="scene-disclaimer">Your uploaded photo drives the reconstruction. Unseen areas remain estimates.</p>
      <div id="downloads" class="downloads" hidden><span>Keep working on your space</span><a id="download-glb" download>${icon('download')} Download GLB</a><a id="download-blend" download>${icon('download')} Blender project</a><a id="download-scene" download>${icon('download')} Scene JSON</a><a id="download-preview" download hidden>${icon('image')} Preview render</a></div>
    </div>
  </section>
  <section id="project-details" class="project-details" hidden>
    <div class="project-notes"><div class="sidebar-heading"><span class="section-number">02</span><h2>Check the reconstruction</h2></div><p class="detail-description">Compare the generated source view with your photo. These notes identify estimates and unsupported details.</p><ul id="confidence-notes" class="confidence-notes"></ul><p id="revision-note" class="revision-note"></p></div>
    <details id="corrections-panel" class="corrections-panel"><summary><span>${icon('cube')} Refine this space <small>Optional dimensions & alignment</small></span>${icon('chevron')}</summary><form id="corrections-form"><p class="detail-description">Measurements are optional. Change only what you know, then rebuild the actual Blender scene. Values are in metres; positions use X (left/right), Y (height), Z (front/back), with the room centre at zero.</p>
      <fieldset><legend>Room dimensions</legend><div class="form-grid"><label>Width<input id="room-width" type="number" min="1" max="50" step="0.1" /></label><label>Depth<input id="room-depth" type="number" min="1" max="50" step="0.1" /></label><label>Height<input id="room-height" type="number" min="1.8" max="12" step="0.1" /></label></div></fieldset>
      <fieldset><legend>Source camera alignment</legend><div class="form-grid"><label>Field of view (°)<input id="camera-fov" type="number" min="20" max="120" step="0.1" /></label><label>Pitch (°)<input id="camera-pitch" type="number" min="-60" max="60" step="0.1" /></label></div><div class="form-grid"><label>Camera X<input id="camera-x" type="number" min="-100" max="100" step="0.1" /></label><label>Camera Y<input id="camera-y" type="number" min="-100" max="100" step="0.1" /></label><label>Camera Z<input id="camera-z" type="number" min="-100" max="100" step="0.1" /></label></div></fieldset>
      <fieldset><legend>Wall corners</legend><label class="wide-label">Floor-plan corners [X, Z]<textarea id="wall-corners" rows="3" spellcheck="false" placeholder="Leave blank to keep the inferred walls"></textarea></label><p class="field-help">A list such as [[-3,-4],[3,-4],[3,4],[-3,4]]. Keep the existing number of corners and a convex perimeter.</p></fieldset>
      <fieldset><legend>Major objects</legend><p class="field-help">Adjust supported cabinets, shelving and other reconstructed objects. Positions refer to each object’s centre.</p><div id="object-corrections"></div></fieldset>
      <p id="corrections-error" class="error-message" role="alert" hidden></p><button id="corrections-submit" class="primary-button" type="submit">${icon('cube')} Rebuild with corrections ${icon('arrow')}</button><p class="field-help">The previous completed model remains available while the new revision is processed.</p>
    </form></details>
  </section>
  <section class="workflow" aria-label="How reconstruction works"><div><span>01</span><p><strong>Bring a real photo</strong>Perspective, depth and visible regions are analyzed.</p></div>${icon('chevron')}<div><span>02</span><p><strong>Build the space in Blender</strong>Room surfaces, supported objects and materials become meshes.</p></div>${icon('chevron')}<div><span>03</span><p><strong>Walk through and refine</strong>Compare the source, explore, and correct the estimates.</p></div></section>
</main>
<footer><span>Built for the spaces with potential.</span><span>TITAN GARAGE STORAGE <span class="footer-dot">·</span> SPACE STUDIO</span></footer>
<dialog id="help-dialog"><button id="close-help" class="icon-button dialog-close" aria-label="Close help">${icon('close')}</button><span class="eyebrow">FROM PHOTO TO BLENDER</span><h2>Your space.<br>A new perspective.</h2><p>Choose a well-lit garage or interior photo, then select <strong>Create 3D walkthrough</strong>. The reconstruction worker estimates perspective and depth, separates supported surfaces and objects, then uses Blender to build an editable scene and a textured browser model.</p><p>Use <strong>Compare photo</strong> to inspect the original beside the matched source camera. Use <strong>Walk through</strong> to look around and move with W, A, S, D or arrow keys. On touch screens, drag to look and hold the directional buttons. Press Escape to release the mouse.</p><div class="help-note"><strong>One photo leaves unknowns.</strong><p>Hidden surfaces, exact dimensions and some objects cannot be established from one view. Confidence notes describe the limits of each reconstruction. Unsupported photos fail visibly instead of being replaced with a sample room. Optional corrections can improve the room shape, camera alignment and supported objects.</p></div><p class="help-privacy">Your projects and generated files are stored by your configured reconstruction worker. Reloading reconnects to the saved job. Cancellation requests stop the worker job; closing the browser leaves it running. No paid scene-generation API is required.</p><button id="got-it" class="primary-button">Let’s explore ${icon('arrow')}</button></dialog>
`;

const el = <T extends HTMLElement = HTMLElement>(id: string) => document.getElementById(id) as T;
type State = 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
type Summary = { id: string; name: string; state: State; stage: string; progress: number; revision: number; completedRevision?: number; error?: string };
type Project = Summary & { warnings?: unknown[]; scene?: SceneDescriptor; corrections?: Record<string, unknown>; artifacts: { source?: string; glb?: string; blend?: string; scene?: string; preview?: string } };
type Mode = 'walk' | 'orbit' | 'source';
const SELECTED_KEY = 'titan.projects.selected.v1';
let viewer: Viewer | null = null;
let file: File | null = null;
let photoUrl: string | null = null;
let project: Project | null = null;
let projects: Summary[] = [];
let workerReady = false;
let requestBusy = false;
let modelLoaded = false;
let selectedId: string | null = null;
let epoch = 0;
let pollTimer: number | null = null;
let loadedModel = '';
let currentMode: Mode = 'orbit';
let previewMode = false;
let cancelRequested = false;
try { selectedId = localStorage.getItem(SELECTED_KEY); } catch { /* Server projects remain available without browser storage. */ }
const active = (item: Summary | null) => item?.state === 'queued' || item?.state === 'running';
const status = (message: string) => { el('view-status').textContent = message; };
function error(message: string) { el('error').textContent = message; el('error').hidden = false; }
function asset(value?: string): string | null { try { if (!value) return null; const url = new URL(value, location.origin); return url.origin === location.origin && /^https?:$/.test(url.protocol) ? url.href : null; } catch { return null; } }
function remember(id: string | null) { try { if (id) localStorage.setItem(SELECTED_KEY, id); else localStorage.removeItem(SELECTED_KEY); } catch { /* Projects are persisted on the server. */ } }
async function api<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { credentials: 'same-origin', ...init });
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new Error(typeof body?.detail === 'string' ? body.detail : `The server could not complete this request (${response.status}).`);
  return body as T;
}
try { viewer = new Viewer(el('viewer'), status); viewer.showEmpty(); }
catch { error('The 3D viewer needs hardware acceleration. Enable it in your browser, then reload. Projects and downloads are still available.'); }
status('Waiting for your photo');

function controls() {
  const running = active(project);
  const locked = requestBusy || running;
  for (const id of ['upload-zone', 'empty-upload', 'remove-photo']) el<HTMLButtonElement>(id).disabled = locked;
  el<HTMLInputElement>('photo-input').disabled = locked;
  el<HTMLButtonElement>('generate').disabled = !file || !workerReady || locked;
  el('generate').querySelector('span')!.textContent = requestBusy ? 'Sending your photo…' : 'Create 3D walkthrough';
  el('processing').hidden = !running && !requestBusy;
  el('cancel-job').hidden = !running;
  el<HTMLButtonElement>('cancel-job').disabled = requestBusy || cancelRequested;
  el('cancel-job').textContent = cancelRequested ? 'Cancellation requested…' : 'Cancel reconstruction';
  el('retry-job').hidden = !project || !['failed', 'cancelled'].includes(project.state);
  el<HTMLButtonElement>('retry-job').disabled = locked || !workerReady;
  for (const id of ['orbit-mode', 'walk-mode', 'source-mode', 'reset']) el<HTMLButtonElement>(id).disabled = !modelLoaded;
  el<HTMLButtonElement>('corrections-submit').disabled = locked || !project || !workerReady;
  el<HTMLFieldSetElement>('corrections-form')?.querySelectorAll<HTMLInputElement | HTMLTextAreaElement>('input, textarea').forEach(input => { input.disabled = locked; });
}
async function workerStatus() {
  el<HTMLButtonElement>('worker-refresh').disabled = true;
  try {
    const data = await api<{ configured: boolean; workerReachable?: boolean; setupRequired?: boolean; message?: string }>('/api/projects/status');
    workerReady = data.configured && data.workerReachable !== false && !data.setupRequired;
    el('worker-card').classList.toggle('connected', workerReady);
    el('worker-title').textContent = workerReady ? 'Reconstruction worker ready' : data.setupRequired || !data.configured ? 'Reconstruction worker needed' : 'Reconstruction worker unavailable';
    el('worker-description').textContent = data.message || (workerReady ? 'Blender and image analysis run on your configured worker.' : 'Connect a Blender worker with the reconstruction models and durable storage to create walkthroughs.');
    el('worker-setup').hidden = workerReady;
  } catch (cause) {
    workerReady = false;
    el('worker-card').classList.remove('connected');
    el('worker-title').textContent = 'Server connection unavailable';
    el('worker-description').textContent = cause instanceof Error ? cause.message : 'Check the server connection and try again.';
    el('worker-setup').hidden = false;
  } finally { el<HTMLButtonElement>('worker-refresh').disabled = false; controls(); }
}
el('worker-refresh').addEventListener('click', workerStatus);

function clearModel() {
  modelLoaded = false;
  loadedModel = '';
  previewMode = false;
  viewer?.showEmpty();
  el('viewer').classList.remove('world-ready');
  el('canvas-wrap').classList.remove('comparing');
  for (const id of ['viewer-hint', 'direction-pad', 'compare-original', 'compare-model-label', 'blender-preview', 'scene-error', 'preview-toggle', 'downloads']) el(id).hidden = true;
}
function displayPhoto(url: string | null) {
  el('original-photo').hidden = !url;
  el('original-label').hidden = !url;
  el('empty-state').hidden = !!url;
  if (url) { el<HTMLImageElement>('original-photo').src = url; el<HTMLImageElement>('comparison-photo').src = url; }
}
function selectPhoto(selected?: File) {
  if (!selected || requestBusy || active(project)) return;
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(selected.type)) { error('Choose a JPG, PNG or WebP image.'); return; }
  if (!selected.size || selected.size > 15 * 1024 * 1024) { error('Choose a non-empty photo no larger than 15 MB.'); return; }
  epoch++;
  if (pollTimer) clearTimeout(pollTimer);
  project = null; selectedId = null; remember(null);
  if (photoUrl) URL.revokeObjectURL(photoUrl);
  file = selected; photoUrl = URL.createObjectURL(selected);
  clearModel(); displayPhoto(photoUrl);
  el<HTMLImageElement>('photo-preview').src = photoUrl;
  el('photo-name').textContent = selected.name;
  el('photo-size').textContent = `${(selected.size / 1024 / 1024).toFixed(1)} MB · Ready to reconstruct`;
  el('photo-card').hidden = false;
  el('upload-zone').classList.add('compact');
  el('scene-name').textContent = selected.name.replace(/\.[^.]+$/, '');
  el('scene-badge').textContent = 'ORIGINAL PHOTO';
  el('project-details').hidden = true;
  el('error').hidden = true;
  status('Original photo · Ready to reconstruct');
  renderProjects(); controls();
}
for (const id of ['upload-zone', 'empty-upload']) el(id).addEventListener('click', () => el<HTMLInputElement>('photo-input').click());
el<HTMLInputElement>('photo-input').addEventListener('change', event => selectPhoto((event.target as HTMLInputElement).files?.[0]));
for (const type of ['dragenter', 'dragover']) el('upload-zone').addEventListener(type, event => { event.preventDefault(); if (!requestBusy && !active(project)) el('upload-zone').classList.add('dragging'); });
for (const type of ['dragleave', 'drop']) el('upload-zone').addEventListener(type, event => { event.preventDefault(); el('upload-zone').classList.remove('dragging'); });
el('upload-zone').addEventListener('drop', event => selectPhoto((event as DragEvent).dataTransfer?.files?.[0]));
el('remove-photo').addEventListener('click', () => {
  if (requestBusy || active(project)) return;
  file = null; if (photoUrl) URL.revokeObjectURL(photoUrl); photoUrl = null;
  el<HTMLInputElement>('photo-input').value = ''; el('photo-card').hidden = true; el('upload-zone').classList.remove('compact');
  clearModel(); displayPhoto(null); status('Waiting for your photo'); controls();
});

function renderProjects() {
  const list = el('project-list'); list.replaceChildren();
  if (!projects.length) { const message = document.createElement('p'); message.className = 'project-placeholder'; message.textContent = 'Your saved spaces will appear here.'; list.append(message); return; }
  for (const item of projects) {
    const button = document.createElement('button'); button.className = `project-item${item.id === selectedId ? ' selected' : ''}`; button.dataset.projectId = item.id;
    const mark = document.createElement('span'); mark.className = `project-mark ${item.state}`; mark.innerHTML = icon('cube');
    const copy = document.createElement('span'); const title = document.createElement('strong'); title.textContent = item.name || 'Untitled space'; const sub = document.createElement('small'); sub.textContent = `${item.state === 'completed' ? 'Ready to explore' : item.state[0].toUpperCase() + item.state.slice(1)} · Revision ${item.revision || 1}`; copy.append(title, sub); button.append(mark, copy); button.disabled = requestBusy; button.addEventListener('click', () => { void openProject(item.id); }); list.append(button);
  }
}
async function refreshProjects() {
  el<HTMLButtonElement>('refresh-projects').disabled = true;
  try { const result = await api<{ projects: Summary[] }>('/api/projects'); projects = Array.isArray(result.projects) ? result.projects : []; renderProjects(); }
  catch (cause) { error(cause instanceof Error ? cause.message : 'Saved projects could not be loaded.'); }
  finally { el<HTMLButtonElement>('refresh-projects').disabled = false; }
}
el('refresh-projects').addEventListener('click', refreshProjects);
const stageNames: Record<string, string> = { queued: 'Waiting for an available worker', analyzing: 'Analyzing perspective, depth and surfaces', reconstructing: 'Reconstructing the room and objects', building: 'Building the Blender scene', building_geometry: 'Building the room and object meshes in Blender', rendering: 'Rendering the source-camera preview', rendering_preview: 'Rendering the source-camera preview in Blender', exporting: 'Preparing the textured GLB', exporting_glb: 'Exporting the textured GLB from Blender', validating: 'Validating the model and output files', completed: 'Reconstruction complete', failed: 'Reconstruction failed', cancelled: 'Reconstruction cancelled' };
function progress(item: Project) {
  const value = Math.max(0, Math.min(100, Number(item.progress) || 0));
  el<HTMLProgressElement>('job-progress').value = value;
  el('progress-percent').textContent = `${Math.round(value)}%`;
  el('stage-label').textContent = item.stage || item.state;
  el('processing-text').textContent = stageNames[item.stage] || 'Processing your reconstruction';
  if (active(item)) status(stageNames[item.stage] || 'Reconstruction is processing');
}
function notes(item: Project) {
  el('project-details').hidden = false;
  const list = el('confidence-notes'); list.replaceChildren();
  const warnings = item.warnings || [];
  if (!warnings.length) { const li = document.createElement('li'); li.textContent = 'Dimensions and unseen surfaces are estimates from one photograph. Compare the source view before relying on placement or scale.'; list.append(li); }
  for (const warning of warnings) { const li = document.createElement('li'); li.textContent = typeof warning === 'string' ? warning : warning && typeof warning === 'object' && 'message' in warning ? String(warning.message) : JSON.stringify(warning); list.append(li); }
  el('revision-note').textContent = `Revision ${item.revision || 1}${item.completedRevision ? ` · Last completed: ${item.completedRevision}` : ''}${active(item) && item.completedRevision ? ' · The previous completed model remains available during this rebuild.' : ''}`;
}
function setDownload(id: string, value?: string) { const link = el<HTMLAnchorElement>(id); const url = asset(value); link.hidden = !url; if (url) link.href = url; else link.removeAttribute('href'); }
async function showModel(item: Project, token: number) {
  const glb = asset(item.artifacts?.glb);
  if (!glb) return;
  const key = `${item.id}:${item.completedRevision || item.revision}:${glb}`;
  if (key === loadedModel) return;
  let scene = item.scene;
  if (!scene && asset(item.artifacts.scene)) scene = await api<SceneDescriptor>(asset(item.artifacts.scene)!);
  if (token !== epoch) return;
  if (!scene) throw new Error('The model has no scene description for camera alignment and collision. Rebuild this project to create a valid scene.');
  item.scene = scene;
  fillCorrections(scene);
  if (!viewer) { error('The model is ready to download, but this browser cannot display 3D. Enable hardware acceleration and reload.'); return; }
  status('Loading the textured 3D model…');
  await viewer.loadModel(glb, scene);
  if (token !== epoch) return;
  loadedModel = key; modelLoaded = true;
  el('viewer').classList.add('world-ready');
  el('original-photo').hidden = true; el('original-label').hidden = true; el('empty-state').hidden = true; el('scene-error').hidden = true;
  el('viewer-hint').hidden = false;
  el('preview-toggle').hidden = !asset(item.artifacts.preview);
  if (asset(item.artifacts.preview)) el<HTMLImageElement>('blender-preview').src = asset(item.artifacts.preview)!;
  setMode('source');
  if (!active(item)) status(item.state === 'completed' ? 'Reconstructed 3D scene · Ready to explore' : 'Previous completed model available · Latest reconstruction did not complete');
}
async function renderProject(item: Project, token: number) {
  if (token !== epoch) return;
  project = item;
  el('scene-name').textContent = item.name || 'Your reconstructed space';
  el('scene-badge').textContent = active(item) ? 'RECONSTRUCTING' : item.state === 'completed' ? 'BLENDER RECONSTRUCTION' : item.state.toUpperCase();
  const source = asset(item.artifacts?.source);
  if (source) { el<HTMLImageElement>('comparison-photo').src = source; if (!modelLoaded) displayPhoto(source); }
  progress(item); notes(item); controls();
  const index = projects.findIndex(entry => entry.id === item.id); if (index < 0) projects.unshift(item); else projects[index] = item; renderProjects();
  for (const [id, name] of [['download-glb', 'glb'], ['download-blend', 'blend'], ['download-scene', 'scene'], ['download-preview', 'preview']] as const) setDownload(id, item.artifacts?.[name]);
  el('downloads').hidden = !asset(item.artifacts?.glb) && !asset(item.artifacts?.blend);
  if (item.state === 'failed') { error(item.error || 'The worker could not reconstruct this photo. Review the image or optional corrections, then retry. No sample model was substituted.'); status('Reconstruction failed · Review the photo or corrections'); }
  if (item.state === 'cancelled') { status('Reconstruction cancelled'); error('This reconstruction was cancelled. You can retry it or choose another photo.'); }
  try { if (item.completedRevision || item.state === 'completed') await showModel(item, token); }
  catch (cause) { if (token !== epoch) return; const message = cause instanceof Error ? cause.message : 'The generated model could not be displayed.'; el('scene-error').textContent = message; el('scene-error').hidden = false; error(message); }
  controls();
}
async function pollProject(id: string, token: number) {
  if (token !== epoch || id !== selectedId) return;
  try {
    const item = await api<Project>(`/api/projects/${encodeURIComponent(id)}`);
    if (token !== epoch) return;
    await renderProject(item, token);
    if (active(item) && token === epoch) pollTimer = window.setTimeout(() => { void pollProject(id, token); }, 2000);
  } catch (cause) {
    if (token !== epoch) return;
    error(`${cause instanceof Error ? cause.message : 'The project status could not be checked.'} Your job remains on the server. Reopen this project or refresh to reconnect.`);
    if (active(project)) pollTimer = window.setTimeout(() => { void pollProject(id, token); }, 5000);
  }
}
async function openProject(id: string) {
  if (requestBusy) return;
  const token = ++epoch; if (pollTimer) clearTimeout(pollTimer);
  selectedId = id; remember(id); project = null; file = null; cancelRequested = false;
  clearModel(); displayPhoto(null); el('error').hidden = true; el('photo-card').hidden = true; el('upload-zone').classList.remove('compact');
  el<HTMLInputElement>('photo-input').value = ''; el('project-details').hidden = true; status('Opening your saved project…'); renderProjects(); controls();
  await pollProject(id, token);
}
el('generate').addEventListener('click', async () => {
  if (!file || !workerReady || requestBusy || active(project)) return;
  requestBusy = true; el('error').hidden = true; el('processing-text').textContent = 'Uploading your photo…'; controls();
  try {
    const body = new FormData(); body.append('photo', file);
    const result = await api<{ id: string }>('/api/projects', { method: 'POST', body });
    requestBusy = false;
    if (!result.id) throw new Error('The server did not return a project ID. Refresh your project list to check whether the upload was saved.');
    const token = ++epoch; if (pollTimer) clearTimeout(pollTimer);
    selectedId = result.id; remember(result.id); cancelRequested = false;
    file = null; el('photo-size').textContent = 'Uploaded · Project saved on the worker';
    await pollProject(result.id, token);
  } catch (cause) { error(`${cause instanceof Error ? cause.message : 'The upload was interrupted.'} Refresh saved projects before uploading again; the server may already have saved it.`); void refreshProjects(); }
  finally { requestBusy = false; controls(); }
});
el('cancel-job').addEventListener('click', async () => {
  if (!project || !active(project) || requestBusy || cancelRequested) return;
  requestBusy = true; cancelRequested = true; controls();
  try { await api(`/api/projects/${encodeURIComponent(project.id)}/cancel`, { method: 'POST' }); status('Cancellation requested · Waiting for the worker to stop'); }
  catch (cause) { cancelRequested = false; error(cause instanceof Error ? cause.message : 'Cancellation could not be requested.'); }
  finally { requestBusy = false; controls(); }
});

type EditableScene = { room?: { width?: number; depth?: number; height?: number; floor_polygon?: number[][] }; camera?: { fov?: number; position?: number[]; target?: number[] }; objects?: { id?: string; kind?: string; name?: string; position?: number[]; dimensions?: number[] }[] };
let correctionScene: EditableScene | null = null;
let correctionDefaults: Record<string, string> = {};
function inputValue(id: string, value?: number) { el<HTMLInputElement>(id).value = Number.isFinite(value) ? String(Math.round(value! * 1000) / 1000) : ''; }
function fillCorrections(scene: SceneDescriptor) {
  correctionScene = scene as EditableScene;
  const s = correctionScene;
  for (const name of ['width', 'depth', 'height'] as const) inputValue(`room-${name}`, s.room?.[name]);
  inputValue('camera-fov', s.camera?.fov);
  const position = s.camera?.position; const target = s.camera?.target;
  ['x', 'y', 'z'].forEach((axis, i) => inputValue(`camera-${axis}`, position?.[i]));
  if (position && target) inputValue('camera-pitch', Math.atan2(target[1] - position[1], Math.hypot(target[0] - position[0], target[2] - position[2])) * 180 / Math.PI); else inputValue('camera-pitch');
  el<HTMLTextAreaElement>('wall-corners').value = s.room?.floor_polygon ? JSON.stringify(s.room.floor_polygon) : '';
  const list = el('object-corrections'); list.replaceChildren();
  if (!s.objects?.length) { const p = document.createElement('p'); p.className = 'field-help'; p.textContent = 'No supported major objects were reconstructed from this image.'; list.append(p); }
  s.objects?.forEach((object, index) => {
    const row = document.createElement('div'); row.className = 'object-editor'; row.dataset.objectIndex = String(index);
    const heading = document.createElement('strong'); heading.textContent = object.name || `${(object.kind || 'Object').replace(/_/g, ' ')} ${index + 1}`; row.append(heading);
    const grid = document.createElement('div'); grid.className = 'form-grid object-grid';
    for (const [key, label, values] of [['position', 'Position', object.position], ['dimensions', 'Size', object.dimensions]] as const) ['X', 'Y', 'Z'].forEach((axis, axisIndex) => {
      const labelEl = document.createElement('label'); labelEl.textContent = `${label} ${axis}`;
      const input = document.createElement('input'); input.type = 'number'; input.step = 'any'; input.min = key === 'dimensions' ? '0.02' : '-100'; input.max = key === 'dimensions' ? '50' : '100'; input.dataset.objectField = key; input.dataset.axis = String(axisIndex); input.value = String(values?.[axisIndex] ?? (key === 'dimensions' ? 1 : 0)); input.dataset.initialValue = input.value; labelEl.append(input); grid.append(labelEl);
    }); row.append(grid); list.append(row);
  });
  correctionDefaults = {};
  el('corrections-form').querySelectorAll<HTMLInputElement | HTMLTextAreaElement>('input[id], textarea[id]').forEach(input => { if (input instanceof HTMLInputElement) input.step = 'any'; correctionDefaults[input.id] = input.value.trim(); });
}
function number(id: string) { const text = el<HTMLInputElement>(id).value.trim(); if (!text) return undefined; const value = Number(text); if (!Number.isFinite(value)) throw new Error('Use finite numbers for dimensions and alignment.'); return value; }
function getCorrections(): Record<string, unknown> {
  const result: Record<string, unknown> = {};
  const changed = (id: string) => el<HTMLInputElement | HTMLTextAreaElement>(id).value.trim() !== (correctionDefaults[id] || '');
  const room: Record<string, number> = {}; for (const key of ['width', 'depth', 'height']) { const value = number(`room-${key}`); if (value !== undefined && changed(`room-${key}`)) room[key] = value; } if (Object.keys(room).length) result.room = room;
  const camera: Record<string, unknown> = {}; const fov = number('camera-fov'); if (fov !== undefined && changed('camera-fov')) camera.fov = fov;
  const position = ['x', 'y', 'z'].map(axis => number(`camera-${axis}`));
  if (position.every(value => value !== undefined) && ['x', 'y', 'z'].some(axis => changed(`camera-${axis}`))) camera.position = position;
  const pitch = number('camera-pitch');
  if (pitch !== undefined && changed('camera-pitch') && position.every(value => value !== undefined)) {
    const p = position as number[]; const previous = correctionScene?.camera; const target = previous?.target; const from = previous?.position;
    const direction = target && from ? [target[0] - from[0], target[2] - from[2]] : [0, -1]; const horizontal = Math.hypot(...direction) || 1; const radians = pitch * Math.PI / 180;
    camera.target = [p[0] + direction[0] / horizontal * Math.cos(radians) * 5, p[1] + Math.sin(radians) * 5, p[2] + direction[1] / horizontal * Math.cos(radians) * 5];
  }
  if (Object.keys(camera).length) result.camera = camera;
  const corners = el<HTMLTextAreaElement>('wall-corners').value.trim();
  if (corners && changed('wall-corners')) { let parsed: unknown; try { parsed = JSON.parse(corners); } catch { throw new Error('Wall corners must be a valid list of [X, Z] pairs.'); } if (!Array.isArray(parsed) || parsed.length < 3 || !parsed.every(point => Array.isArray(point) && point.length === 2 && point.every(value => typeof value === 'number' && Number.isFinite(value)))) throw new Error('Provide at least three wall corners, each with two finite numbers: [X, Z].'); if (correctionScene?.room?.floor_polygon && parsed.length !== correctionScene.room.floor_polygon.length) throw new Error('Keep the same number of wall corners as the current room.'); result.wall_corners = parsed; }
  const objects: unknown[] = [];
  el('object-corrections').querySelectorAll<HTMLElement>('[data-object-index]').forEach(row => {
    const index = Number(row.dataset.objectIndex); const object = correctionScene?.objects?.[index];
    const item: Record<string, unknown> = { id: object?.id || String(index) };
    let modified = false;
    for (const field of ['position', 'dimensions']) { const inputs = Array.from(row.querySelectorAll<HTMLInputElement>(`[data-object-field="${field}"]`)); const values = inputs.map(input => Number(input.value)); if (values.some(value => !Number.isFinite(value))) throw new Error('Object positions and dimensions must be finite numbers.'); if (inputs.some(input => input.value !== input.dataset.initialValue)) { item[field] = values; modified = true; } } if (modified) objects.push(item);
  }); if (objects.length) result.objects = objects;
  return result;
}
async function rebuild(corrections: Record<string, unknown>) {
  if (!project || active(project) || requestBusy || !workerReady) return;
  requestBusy = true; el('error').hidden = true; controls();
  try {
    const id = project.id; await api(`/api/projects/${encodeURIComponent(id)}/rebuild`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corrections) });
    cancelRequested = false; const token = ++epoch; if (pollTimer) clearTimeout(pollTimer); await pollProject(id, token);
  } catch (cause) { error(cause instanceof Error ? cause.message : 'The rebuild could not be started.'); }
  finally { requestBusy = false; controls(); }
}
el('retry-job').addEventListener('click', () => { void rebuild(project?.corrections || {}); });
el('corrections-form').addEventListener('submit', event => { event.preventDefault(); el('corrections-error').hidden = true; try { void rebuild(getCorrections()); } catch (cause) { el('corrections-error').textContent = cause instanceof Error ? cause.message : 'Review the corrections.'; el('corrections-error').hidden = false; } });

function setMode(mode: Mode) {
  if (!modelLoaded) return;
  currentMode = mode; previewMode = false; viewer?.setMode(mode);
  for (const item of ['walk', 'orbit', 'source']) { el(`${item}-mode`).classList.toggle('active', item === mode); el(`${item}-mode`).setAttribute('aria-pressed', String(item === mode)); }
  el('canvas-wrap').classList.toggle('comparing', mode === 'source');
  el('compare-original').hidden = mode !== 'source'; el('compare-model-label').hidden = mode !== 'source'; el('blender-preview').hidden = true;
  el('preview-toggle').setAttribute('aria-pressed', 'false');
  el('direction-pad').hidden = mode !== 'walk';
  const touch = window.matchMedia('(pointer: coarse)').matches || innerWidth <= 760;
  el('viewer-hint').innerHTML = mode === 'source' ? `${icon('image')} Source-camera comparison <span>·</span> Review inferred details` : mode === 'walk' ? touch ? `${icon('walk')} Drag to look <span>·</span> Hold arrows to move` : `${icon('walk')} Click to look <span>·</span> WASD / arrows to move <span>·</span> Esc to release` : `${icon('orbit')} Drag to orbit <span>·</span> Scroll to move closer`;
  el('compare-model-label').textContent = 'Reconstructed source view';
}
for (const mode of ['walk', 'orbit', 'source'] as const) el(`${mode}-mode`).addEventListener('click', () => setMode(mode));
el('preview-toggle').addEventListener('click', () => { if (!modelLoaded) return; if (currentMode !== 'source') setMode('source'); previewMode = !previewMode; el('blender-preview').hidden = !previewMode; el('preview-toggle').setAttribute('aria-pressed', String(previewMode)); el('compare-model-label').textContent = previewMode ? 'Blender source-camera render' : 'Reconstructed source view'; });
el('reset').addEventListener('click', () => viewer?.reset());
el('fullscreen').addEventListener('click', async () => { try { if (document.fullscreenElement) await document.exitFullscreen(); else await el('canvas-wrap').requestFullscreen(); } catch { error('Full screen is unavailable in this browser.'); } });
document.querySelectorAll<HTMLButtonElement>('[data-move]').forEach(button => { const direction = button.dataset.move as 'forward' | 'backward' | 'left' | 'right'; button.addEventListener('pointerdown', event => { event.preventDefault(); button.setPointerCapture(event.pointerId); viewer?.move(direction, true); }); for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) button.addEventListener(event, () => viewer?.move(direction, false)); });
const dialog = el<HTMLDialogElement>('help-dialog'); el('help').addEventListener('click', () => dialog.showModal()); for (const id of ['close-help', 'got-it']) el(id).addEventListener('click', () => dialog.close());
dialog.addEventListener('click', event => { if (event.target === dialog) { const rect = dialog.getBoundingClientRect(); if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) dialog.close(); } });
void (async () => { await Promise.allSettled([workerStatus(), refreshProjects()]); const id = selectedId && projects.some(item => item.id === selectedId) ? selectedId : projects[0]?.id; if (id && !file) await openProject(id); })();
window.addEventListener('beforeunload', () => { if (pollTimer) clearTimeout(pollTimer); viewer?.dispose(); if (photoUrl) URL.revokeObjectURL(photoUrl); });
