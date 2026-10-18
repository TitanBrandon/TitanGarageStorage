import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { SparkRenderer, SplatMesh } from '@sparkjsdev/spark';

type Mode = 'walk' | 'orbit';
type Direction = 'forward' | 'backward' | 'left' | 'right';

/** Renders real Gaussian-splat assets; an empty viewer never substitutes a sample. */
export default class Viewer {
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.PerspectiveCamera(65, 1, 0.025, 1000);
  private readonly renderer: THREE.WebGLRenderer;
  private readonly spark: SparkRenderer;
  private readonly controls: OrbitControls;
  private readonly observer: ResizeObserver;
  private readonly clock = new THREE.Clock();
  private readonly keys = new Set<string>();
  private readonly movement = new Set<Direction>();
  private readonly velocity = new THREE.Vector3();
  private readonly pending = new Set<SplatMesh>();
  private readonly initialPosition = new THREE.Vector3(0, 0, 0);
  private readonly initialTarget = new THREE.Vector3(0, 0, -3);
  private world: SplatMesh | null = null;
  private mode: Mode = 'orbit';
  private count = 0;
  private imported = false;
  private request: AbortController | null = null;
  private loadEpoch = 0;
  private dragging = false;
  private dragX = 0;
  private dragY = 0;
  private yaw = 0;
  private pitch = 0;
  private frame = 0;
  private disposed = false;
  private needsRender = true;

