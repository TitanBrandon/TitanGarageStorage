import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

export type Vec2 = [number, number];
export type Vec3 = [number, number, number];
export type CameraMode = 'walk' | 'orbit' | 'source';
type Direction = 'forward' | 'backward' | 'left' | 'right';
export interface SceneMaterial { color: Vec3; roughness: number; metalness: number; kind: string; texture?: string | null; texture_tile_size?: number; texture_repeat?: boolean }
export interface SceneOpening { kind: 'door' | 'window' | 'opening'; offset: number; width: number; height: number; bottom: number; confidence?: number }
export interface SceneWall { id: string; start: Vec2; end: Vec2; height: number; thickness: number; openings?: SceneOpening[]; material?: string }
export interface SceneObject { id: string; kind: string; position: Vec3; dimensions: Vec3; rotation_y: number; wall_id?: string | null; material?: string; front_material?: string | null; confidence?: number }
export interface SceneDescriptor {
  schema_version?: number;
  units?: string;
  room: { width: number; depth: number; height: number; floor_polygon: Vec2[]; walls: SceneWall[]; ceiling?: boolean; floor_material?: string; ceiling_material?: string };
  camera: { position: Vec3; target: Vec3; fov: number; aspect: number; fov_axis?: 'vertical' | 'horizontal' };
  walk_start: { position: Vec3; target: Vec3 };
  objects: SceneObject[];
  materials?: Record<string, SceneMaterial>;
  source?: { image_path: string; width: number; height: number; sha256: string };
  analysis?: { confidence: number; warnings: string[]; method: string; diagnostics?: Record<string, unknown> };
}
interface WallCollider { a: THREE.Vector2; b: THREE.Vector2; radius: number }
interface BoxCollider { x: number; z: number; halfWidth: number; halfDepth: number; cosine: number; sine: number }
interface CollisionScene { floor: THREE.Vector2[]; walls: WallCollider[]; boxes: BoxCollider[]; eyeHeight: number }
const BODY_RADIUS = 0.23;

/** Loads Blender GLB geometry and navigates its independently described room. */
export default class Viewer {
  private readonly scene = new THREE.Scene();
  private readonly camera = new THREE.PerspectiveCamera(60, 1, 0.035, 250);
  private readonly renderer: THREE.WebGLRenderer;
  private readonly controls: OrbitControls;
  private readonly observer: ResizeObserver;
  private readonly clock = new THREE.Clock();
  private readonly keys = new Set<string>();
  private readonly movement = new Set<Direction>();
  private readonly velocity = new THREE.Vector3();
  private readonly sun = new THREE.DirectionalLight('#fff4e4', 2.1);
  private readonly fill = new THREE.DirectionalLight('#e2edff', 0.45);
  private readonly hemisphere = new THREE.HemisphereLight('#eef3fa', '#737675', 1.3);
  private environment: THREE.WebGLRenderTarget | null = null;
  private model: THREE.Group | null = null;
  private metadata: SceneDescriptor | null = null;
  private collision: CollisionScene | null = null;
  private readonly walkPosition = new THREE.Vector3();
  private readonly walkTarget = new THREE.Vector3();
  private savedWalk: { position: THREE.Vector3; quaternion: THREE.Quaternion } | null = null;
  private mode: CameraMode = 'orbit';
  private meshCount = 0;
  private collisions = 0;
  private request: AbortController | null = null;
  private epoch = 0;
  private dragging = false;
  private dragX = 0;
  private dragY = 0;
  private yaw = 0;
  private pitch = 0;
  private frame = 0;
  private disposed = false;
  private needsRender = true;

