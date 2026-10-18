import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { createExampleScene } from './scene';

const SOURCE_FOV = 58;

type Mode = 'walk' | 'orbit';
type Direction = 'forward' | 'backward' | 'left' | 'right';

/** Browser-side viewer. Photo geometry is reconstructed from an actual predicted depth map. */
export default class Viewer {
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.PerspectiveCamera(SOURCE_FOV, 1, 0.08, 170);
  private readonly renderer: THREE.WebGLRenderer;
  private readonly controls: OrbitControls;
  private readonly observer: ResizeObserver;
  private readonly clock = new THREE.Clock();
  private readonly keys = new Set<string>();
  private readonly movement = new Set<Direction>();
  private readonly raycaster = new THREE.Raycaster();
  private environment: THREE.WebGLRenderTarget | null = null;
  private readonly velocity = new THREE.Vector3();
  private model: THREE.Group | null = null;
  private photoMesh: THREE.Mesh | null = null;
  private photoPoints: THREE.Points | null = null;
  private mode: Mode = 'orbit';
  private photo = false;
  private photoAspect = 1;
  private pointCloud = false;
  private dragging = false;
  private dragX = 0;
  private dragY = 0;
  private yaw = 0;
  private pitch = 0;
  private frame = 0;
  private disposed = false;
  private readonly initialPosition = new THREE.Vector3();
  private readonly initialTarget = new THREE.Vector3();
  private readonly onStatus?: (message: string) => void;

  constructor(private readonly container: HTMLElement, onStatus?: (message: string) => void) {
    this.onStatus = onStatus;
    this.renderer = new THREE.WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 1.04;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    // All room geometry is static; cache the sun shadow between camera moves.
    this.renderer.shadowMap.autoUpdate = false;
    const canvas = this.renderer.domElement;
    canvas.style.display = 'block';
    canvas.style.width = '100%';
    canvas.style.height = '100%';
    canvas.style.touchAction = 'none';
    canvas.tabIndex = 0;
    canvas.setAttribute('aria-label', 'Interactive 3D space. Drag to look around, or select Walk and use W A S D.');
    this.container.appendChild(canvas);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.075;
    this.controls.rotateSpeed = 0.55;
    this.controls.panSpeed = 0.75;
    this.controls.minDistance = 0.6;
    this.controls.maxDistance = 32;
    this.controls.maxPolarAngle = Math.PI * 0.89;
    this.addLighting();
    this.observer = new ResizeObserver(this.resize);
    this.observer.observe(container);
    canvas.addEventListener('pointerdown', this.pointerDown);
    canvas.addEventListener('pointermove', this.pointerMove);
    canvas.addEventListener('pointerup', this.pointerUp);
    canvas.addEventListener('pointercancel', this.pointerUp);
    canvas.addEventListener('blur', this.blur);
    document.addEventListener('pointerlockchange', this.lockChange);
    window.addEventListener('keydown', this.keyDown);
    window.addEventListener('keyup', this.keyUp);
    window.addEventListener('blur', this.blur);
    this.showExample();
    this.resize();
    this.animate();
  }