  constructor(private readonly container: HTMLElement, private readonly onStatus?: (message: string) => void) {
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('webgl2', { alpha: true, antialias: false, powerPreference: 'high-performance' });
    if (!context) throw new Error('Realistic 3D worlds require WebGL 2. Enable hardware acceleration or try a current Chrome, Edge, Firefox, or Safari browser.');
    this.renderer = new THREE.WebGLRenderer({ canvas, context, antialias: false, alpha: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.NoToneMapping;
    this.spark = new SparkRenderer({ renderer: this.renderer, onDirty: () => { this.needsRender = true; } });
    canvas.style.display = 'block';
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    canvas.style.touchAction = 'none';
    canvas.tabIndex = 0;
    canvas.setAttribute('aria-label', 'Interactive realistic 3D world. Drag to orbit, or select Walk and click the scene to use W A S D.');
    this.container.appendChild(canvas);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.075;
    this.controls.rotateSpeed = 0.45;
    this.controls.panSpeed = 0.7;
    this.controls.minDistance = 0.1;
    this.controls.maxDistance = 200;
    this.controls.maxPolarAngle = Math.PI * 0.98;
    this.controls.target.copy(this.initialTarget);
    this.camera.lookAt(this.initialTarget);
    this.controls.enabled = false;
    this.observer = new ResizeObserver(this.resize);
    this.observer.observe(container);
    canvas.addEventListener('pointerdown', this.pointerDown);
    canvas.addEventListener('pointermove', this.pointerMove);
    canvas.addEventListener('pointerup', this.pointerUp);
    canvas.addEventListener('pointercancel', this.pointerUp);
    canvas.addEventListener('blur', this.blur);
    window.addEventListener('pointerup', this.pointerUp);
    document.addEventListener('pointerlockchange', this.lockChange);
    window.addEventListener('keydown', this.keyDown);
    window.addEventListener('keyup', this.keyUp);
    window.addEventListener('blur', this.blur);
    this.container.dataset.splatCount = '0';
    this.container.dataset.loadState = 'empty';
    this.resize();
    this.animate();
  }

  get loadedSplatCount(): number { return this.count; }
  get hasWorld(): boolean { return this.world !== null; }

  /** Load a World Labs SPZ URL, or a local blob URL with its original filename. */
  async loadWorld(url: string, filename?: string): Promise<void> {
    if (this.disposed) throw new Error('This 3D viewer has been closed.');
    this.request?.abort();
    const controller = new AbortController();
    this.request = controller;
    const epoch = ++this.loadEpoch;
    this.container.dataset.loadState = 'loading';
    let candidate: SplatMesh | null = null;
    let previous: SplatMesh | null = null;
    const assertCurrent = () => {
      if (this.disposed || controller.signal.aborted || epoch !== this.loadEpoch) throw new DOMException('World loading was cancelled.', 'AbortError');
    };
    try {
      this.onStatus?.('Downloading the 3D world…');
      const response = await fetch(url, { signal: controller.signal });
      if (!response.ok) throw new Error(`The 3D asset could not be downloaded (HTTP ${response.status}). Try its original World Labs link or import an exported SPZ file.`);
      const fileBytes = await response.arrayBuffer();
      assertCurrent();
      if (fileBytes.byteLength === 0) throw new Error('The downloaded 3D asset is empty.');
      this.onStatus?.('Decoding the Gaussian splats…');
      candidate = new SplatMesh({ fileBytes, fileName: filename, editable: false, raycastable: false });
      this.pending.add(candidate);
      await candidate.initialized;
      assertCurrent();
      if (!candidate.isInitialized || candidate.numSplats < 1) throw new Error('This file does not contain a usable Gaussian-splat world. Import an SPZ, Gaussian PLY, or SPLAT file.');
      // Generated World Labs assets use image/RDF coordinates. Generic SPZ
      // imports use the format's standard Y-up convention; PLY/SPLAT scans
      // commonly use RDF and receive the half-turn into Three.js coordinates.
      const standardSpzImport = filename?.toLowerCase().endsWith('.spz');
      candidate.rotation.x = standardSpzImport ? 0 : Math.PI;
      candidate.updateMatrixWorld(true);
      // Let an older camera sort finish before replacing its source buffers.
      this.spark.autoUpdate = false;
      const sortDeadline = performance.now() + 30_000;
      while (this.spark.sorting) {
        assertCurrent();
        if (performance.now() > sortDeadline) throw new Error('The browser could not prepare the 3D world. Try a smaller export or a browser with hardware acceleration.');
        await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
      }
      assertCurrent();
      previous = this.world;
      previous?.removeFromParent();
      this.world = candidate;
      this.scene.add(candidate);
      this.scene.add(this.spark);
      if (filename) this.frameImportedWorld(candidate);
      else {
        this.initialPosition.set(0, 0, 0);
        this.initialTarget.set(0, 0, -3);
      }
      this.reset();
      this.controls.enabled = this.mode === 'orbit';
      this.spark.clearSplats();
      this.onStatus?.('Preparing the first 3D view…');
      this.renderer.getDrawingBufferSize(this.spark.renderSize);
      await this.spark.update({ scene: this.scene, camera: this.camera });
      assertCurrent();
      // Spark can throttle a sort into the next frame. Await that real result
      // rather than reporting success while its draw count is still zero.
      const firstViewDeadline = performance.now() + 30_000;
      while (this.spark.activeSplats < 1) {
        assertCurrent();
        if (performance.now() > firstViewDeadline) throw new Error('The browser could not prepare a visible 3D view. Try a smaller export or import the downloaded SPZ file.');
        await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
      }
      this.renderer.render(this.scene, this.camera);
      this.container.dataset.loadState = 'ready';
      this.count = candidate.numSplats;
      this.imported = Boolean(filename);
      this.container.dataset.splatCount = String(this.count);
      this.renderer.domElement.dataset.splatCount = String(this.count);
      this.pending.delete(candidate);
      previous?.dispose();
      this.onStatus?.(`${this.count.toLocaleString()} Gaussian splats loaded · Ready to explore`);
    } catch (error) {
      if (candidate) {
        this.pending.delete(candidate);
        if (this.world === candidate) {
          candidate.removeFromParent();
          this.world = previous;
          if (previous && !this.disposed) this.scene.add(previous);
          this.spark.clearSplats();
        }
        candidate.dispose();
      }
      if (epoch === this.loadEpoch) this.container.dataset.loadState = this.world ? 'ready' : 'error';
      if (!this.world) {
        this.count = 0;
        this.container.dataset.splatCount = '0';
        this.renderer.domElement.dataset.splatCount = '0';
        this.scene.remove(this.spark);
        this.controls.enabled = false;
      }
      if (error instanceof TypeError && /fetch|network|load/i.test(error.message)) {
        throw new Error('The browser could not download this 3D asset. Its link may have expired or the host may block cross-origin access. Open the World Labs world link or download its SPZ file and import it here.');
      }
      throw error;
    } finally {
      if (!this.disposed) this.spark.autoUpdate = true;
      if (this.request === controller) this.request = null;
    }
  }

  showEmpty(): void {
    this.request?.abort();
    this.request = null;
    this.loadEpoch++;
    this.blur();
    this.world?.removeFromParent();
    this.world?.dispose();
    this.world = null;
    this.count = 0;
    this.imported = false;
    this.container.dataset.splatCount = '0';
    this.container.dataset.loadState = 'empty';
    this.renderer.domElement.dataset.splatCount = '0';
    this.spark.clearSplats();
    this.scene.remove(this.spark);
    this.controls.enabled = false;
    if (document.pointerLockElement === this.renderer.domElement) document.exitPointerLock();
    this.renderer.clear();
  }

  clear(): void { this.showEmpty(); }

  setMode(mode: Mode): void {
    if (document.pointerLockElement === this.renderer.domElement) document.exitPointerLock();
    this.mode = mode;
    this.needsRender = true;
    this.blur();
    this.controls.enabled = !!this.world && mode === 'orbit';
    this.renderer.domElement.style.cursor = 'grab';
    if (mode === 'walk') {
      this.syncLookAngles();
      if (this.world) this.onStatus?.('Click the world to look around · W A S D to move · Escape releases the mouse');
    } else {
      const direction = this.camera.getWorldDirection(new THREE.Vector3());
      this.controls.target.copy(this.camera.position).addScaledVector(direction, 3);
      this.controls.update();
      if (this.world) this.onStatus?.('Drag to orbit · Scroll to move closer · Right-drag to pan');
    }
  }

  reset(): void {
    if (document.pointerLockElement === this.renderer.domElement) document.exitPointerLock();
    this.blur();
    this.needsRender = true;
    this.camera.position.copy(this.initialPosition);
    this.camera.lookAt(this.initialTarget);
    this.controls.target.copy(this.initialTarget);
    this.controls.update();
    this.syncLookAngles();
  }

  /** Imported assets can use different vertical coordinate conventions. */
  flipOrientation(): void {
    if (!this.world || !this.imported) return;
    this.world.rotation.x = (this.world.rotation.x + Math.PI) % (2 * Math.PI);
    this.world.updateMatrixWorld(true);
    this.frameImportedWorld(this.world);
    this.reset();
    this.needsRender = true;
    this.spark.setDirty();
    this.onStatus?.('Scene orientation flipped · Ready to explore');
  }

  /** Press-and-hold navigation for touch controls; visual splats do not provide collision walls. */
  move(direction: Direction, active: boolean): void {
    if (active && this.world && !document.querySelector('dialog[open]')) this.movement.add(direction);
    else this.movement.delete(direction);
  }

  dispose(): void {
    if (this.disposed) return;
    this.showEmpty();
    this.disposed = true;
    cancelAnimationFrame(this.frame);
    this.observer.disconnect();
    const canvas = this.renderer.domElement;
    canvas.removeEventListener('pointerdown', this.pointerDown);
    canvas.removeEventListener('pointermove', this.pointerMove);
    canvas.removeEventListener('pointerup', this.pointerUp);
    canvas.removeEventListener('pointercancel', this.pointerUp);
    canvas.removeEventListener('blur', this.blur);
    window.removeEventListener('pointerup', this.pointerUp);
    document.removeEventListener('pointerlockchange', this.lockChange);
    window.removeEventListener('keydown', this.keyDown);
    window.removeEventListener('keyup', this.keyUp);
    window.removeEventListener('blur', this.blur);
    this.controls.dispose();
    // Decoding cannot be interrupted by Spark. Release any in-flight mesh as
    // soon as its decoder finishes; downloading is cancelled above.
    for (const mesh of this.pending) void mesh.initialized.then(() => mesh.dispose(), () => mesh.dispose());
    this.pending.clear();
    this.spark.dispose();
    this.renderer.dispose();
    this.renderer.forceContextLoss();
    canvas.remove();
  }

  private frameImportedWorld(mesh: SplatMesh): void {
    // Distant background Gaussians can lie hundreds of units from a scan.
    // Frame the central 60% of a deterministic sample rather than those outliers.
    let bounds: THREE.Box3;
    if (mesh.packedSplats) {
      const samples: number[][] = [[], [], []];
      const stride = Math.max(1, Math.ceil(mesh.numSplats / 8192));
      for (let index = 0; index < mesh.numSplats; index += stride) {
        const splat = mesh.packedSplats.getSplat(index);
        if (splat.opacity < 0.025) continue;
        const center = splat.center.applyMatrix4(mesh.matrixWorld);
        if (![center.x, center.y, center.z].every(Number.isFinite)) continue;
        samples[0].push(center.x);
        samples[1].push(center.y);
        samples[2].push(center.z);
      }
      if (samples[0].length < 2) return;
      for (const values of samples) values.sort((a, b) => a - b);
      const minimum = samples.map(values => values[Math.floor((values.length - 1) * 0.2)]);
      const maximum = samples.map(values => values[Math.ceil((values.length - 1) * 0.8)]);
      bounds = new THREE.Box3(new THREE.Vector3(...minimum), new THREE.Vector3(...maximum));
    } else bounds = mesh.getBoundingBox().applyMatrix4(mesh.matrixWorld);
    if (bounds.isEmpty()) return;
    const center = bounds.getCenter(new THREE.Vector3());
    const radius = bounds.getSize(new THREE.Vector3()).length() * 0.5;
    if (!Number.isFinite(radius) || radius <= 0) return;
    // Generic imported scans can be far from their origin. Fit their bounds;
    // generated worlds retain the provider's original camera location instead.
    const verticalFov = THREE.MathUtils.degToRad(this.camera.fov / 2);
    const horizontalFov = Math.atan(Math.tan(verticalFov) * this.camera.aspect);
    const distance = Math.max(0.5, radius / Math.sin(Math.min(verticalFov, horizontalFov)) * 1.1);
    this.initialTarget.copy(center);
    this.initialPosition.copy(center).add(new THREE.Vector3(0, radius * 0.12, distance));
    this.controls.maxDistance = Math.max(200, distance * 4);
  }

  private readonly resize = (): void => {
    const width = Math.max(1, this.container.clientWidth);
    const height = Math.max(1, this.container.clientHeight);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height, false);
    this.needsRender = true;
  };

  private syncLookAngles(): void {
    const euler = new THREE.Euler().setFromQuaternion(this.camera.quaternion, 'YXZ');
    this.pitch = euler.x;
    this.yaw = euler.y;
  }

  private readonly pointerDown = (event: PointerEvent): void => {
    if (!this.world || this.mode !== 'walk' || event.button !== 0 || document.querySelector('dialog[open]')) return;
    const canvas = this.renderer.domElement;
    canvas.focus({ preventScroll: true });
    this.dragging = true;
    this.dragX = event.clientX;
    this.dragY = event.clientY;
    canvas.style.cursor = 'grabbing';
    if (event.pointerType === 'mouse' && document.pointerLockElement !== canvas && canvas.requestPointerLock) {
      try {
        const request = canvas.requestPointerLock();
        if (request && typeof request.catch === 'function') void request.catch(() => undefined);
      } catch { /* Embedded previews can still use drag-to-look. */ }
    } else if (event.pointerType !== 'mouse') canvas.setPointerCapture(event.pointerId);
  };

  private readonly pointerMove = (event: PointerEvent): void => {
    if (this.mode !== 'walk' || !this.world) return;
    const locked = document.pointerLockElement === this.renderer.domElement;
    if (!locked && !this.dragging) return;
    const x = locked ? event.movementX : event.clientX - this.dragX;
    const y = locked ? event.movementY : event.clientY - this.dragY;
    this.dragX = event.clientX;
    this.dragY = event.clientY;
    this.yaw -= x * 0.0027;
    this.pitch = THREE.MathUtils.clamp(this.pitch - y * 0.0027, -1.48, 1.48);
    this.camera.quaternion.setFromEuler(new THREE.Euler(this.pitch, this.yaw, 0, 'YXZ'));
    this.needsRender = true;
  };

  private readonly pointerUp = (): void => {
    this.dragging = false;
    this.renderer.domElement.style.cursor = 'grab';
  };

  private readonly lockChange = (): void => {
    if (document.pointerLockElement !== this.renderer.domElement) this.blur();
  };

  private readonly keyDown = (event: KeyboardEvent): void => {
    if (document.activeElement !== this.renderer.domElement || document.querySelector('dialog[open]') || this.mode !== 'walk' || !this.world) return;
    if (['KeyW', 'KeyA', 'KeyS', 'KeyD', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'KeyQ', 'KeyE', 'Space', 'ShiftLeft', 'ShiftRight'].includes(event.code)) {
      event.preventDefault();
      this.keys.add(event.code);
    }
  };

  private readonly keyUp = (event: KeyboardEvent): void => { this.keys.delete(event.code); };
  private readonly blur = (): void => { this.keys.clear(); this.movement.clear(); this.velocity.set(0, 0, 0); this.dragging = false; };

  private updateWalk(delta: number): void {
    if (document.querySelector('dialog[open]')) { this.blur(); return; }
    const forward = Number(this.keys.has('KeyW') || this.keys.has('ArrowUp') || this.movement.has('forward')) - Number(this.keys.has('KeyS') || this.keys.has('ArrowDown') || this.movement.has('backward'));
    const side = Number(this.keys.has('KeyD') || this.keys.has('ArrowRight') || this.movement.has('right')) - Number(this.keys.has('KeyA') || this.keys.has('ArrowLeft') || this.movement.has('left'));
    const vertical = Number(this.keys.has('KeyE') || this.keys.has('Space')) - Number(this.keys.has('KeyQ'));
    const direction = new THREE.Vector3(-Math.sin(this.yaw) * forward + Math.cos(this.yaw) * side, vertical, -Math.cos(this.yaw) * forward - Math.sin(this.yaw) * side);
    if (direction.lengthSq() > 0) direction.normalize();
    const speed = this.keys.has('ShiftLeft') || this.keys.has('ShiftRight') ? 4.5 : 1.8;
    this.velocity.lerp(direction.multiplyScalar(speed), 1 - Math.exp(-12 * delta));
    if (this.velocity.lengthSq() > 0.0000001) {
      this.camera.position.addScaledVector(this.velocity, delta);
      this.needsRender = true;
    } else this.velocity.set(0, 0, 0);
  }

  private readonly animate = (): void => {
    if (this.disposed) return;
    this.frame = requestAnimationFrame(this.animate);
    const delta = Math.min(this.clock.getDelta(), 0.05);
    if (this.world) {
      if (this.mode === 'walk') this.updateWalk(delta);
      else if (this.controls.update()) this.needsRender = true;
    }
    if (this.needsRender || (this.world && this.spark.dirty)) {
      this.needsRender = false;
      this.renderer.render(this.scene, this.camera);
    }
  };
}