  constructor(private readonly container: HTMLElement, private readonly onStatus?: (message: string) => void) {
    this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: 'high-performance' });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.setClearColor(0x000000, 0);
    this.renderer.outputColorSpace = THREE.SRGBColorSpace;
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure = 0.95;
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.shadowMap.autoUpdate = false;
    const generator = new THREE.PMREMGenerator(this.renderer);
    const environmentScene = new RoomEnvironment();
    this.environment = generator.fromScene(environmentScene, 0.04);
    this.scene.environment = this.environment.texture;
    this.scene.environmentIntensity = 0.65;
    environmentScene.dispose();
    generator.dispose();
    this.scene.add(this.hemisphere, this.sun, this.fill, this.sun.target);
    this.sun.castShadow = true;
    this.sun.shadow.mapSize.set(2048, 2048);
    this.sun.shadow.normalBias = 0.025;
    this.sun.shadow.bias = -0.00012;
    this.sun.shadow.radius = 3;
    const canvas = this.renderer.domElement;
    canvas.style.cssText = 'display:block;width:100%;height:100%;touch-action:none';
    canvas.tabIndex = 0;
    canvas.setAttribute('aria-label', 'Reconstructed 3D room. Select Walk, click the scene, and move with W A S D. Source view matches the uploaded camera.');
    this.container.appendChild(canvas);
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.085;
    this.controls.rotateSpeed = 0.5;
    this.controls.minDistance = 0.15;
    this.controls.maxDistance = 80;
    this.controls.maxPolarAngle = Math.PI * 0.495;
    this.controls.enabled = false;
    this.observer = new ResizeObserver(this.resize);
    this.observer.observe(container);
    canvas.addEventListener('pointerdown', this.pointerDown);
    canvas.addEventListener('pointermove', this.pointerMove);
    canvas.addEventListener('pointercancel', this.pointerUp);
    canvas.addEventListener('blur', this.blur);
    window.addEventListener('pointerup', this.pointerUp);
    document.addEventListener('pointerlockchange', this.lockChange);
    window.addEventListener('keydown', this.keyDown);
    window.addEventListener('keyup', this.keyUp);
    window.addEventListener('blur', this.blur);
    this.container.dataset.loadState = 'empty';
    this.container.dataset.modelMeshCount = '0';
    this.container.dataset.textureCount = '0';
    this.container.dataset.collisionCount = '0';
    this.resize();
    this.animate();
  }

  get hasModel(): boolean { return this.model !== null; }
  get loadedMeshCount(): number { return this.meshCount; }

  async loadModel(url: string, sceneMetadata: SceneDescriptor): Promise<void> {
    if (this.disposed) throw new Error('The 3D viewer has been closed.');
    this.validateMetadata(sceneMetadata);
    const collision = this.buildCollisions(sceneMetadata);
    const walkStart = this.safeWalkStart(sceneMetadata, collision);
    this.request?.abort();
    const controller = new AbortController();
    this.request = controller;
    const epoch = ++this.epoch;
    let candidate: THREE.Group | null = null;
    this.container.dataset.loadState = 'loading';
    const assertCurrent = () => {
      if (this.disposed || controller.signal.aborted || epoch !== this.epoch) throw new DOMException('Model loading was cancelled.', 'AbortError');
    };
    try {
      this.onStatus?.('Loading the textured Blender model…');
      const response = await fetch(url, { signal: controller.signal });
      if (!response.ok) throw new Error(`The 3D model could not be downloaded (HTTP ${response.status}). Reopen the project or retry processing.`);
      const bytes = await response.arrayBuffer();
      assertCurrent();
      if (bytes.byteLength < 20 || new DataView(bytes).getUint32(0, true) !== 0x46546c67) throw new Error('The generated asset is not a valid GLB model. Reprocess this project.');
      const base = url.startsWith('blob:') ? '' : new URL('.', new URL(url, location.href)).href;
      const gltf = await new GLTFLoader().parseAsync(bytes, base);
      candidate = gltf.scene;
      assertCurrent();
      const geometries = new Set<THREE.BufferGeometry>();
      const textures = new Set<THREE.Texture>();
      let meshes = 0;
      let triangles = 0;
      candidate.traverse(object => {
        if (!(object instanceof THREE.Mesh)) return;
        meshes++;
        geometries.add(object.geometry);
        const count = object.geometry.index?.count ?? object.geometry.getAttribute('position')?.count ?? 0;
        triangles += Math.floor(count / 3);
        if (!object.geometry.getAttribute('normal')) object.geometry.computeVertexNormals();
        object.castShadow = true;
        object.receiveShadow = true;
        for (const material of Array.isArray(object.material) ? object.material : [object.material]) {
          if (material instanceof THREE.MeshStandardMaterial) material.envMapIntensity = 0.8;
          for (const value of Object.values(material)) if (value instanceof THREE.Texture) {
            value.anisotropy = Math.min(8, this.renderer.capabilities.getMaxAnisotropy());
            textures.add(value);
          }
        }
      });
      if (meshes < 1 || triangles < 12) throw new Error('The generated model does not contain usable 3D geometry. Reprocess this photo or correct its room outline.');
      if (textures.size < 1) throw new Error('The generated model has no usable textures. Reprocess the project to prepare its photo-derived materials.');
      this.clearModel();
      this.model = candidate;
      candidate = null;
      this.metadata = sceneMetadata;
      this.collision = collision;
      this.walkPosition.copy(walkStart);
      this.walkTarget.fromArray(sceneMetadata.walk_start.target);
      this.walkTarget.add(walkStart.clone().sub(new THREE.Vector3().fromArray(sceneMetadata.walk_start.position)));
      this.savedWalk = null;
      this.meshCount = meshes;
      this.collisions = 0;
      this.scene.add(this.model);
      this.scene.background = new THREE.Color('#dfe5e8');
      this.configureLighting(sceneMetadata);
      this.reset();
      this.controls.enabled = this.mode === 'orbit';
      this.renderer.shadowMap.needsUpdate = true;
      this.renderFrame();
      this.container.dataset.modelMeshCount = String(meshes);
      this.container.dataset.textureCount = String(textures.size);
      this.container.dataset.triangleCount = String(triangles);
      this.container.dataset.collisionCount = '0';
      this.container.dataset.loadState = 'ready';
      this.needsRender = true;
      this.onStatus?.(`${meshes} modeled surfaces · Textures loaded · Ready to explore`);
    } catch (error) {
      if (candidate) this.disposeGroup(candidate);
      if (epoch === this.epoch) this.container.dataset.loadState = this.model ? 'ready' : 'error';
      if (error instanceof TypeError && /fetch|network/i.test(error.message)) throw new Error('The browser could not download the generated model. Check the connection and reopen this project.');
      throw error;
    } finally {
      if (this.request === controller) this.request = null;
    }
  }

  setMode(mode: CameraMode): void {
    if (this.mode === 'walk' && this.model) this.savedWalk = { position: this.camera.position.clone(), quaternion: this.camera.quaternion.clone() };
    if (document.pointerLockElement === this.renderer.domElement) document.exitPointerLock();
    this.blur();
    const oldMode = this.mode;
    this.mode = mode;
    this.controls.enabled = !!this.model && mode === 'orbit';
    this.container.dataset.cameraMode = mode;
    if (!this.metadata || !this.model) return;
    if (mode === 'source') this.applySourceCamera();
    else if (mode === 'walk') {
      if (this.savedWalk) {
        this.camera.position.copy(this.savedWalk.position);
        this.camera.quaternion.copy(this.savedWalk.quaternion);
      } else this.applyWalkCamera();
      this.syncLookAngles();
    } else {
      if (oldMode === 'source') this.controls.target.fromArray(this.metadata.camera.target);
      else this.controls.target.copy(this.camera.position).addScaledVector(this.camera.getWorldDirection(new THREE.Vector3()), Math.min(this.metadata.room.depth / 2, 5));
      this.controls.update();
    }
    this.updateProjection();
    this.updatePoseData();
    this.needsRender = true;
    this.onStatus?.(mode === 'source' ? 'Source camera · Compare the estimated model with your photo' : mode === 'walk' ? 'Click the room to look · W A S D / arrows to walk · Escape releases the mouse' : 'Drag to orbit · Scroll to move closer · Right-drag to pan');
  }

  reset(): void {
    if (document.pointerLockElement === this.renderer.domElement) document.exitPointerLock();
    this.blur();
    if (!this.metadata) return;
    if (this.mode === 'walk') {
      this.savedWalk = null;
      this.applyWalkCamera();
    } else this.applySourceCamera();
    this.updateProjection();
    this.syncLookAngles();
    this.updatePoseData();
    this.needsRender = true;
  }

  move(direction: Direction, active: boolean): void {
    if (active && this.model && this.mode === 'walk' && !document.querySelector('dialog[open]')) this.movement.add(direction);
    else this.movement.delete(direction);
  }

  showEmpty(): void {
    this.request?.abort();
    this.request = null;
    this.epoch++;
    this.blur();
    if (document.pointerLockElement === this.renderer.domElement) document.exitPointerLock();
    this.clearModel();
    this.metadata = null;
    this.collision = null;
    this.savedWalk = null;
    this.meshCount = 0;
    this.collisions = 0;
    this.controls.enabled = false;
    this.scene.background = null;
    Object.assign(this.container.dataset, { loadState: 'empty', modelMeshCount: '0', textureCount: '0', collisionCount: '0' });
    this.needsRender = true;
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
    canvas.removeEventListener('pointercancel', this.pointerUp);
    canvas.removeEventListener('blur', this.blur);
    window.removeEventListener('pointerup', this.pointerUp);
    document.removeEventListener('pointerlockchange', this.lockChange);
    window.removeEventListener('keydown', this.keyDown);
    window.removeEventListener('keyup', this.keyUp);
    window.removeEventListener('blur', this.blur);
    this.controls.dispose();
    this.environment?.dispose();
    this.sun.dispose();
    this.fill.dispose();
    this.hemisphere.dispose();
    this.renderer.dispose();
    this.renderer.forceContextLoss();
    canvas.remove();
  }

  private validateMetadata(scene: SceneDescriptor): void {
    const vector = (value: unknown, length: number) => Array.isArray(value) && value.length === length && value.every(item => typeof item === 'number' && Number.isFinite(item));
    if (!scene?.room || !scene.camera || !scene.walk_start || !Array.isArray(scene.room.floor_polygon) || scene.room.floor_polygon.length < 3 || !scene.room.floor_polygon.every(point => vector(point, 2)) || !vector(scene.camera.position, 3) || !vector(scene.camera.target, 3) || !vector(scene.walk_start.position, 3) || !vector(scene.walk_start.target, 3)) throw new Error('The model is missing valid room and camera metadata. Reprocess this project.');
    if (![scene.room.width, scene.room.depth, scene.room.height, scene.camera.fov, scene.camera.aspect].every(value => Number.isFinite(value) && value > 0)) throw new Error('The room dimensions or camera calibration are invalid. Correct the project settings and rebuild.');
  }

  private buildCollisions(scene: SceneDescriptor): CollisionScene {
    const eyeHeight = scene.walk_start.position[1] > 0.3 ? scene.walk_start.position[1] : 1.65;
    const collision: CollisionScene = { floor: scene.room.floor_polygon.map(point => new THREE.Vector2(...point)), walls: [], boxes: [], eyeHeight };
    for (const wall of scene.room.walls ?? []) {
      if (wall.height < 0.15) continue;
      const a = new THREE.Vector2(...wall.start), b = new THREE.Vector2(...wall.end);
      const length = a.distanceTo(b);
      if (length < 0.001) continue;
      const direction = b.clone().sub(a).divideScalar(length);
      const passages = (wall.openings ?? []).filter(opening => opening.kind !== 'window' && opening.bottom <= 0.12 && opening.bottom + opening.height >= eyeHeight + 0.15).map(opening => [Math.max(0, opening.offset), Math.min(length, opening.offset + opening.width)]).sort((first, second) => first[0] - second[0]);
      const add = (start: number, end: number) => { if (end - start > 0.001) collision.walls.push({ a: a.clone().addScaledVector(direction, start), b: a.clone().addScaledVector(direction, end), radius: BODY_RADIUS + (wall.thickness ?? 0.12) / 2 }); };
      let cursor = 0;
      for (const passage of passages) { add(cursor, passage[0]); cursor = Math.max(cursor, passage[1]); }
      add(cursor, length);
    }
    for (const object of scene.objects ?? []) {
      const [width, height, depth] = object.dimensions;
      if (width <= 0.04 || depth <= 0.04 || object.position[1] + height / 2 < 0.15 || object.position[1] - height / 2 > eyeHeight + 0.15) continue;
      collision.boxes.push({ x: object.position[0], z: object.position[2], halfWidth: width / 2, halfDepth: depth / 2, cosine: Math.cos(object.rotation_y ?? 0), sine: Math.sin(object.rotation_y ?? 0) });
    }
    return collision;
  }

  private distanceToSegment(x: number, z: number, a: THREE.Vector2, b: THREE.Vector2): number {
    const dx = b.x - a.x, dz = b.y - a.y;
    const denominator = dx * dx + dz * dz;
    const t = denominator ? THREE.MathUtils.clamp(((x - a.x) * dx + (z - a.y) * dz) / denominator, 0, 1) : 0;
    return Math.hypot(x - a.x - t * dx, z - a.y - t * dz);
  }

  private canOccupy(x: number, z: number, collision: CollisionScene): boolean {
    let inside = false;
    const floor = collision.floor;
    for (let i = 0, j = floor.length - 1; i < floor.length; j = i++) {
      const a = floor[i], b = floor[j];
      if ((a.y > z) !== (b.y > z) && x < (b.x - a.x) * (z - a.y) / (b.y - a.y) + a.x) inside = !inside;
      if (this.distanceToSegment(x, z, a, b) < BODY_RADIUS - 0.001) return false;
    }
    if (!inside) return false;
    for (const wall of collision.walls) if (this.distanceToSegment(x, z, wall.a, wall.b) < wall.radius) return false;
    for (const box of collision.boxes) {
      const dx = x - box.x, dz = z - box.z;
      const localX = box.cosine * dx - box.sine * dz;
      const localZ = box.sine * dx + box.cosine * dz;
      const nearestX = THREE.MathUtils.clamp(localX, -box.halfWidth, box.halfWidth);
      const nearestZ = THREE.MathUtils.clamp(localZ, -box.halfDepth, box.halfDepth);
      if ((localX - nearestX) ** 2 + (localZ - nearestZ) ** 2 < BODY_RADIUS ** 2) return false;
    }
    return true;
  }

  private safeWalkStart(scene: SceneDescriptor, collision: CollisionScene): THREE.Vector3 {
    const desired = new THREE.Vector3().fromArray(scene.walk_start.position);
    desired.y = collision.eyeHeight;
    if (this.canOccupy(desired.x, desired.z, collision)) return desired;
    const xs = collision.floor.map(point => point.x), zs = collision.floor.map(point => point.y);
    const minX = Math.min(...xs), maxX = Math.max(...xs), minZ = Math.min(...zs), maxZ = Math.max(...zs);
    let best: THREE.Vector3 | null = null;
    let distance = Infinity;
    const spacing = Math.max(0.18, Math.max(maxX - minX, maxZ - minZ) / 70);
    for (let x = minX + BODY_RADIUS; x <= maxX - BODY_RADIUS; x += spacing) for (let z = minZ + BODY_RADIUS; z <= maxZ - BODY_RADIUS; z += spacing) {
      if (!this.canOccupy(x, z, collision)) continue;
      const squared = (x - desired.x) ** 2 + (z - desired.z) ** 2;
      if (squared < distance) { distance = squared; best = new THREE.Vector3(x, collision.eyeHeight, z); }
    }
    if (!best) throw new Error('No safe walking area could be found. Correct the room corners or object positions and rebuild this project.');
    return best;
  }

  private configureLighting(scene: SceneDescriptor): void {
    const { width, depth, height } = scene.room;
    this.sun.position.set(width * 0.4, height * 0.92, depth * 0.9);
    this.sun.target.position.set(0, 1, -depth * 0.25);
    this.fill.position.set(-width * 0.35, height * 0.65, depth * 0.6);
    const extent = Math.max(width, depth) * 0.8;
    Object.assign(this.sun.shadow.camera, { left: -extent, right: extent, top: extent, bottom: -extent, near: 0.1, far: Math.max(40, extent * 4) });
    this.sun.shadow.camera.updateProjectionMatrix();
    this.controls.maxDistance = Math.max(20, Math.hypot(width, depth) * 3);
  }

  private applySourceCamera(): void {
    if (!this.metadata) return;
    this.camera.position.fromArray(this.metadata.camera.position);
    this.camera.lookAt(new THREE.Vector3().fromArray(this.metadata.camera.target));
    this.controls.target.fromArray(this.metadata.camera.target);
    // Flush orbit damping before installing a precisely calibrated source pose.
    const damping = this.controls.enableDamping;
    this.controls.enableDamping = false;
    this.controls.update();
    this.controls.enableDamping = damping;
    this.camera.position.fromArray(this.metadata.camera.position);
    this.camera.lookAt(new THREE.Vector3().fromArray(this.metadata.camera.target));
    this.controls.target.fromArray(this.metadata.camera.target);
  }

  private applyWalkCamera(): void {
    this.camera.position.copy(this.walkPosition);
    this.camera.lookAt(this.walkTarget);
    this.syncLookAngles();
  }

  private updateProjection(): void {
    if (this.mode === 'source' && this.metadata) {
      const source = this.metadata.camera;
      const tangent = Math.tan(THREE.MathUtils.degToRad(source.fov / 2)) / (source.fov_axis === 'horizontal' ? source.aspect : 1);
      this.camera.aspect = source.aspect;
      this.camera.fov = THREE.MathUtils.radToDeg(2 * Math.atan(tangent));
    } else {
      this.camera.aspect = Math.max(1, this.container.clientWidth) / Math.max(1, this.container.clientHeight);
      this.camera.fov = this.mode === 'walk' ? 65 : 60;
    }
    this.camera.updateProjectionMatrix();
  }

  private renderFrame(): void {
    const width = Math.max(1, this.container.clientWidth), height = Math.max(1, this.container.clientHeight);
    this.renderer.setScissorTest(false);
    this.renderer.setViewport(0, 0, width, height);
    this.renderer.clear();
    if (this.mode === 'source' && this.metadata) {
      // Preserve the calibrated photo rectangle exactly, including its field
      // of view. Letterboxing avoids adding unseen room surfaces to comparison.
      const aspect = this.metadata.camera.aspect;
      const fittedWidth = Math.min(width, height * aspect);
      const fittedHeight = fittedWidth / aspect;
      const x = (width - fittedWidth) / 2, y = (height - fittedHeight) / 2;
      this.renderer.setViewport(x, y, fittedWidth, fittedHeight);
      this.renderer.setScissor(x, y, fittedWidth, fittedHeight);
      this.renderer.setScissorTest(true);
    }
    this.renderer.render(this.scene, this.camera);
    this.renderer.setScissorTest(false);
  }

  private readonly resize = (): void => {
    const width = Math.max(1, this.container.clientWidth), height = Math.max(1, this.container.clientHeight);
    this.camera.aspect = width / height;
    this.updateProjection();
    this.renderer.setSize(width, height, false);
    this.needsRender = true;
  };

  private syncLookAngles(): void {
    const euler = new THREE.Euler().setFromQuaternion(this.camera.quaternion, 'YXZ');
    this.pitch = euler.x;
    this.yaw = euler.y;
  }

  private updatePoseData(): void {
    this.container.dataset.cameraPosition = JSON.stringify(this.camera.position.toArray().map(value => Number(value.toFixed(4))));
    this.container.dataset.cameraQuaternion = JSON.stringify(this.camera.quaternion.toArray().map(value => Number(value.toFixed(5))));
    this.container.dataset.cameraFov = this.camera.fov.toFixed(3);
    this.container.dataset.cameraAspect = this.camera.aspect.toFixed(5);
    this.container.dataset.cameraMode = this.mode;
  }

  private readonly pointerDown = (event: PointerEvent): void => {
    if (!this.model || this.mode !== 'walk' || event.button !== 0 || document.querySelector('dialog[open]')) return;
    const canvas = this.renderer.domElement;
    canvas.focus({ preventScroll: true });
    this.dragging = true;
    this.dragX = event.clientX;
    this.dragY = event.clientY;
    canvas.style.cursor = 'grabbing';
    if (event.pointerType === 'mouse' && document.pointerLockElement !== canvas && canvas.requestPointerLock) {
      try { const request = canvas.requestPointerLock(); if (request?.catch) void request.catch(() => undefined); } catch { /* Drag-to-look remains available in embedded previews. */ }
    } else if (event.pointerType !== 'mouse') canvas.setPointerCapture(event.pointerId);
  };

  private readonly pointerMove = (event: PointerEvent): void => {
    if (this.mode !== 'walk' || !this.model) return;
    const locked = document.pointerLockElement === this.renderer.domElement;
    if (!locked && !this.dragging) return;
    const x = locked ? event.movementX : event.clientX - this.dragX;
    const y = locked ? event.movementY : event.clientY - this.dragY;
    this.dragX = event.clientX;
    this.dragY = event.clientY;
    this.yaw -= x * 0.0027;
    this.pitch = THREE.MathUtils.clamp(this.pitch - y * 0.0027, -1.4, 1.4);
    this.camera.quaternion.setFromEuler(new THREE.Euler(this.pitch, this.yaw, 0, 'YXZ'));
    this.needsRender = true;
  };

  private readonly pointerUp = (): void => { this.dragging = false; this.renderer.domElement.style.cursor = 'grab'; };
  private readonly lockChange = (): void => { if (document.pointerLockElement !== this.renderer.domElement) this.blur(); };
  private readonly keyDown = (event: KeyboardEvent): void => {
    // Handle Escape before focus/mode guards. Embedded browsers and automated
    // input do not always perform the native pointer-lock exit themselves.
    if (event.code === 'Escape') {
      if (document.pointerLockElement === this.renderer.domElement) {
        document.exitPointerLock();
        event.preventDefault();
      }
      this.blur();
      return;
    }
    if (this.mode !== 'walk' || !this.model || document.activeElement !== this.renderer.domElement || document.querySelector('dialog[open]')) return;
    if (['KeyW', 'KeyA', 'KeyS', 'KeyD', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ShiftLeft', 'ShiftRight'].includes(event.code)) { event.preventDefault(); this.keys.add(event.code); }
  };
  private readonly keyUp = (event: KeyboardEvent): void => { this.keys.delete(event.code); };
  private readonly blur = (): void => { this.keys.clear(); this.movement.clear(); this.velocity.set(0, 0, 0); this.dragging = false; };

  private updateWalk(delta: number): void {
    if (!this.collision) return;
    if (document.querySelector('dialog[open]')) { this.blur(); return; }
    const forward = Number(this.keys.has('KeyW') || this.keys.has('ArrowUp') || this.movement.has('forward')) - Number(this.keys.has('KeyS') || this.keys.has('ArrowDown') || this.movement.has('backward'));
    const side = Number(this.keys.has('KeyD') || this.keys.has('ArrowRight') || this.movement.has('right')) - Number(this.keys.has('KeyA') || this.keys.has('ArrowLeft') || this.movement.has('left'));
    const direction = new THREE.Vector3(-Math.sin(this.yaw) * forward + Math.cos(this.yaw) * side, 0, -Math.cos(this.yaw) * forward - Math.sin(this.yaw) * side);
    if (direction.lengthSq() > 0) direction.normalize();
    const speed = this.keys.has('ShiftLeft') || this.keys.has('ShiftRight') ? 3.4 : 1.85;
    this.velocity.lerp(direction.multiplyScalar(speed), 1 - Math.exp(-14 * delta));
    if (this.velocity.lengthSq() < 0.000001) { this.velocity.set(0, 0, 0); return; }
    const step = this.velocity.clone().multiplyScalar(delta);
    const parts = Math.max(1, Math.ceil(step.length() / 0.065));
    const dx = step.x / parts, dz = step.z / parts;
    let blocked = false;
    for (let i = 0; i < parts; i++) {
      const x = this.camera.position.x, z = this.camera.position.z;
      if (this.canOccupy(x + dx, z + dz, this.collision)) { this.camera.position.x += dx; this.camera.position.z += dz; }
      else {
        blocked = true;
        if (this.canOccupy(x + dx, z, this.collision)) this.camera.position.x += dx;
        if (this.canOccupy(this.camera.position.x, z + dz, this.collision)) this.camera.position.z += dz;
      }
    }
    this.camera.position.y = this.collision.eyeHeight;
    if (blocked) { this.collisions++; this.container.dataset.collisionCount = String(this.collisions); }
    this.needsRender = true;
  }

  private clearModel(): void { if (this.model) { this.model.removeFromParent(); this.disposeGroup(this.model); this.model = null; } }

  private disposeGroup(group: THREE.Object3D): void {
    const geometries = new Set<THREE.BufferGeometry>(), materials = new Set<THREE.Material>(), textures = new Set<THREE.Texture>();
    group.traverse(object => {
      if (!(object instanceof THREE.Mesh)) return;
      geometries.add(object.geometry);
      for (const material of Array.isArray(object.material) ? object.material : [object.material]) { materials.add(material); for (const value of Object.values(material)) if (value instanceof THREE.Texture) textures.add(value); }
    });
    const images = new Set<ImageBitmap>();
    for (const geometry of geometries) geometry.dispose();
    for (const material of materials) material.dispose();
    for (const texture of textures) { if (typeof ImageBitmap !== 'undefined' && texture.image instanceof ImageBitmap) images.add(texture.image); texture.dispose(); }
    for (const image of images) image.close();
  }

  private readonly animate = (): void => {
    if (this.disposed) return;
    this.frame = requestAnimationFrame(this.animate);
    // Retain useful walking speed on slower GPUs; spatial substeps below
    // still limit every collision sweep to 6.5 cm, including long frames.
    const delta = Math.min(this.clock.getDelta(), 0.12);
    if (this.model) {
      if (this.mode === 'walk') this.updateWalk(delta);
      else if (this.mode === 'orbit' && this.controls.update()) this.needsRender = true;
    }
    if (this.needsRender) { this.needsRender = false; this.updatePoseData(); this.renderFrame(); }
  };
}