  /** Input must be a grayscale depth image: brighter pixels are nearer the camera. */
  loadPhoto(color: HTMLImageElement, depth: HTMLImageElement): void {
    if (!color.naturalWidth || !depth.naturalWidth) throw new Error('The photo and depth map must finish loading first.');
    const aspect = color.naturalWidth / color.naturalHeight;
    const longest = 380;
    const width = Math.max(24, Math.round(aspect >= 1 ? longest : longest * aspect));
    const height = Math.max(24, Math.round(aspect >= 1 ? longest / aspect : longest));
    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext('2d', { willReadFrequently: true });
    if (!context) throw new Error('This browser cannot read the depth image.');
    context.drawImage(depth, 0, 0, width, height);
    const depthPixels = context.getImageData(0, 0, width, height).data;
    const values = new Float32Array(width * height);
    for (let index = 0; index < values.length; index++) values[index] = depthPixels[index * 4] / 255;
    const sorted = Float32Array.from(values).sort();
    const low = sorted[Math.floor(sorted.length * 0.015)];
    const high = sorted[Math.floor(sorted.length * 0.985)];
    if (high - low < 0.015) throw new Error('The depth map has no usable depth variation. Try another photo.');
    context.drawImage(color, 0, 0, width, height);
    const colorPixels = context.getImageData(0, 0, width, height).data;
    const positions = new Float32Array(width * height * 3);
    const colors = new Float32Array(width * height * 3);
    const uvs = new Float32Array(width * height * 2);
    const distances = new Float32Array(width * height);
    const tangent = Math.tan(THREE.MathUtils.degToRad(SOURCE_FOV * 0.5));
    const pixelColor = new THREE.Color();
    // A monocular depth map has relative scale. These distances are a navigable
    // presentation scale, not a measurement of the photographed room.
    const near = 2.4;
    const far = 17;
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const index = y * width + x;
        const u = x / (width - 1);
        const v = y / (height - 1);
        const inverseDepth = THREE.MathUtils.clamp((values[index] - low) / (high - low), 0, 1);
        const distance = 1 / THREE.MathUtils.lerp(1 / far, 1 / near, inverseDepth);
        distances[index] = distance;
        positions[index * 3] = (u * 2 - 1) * distance * tangent * aspect;
        positions[index * 3 + 1] = (1 - v * 2) * distance * tangent;
        positions[index * 3 + 2] = -distance;
        uvs[index * 2] = u;
        uvs[index * 2 + 1] = 1 - v;
        pixelColor.setRGB(colorPixels[index * 4] / 255, colorPixels[index * 4 + 1] / 255, colorPixels[index * 4 + 2] / 255, THREE.SRGBColorSpace);
        colors[index * 3] = pixelColor.r;
        colors[index * 3 + 1] = pixelColor.g;
        colors[index * 3 + 2] = pixelColor.b;
      }
    }
    const indices: number[] = [];
    const addTriangle = (a: number, b: number, c: number) => {
      const minimum = Math.min(distances[a], distances[b], distances[c]);
      const maximum = Math.max(distances[a], distances[b], distances[c]);
      // Separate object silhouettes instead of stretching their colors across
      // unseen gaps. Missing surfaces remain missing when the camera moves.
      if (maximum - minimum <= Math.max(0.28, minimum * 0.13)) indices.push(a, b, c);
    };
    for (let y = 0; y < height - 1; y++) {
      for (let x = 0; x < width - 1; x++) {
        const a = y * width + x;
        const b = a + 1;
        const c = a + width;
        const d = c + 1;
        addTriangle(a, c, b);
        addTriangle(b, c, d);
      }
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geometry.setAttribute('uv', new THREE.BufferAttribute(uvs, 2));
    geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));
    geometry.setIndex(indices);
    geometry.computeBoundingSphere();
    const texture = new THREE.Texture(color);
    texture.colorSpace = THREE.SRGBColorSpace;
    texture.anisotropy = Math.min(this.renderer.capabilities.getMaxAnisotropy(), 8);
    texture.needsUpdate = true;
    const material = new THREE.MeshBasicMaterial({ map: texture, side: THREE.DoubleSide, toneMapped: false });
    const mesh = new THREE.Mesh(geometry, material);
    mesh.name = 'Photo surface reconstructed from estimated depth';
    // Point geometry intentionally has no triangle index: each depth sample is a point.
    const pointGeometry = new THREE.BufferGeometry();
    pointGeometry.setAttribute('position', geometry.getAttribute('position'));
    pointGeometry.setAttribute('color', geometry.getAttribute('color'));
    pointGeometry.computeBoundingSphere();
    const points = new THREE.Points(pointGeometry, new THREE.PointsMaterial({
      size: 0.027, sizeAttenuation: true, vertexColors: true, toneMapped: false,
    }));
    this.clearModel();
    this.model = new THREE.Group();
    this.model.add(mesh, points);
    this.scene.add(this.model);
    this.photoMesh = mesh;
    this.photoPoints = points;
    this.photo = true;
    this.pointCloud = false;
    this.photoAspect = aspect;
    this.resize();
    this.scene.background = new THREE.Color('#11171c');
    this.scene.fog = null;
    this.controls.maxPolarAngle = Math.PI * 0.89;
    this.initialPosition.set(0, 0, 0.01);
    this.initialTarget.set(0, 0, -6);
    this.controls.minDistance = 0.15;
    this.controls.maxDistance = 28;
    this.applyPointMode();
    this.reset();
    this.onStatus?.('Photo reconstructed. Move gently to explore its estimated depth.');
  }

  showExample(): void {
    this.clearModel();
    this.photo = false;
    this.pointCloud = false;
    this.resize();
    this.photoMesh = null;
    this.photoPoints = null;
    this.model = createExampleScene();
    this.scene.add(this.model);
    this.scene.background = new THREE.Color('#c9d9e1');
    this.scene.fog = new THREE.Fog('#c9d9e1', 39, 100);
    this.controls.maxPolarAngle = Math.PI * 0.495;
    this.renderer.shadowMap.needsUpdate = true;
    this.initialPosition.set(0.7, 1.85, 7.5);
    this.initialTarget.set(0, 1.55, -7.5);
    this.controls.minDistance = 1.2;
    this.controls.maxDistance = 38;
    this.reset();
  }

  setMode(mode: Mode): void {
    if (mode === this.mode) return;
    if (document.pointerLockElement === this.renderer.domElement) document.exitPointerLock();
    this.mode = mode;
    this.controls.enabled = mode === 'orbit';
    this.keys.clear();
    this.movement.clear();
    this.velocity.set(0, 0, 0);
    this.dragging = false;
    this.renderer.domElement.style.cursor = mode === 'walk' ? 'grab' : 'grab';
    if (mode === 'walk') {
      this.syncLookAngles();
      this.onStatus?.('Click the scene to look around. Move with W A S D or the arrow keys.');
    } else {
      const direction = this.camera.getWorldDirection(new THREE.Vector3());
      this.controls.target.copy(this.camera.position).addScaledVector(direction, this.photo ? 5 : 10);
      this.controls.update();
      this.onStatus?.('Drag to orbit · Scroll to move closer · Right-drag to pan');
    }
  }

  reset(): void {
    if (document.pointerLockElement === this.renderer.domElement) document.exitPointerLock();
    this.keys.clear();
    this.movement.clear();
    this.velocity.set(0, 0, 0);
    this.dragging = false;
    this.camera.position.copy(this.initialPosition);
    this.camera.lookAt(this.initialTarget);
    this.controls.target.copy(this.initialTarget);
    this.controls.update();
    this.syncLookAngles();
  }

  setPointCloud(enabled: boolean): void {
    this.pointCloud = enabled;
    this.applyPointMode();
  }

  /** Supports press-and-hold on-screen navigation controls. */
  move(direction: Direction, active: boolean): void {
    if (active) this.movement.add(direction);
    else this.movement.delete(direction);
  }

  dispose(): void {
    this.disposed = true;
    cancelAnimationFrame(this.frame);
    this.observer.disconnect();
    const canvas = this.renderer.domElement;
    if (document.pointerLockElement === canvas) document.exitPointerLock();
    canvas.removeEventListener('pointerdown', this.pointerDown);
    canvas.removeEventListener('pointermove', this.pointerMove);
    canvas.removeEventListener('pointerup', this.pointerUp);
    canvas.removeEventListener('pointercancel', this.pointerUp);
    canvas.removeEventListener('blur', this.blur);
    document.removeEventListener('pointerlockchange', this.lockChange);
    window.removeEventListener('keydown', this.keyDown);
    window.removeEventListener('keyup', this.keyUp);
    window.removeEventListener('blur', this.blur);
    this.controls.dispose();
    this.clearModel();
    this.scene.traverse((object) => { if (object instanceof THREE.Light) object.dispose(); });
    this.environment?.dispose();
    this.renderer.dispose();
    canvas.remove();
  }

  private addLighting(): void {
    const generator = new THREE.PMREMGenerator(this.renderer);
    const room = new RoomEnvironment();
    this.environment = generator.fromScene(room, 0.04);
    this.scene.environment = this.environment.texture;
    this.scene.environmentIntensity = 0.6;
    room.dispose();
    generator.dispose();
    this.scene.add(new THREE.HemisphereLight('#d9eaff', '#6a675d', 2.25));
    const sun = new THREE.DirectionalLight('#fff2df', 3.0);
    sun.position.set(14, 24, 13);
    sun.castShadow = true;
    sun.shadow.mapSize.set(2048, 2048);
    sun.shadow.camera.left = -23;
    sun.shadow.camera.right = 23;
    sun.shadow.camera.top = 24;
    sun.shadow.camera.bottom = -24;
    sun.shadow.camera.near = 1;
    sun.shadow.camera.far = 80;
    sun.shadow.normalBias = 0.035;
    sun.shadow.bias = -0.00015;
    sun.shadow.radius = 4;
    this.scene.add(sun);
    const fill = new THREE.DirectionalLight('#b8d9ff', 1.4);
    fill.position.set(-10, 6, 5);
    this.scene.add(fill);
  }

  private applyPointMode(): void {
    if (this.photoMesh) this.photoMesh.visible = !this.pointCloud;
    if (this.photoPoints) this.photoPoints.visible = this.pointCloud;
  }

  private clearModel(): void {
    if (!this.model) return;
    this.scene.remove(this.model);
    const geometries = new Set<THREE.BufferGeometry>();
    const materials = new Set<THREE.Material>();
    const textures = new Set<THREE.Texture>();
    this.model.traverse((object) => {
      if (object instanceof THREE.Mesh || object instanceof THREE.Points) {
        geometries.add(object.geometry);
        for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
          materials.add(material);
          for (const value of Object.values(material)) if (value instanceof THREE.Texture) textures.add(value);
        }
      }
    });
    for (const geometry of geometries) geometry.dispose();
    for (const material of materials) material.dispose();
    for (const texture of textures) texture.dispose();
    this.model = null;
    this.photoMesh = null;
    this.photoPoints = null;
  }

  private readonly resize = (): void => {
    const width = Math.max(1, this.container.clientWidth);
    const height = Math.max(1, this.container.clientHeight);
    this.camera.aspect = width / height;
    // Geometry uses the source photo's field of view. Widen the vertical
    // camera field on narrow viewports so its full original framing fits;
    // wider viewports naturally leave space at the sides.
    const fit = this.photo ? Math.max(1, this.photoAspect / this.camera.aspect) : 1;
    this.camera.fov = THREE.MathUtils.radToDeg(2 * Math.atan(Math.tan(THREE.MathUtils.degToRad(SOURCE_FOV / 2)) * fit));
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width, height, false);
  };

  private syncLookAngles(): void {
    const euler = new THREE.Euler().setFromQuaternion(this.camera.quaternion, 'YXZ');
    this.pitch = euler.x;
    this.yaw = euler.y;
  }

  private readonly pointerDown = (event: PointerEvent): void => {
    if (this.mode !== 'walk' || event.button !== 0) return;
    const canvas = this.renderer.domElement;
    canvas.focus({ preventScroll: true });
    this.dragging = true;
    this.dragX = event.clientX;
    this.dragY = event.clientY;
    canvas.style.cursor = 'grabbing';
    if (event.pointerType === 'mouse' && document.pointerLockElement !== canvas && canvas.requestPointerLock) {
      // Pointer-lock rejection (for example in an embedded preview) falls back
      // to the same drag-to-look controls used on touchscreens.
      try {
        const request = canvas.requestPointerLock();
        if (request && typeof request.catch === 'function') void request.catch(() => undefined);
      } catch { /* Drag-to-look remains available. */ }
    } else if (event.pointerType !== 'mouse') canvas.setPointerCapture(event.pointerId);
  };

  private readonly pointerMove = (event: PointerEvent): void => {
    if (this.mode !== 'walk') return;
    const locked = document.pointerLockElement === this.renderer.domElement;
    if (!locked && !this.dragging) return;
    const x = locked ? event.movementX : event.clientX - this.dragX;
    const y = locked ? event.movementY : event.clientY - this.dragY;
    this.dragX = event.clientX;
    this.dragY = event.clientY;
    this.yaw -= x * 0.0027;
    this.pitch = THREE.MathUtils.clamp(this.pitch - y * 0.0027, -1.40, 1.40);
    this.camera.quaternion.setFromEuler(new THREE.Euler(this.pitch, this.yaw, 0, 'YXZ'));
  };

  private readonly pointerUp = (): void => {
    this.dragging = false;
    this.renderer.domElement.style.cursor = 'grab';
  };

  private readonly lockChange = (): void => {
    if (document.pointerLockElement !== this.renderer.domElement) {
      this.dragging = false;
      this.keys.clear();
      this.velocity.set(0, 0, 0);
    }
  };

  private readonly keyDown = (event: KeyboardEvent): void => {
    const target = event.target;
    if (document.activeElement !== this.renderer.domElement || document.querySelector('dialog[open]')) return;
    if (this.mode !== 'walk' || target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target instanceof HTMLSelectElement || (target instanceof HTMLElement && target.isContentEditable)) return;
    if (['KeyW', 'KeyA', 'KeyS', 'KeyD', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'KeyQ', 'KeyE', 'Space', 'ShiftLeft', 'ShiftRight'].includes(event.code)) {
      event.preventDefault();
      this.keys.add(event.code);
    }
  };

  private readonly keyUp = (event: KeyboardEvent): void => { this.keys.delete(event.code); };
  private readonly blur = (): void => { this.keys.clear(); this.movement.clear(); this.velocity.set(0, 0, 0); this.dragging = false; };

  private updateWalk(delta: number): void {
    const forward = Number(this.keys.has('KeyW') || this.keys.has('ArrowUp') || this.movement.has('forward')) - Number(this.keys.has('KeyS') || this.keys.has('ArrowDown') || this.movement.has('backward'));
    const side = Number(this.keys.has('KeyD') || this.keys.has('ArrowRight') || this.movement.has('right')) - Number(this.keys.has('KeyA') || this.keys.has('ArrowLeft') || this.movement.has('left'));
    const vertical = this.photo ? Number(this.keys.has('KeyE') || this.keys.has('Space')) - Number(this.keys.has('KeyQ')) : 0;
    const direction = new THREE.Vector3(-Math.sin(this.yaw) * forward + Math.cos(this.yaw) * side, vertical, -Math.cos(this.yaw) * forward - Math.sin(this.yaw) * side);
    if (direction.lengthSq() > 0) direction.normalize();
    const speed = this.photo ? 1.8 : (this.keys.has('ShiftLeft') || this.keys.has('ShiftRight') ? 5 : 2.8);
    const targetVelocity = direction.multiplyScalar(speed);
    this.velocity.lerp(targetVelocity, 1 - Math.exp(-12 * delta));
    if (this.velocity.lengthSq() < 0.00001) return;
    const step = this.velocity.clone().multiplyScalar(delta);
    if (!this.photo && this.model && step.lengthSq() > 0) {
      this.raycaster.set(this.camera.position, step.clone().normalize());
      this.raycaster.near = 0.01;
      this.raycaster.far = step.length() + 0.34;
      if (this.raycaster.intersectObject(this.model, true).length > 0) {
        this.velocity.set(0, 0, 0);
        return;
      }
    }
    this.camera.position.add(step);
    if (this.photo) {
      this.camera.position.x = THREE.MathUtils.clamp(this.camera.position.x, -8, 8);
      this.camera.position.y = THREE.MathUtils.clamp(this.camera.position.y, -5, 5);
      this.camera.position.z = THREE.MathUtils.clamp(this.camera.position.z, -12, 6);
    } else {
      this.camera.position.x = THREE.MathUtils.clamp(this.camera.position.x, -9.5, 13);
      this.camera.position.y = THREE.MathUtils.clamp(this.camera.position.y, 1.25, 2.1);
      this.camera.position.z = THREE.MathUtils.clamp(this.camera.position.z, -18.3, 13);
    }
  }

  private readonly animate = (): void => {
    if (this.disposed) return;
    this.frame = requestAnimationFrame(this.animate);
    const delta = Math.min(this.clock.getDelta(), 0.05);
    if (this.mode === 'walk') this.updateWalk(delta);
    else this.controls.update();
    this.renderer.render(this.scene, this.camera);
  };
}
