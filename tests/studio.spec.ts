import { test, expect, type Page, type APIRequestContext } from '@playwright/test';
import { createHash } from 'node:crypto';
import { mkdir, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import type { SceneDescriptor } from '../src/viewer';

// These tests exercise the hosted server, authenticated proxy, durable worker,
// actual image analysis, Blender subprocess, exported GLB and browser renderer.
// Run against the production-style stack using TITAN_TEST_BASE_URL and (when
// required) TITAN_TEST_SITE_PASSWORD. No reconstruction response is mocked.
const production = Boolean(process.env.TITAN_TEST_BASE_URL);
const evidence = fileURLToPath(new URL('../validation/results/', import.meta.url));
const completed: Record<string, { geometry: string; materials: string; image: string }> = {};
interface Project {
  id: string; jobId: string; state: string; stage: string; progress: number;
  revision: number; error?: string; scene: SceneDescriptor;
  artifacts: Record<string, string>;
}
const hash = (value: string | Buffer) => createHash('sha256').update(value).digest('hex');
const position = async (page: Page) => JSON.parse(await page.locator('#viewer').getAttribute('data-camera-position') || '[]') as number[];
const withinFloor = ([x, z]: number[], polygon: number[][]) => {
  let inside = false;
  for (let i = 0, j = polygon.length - 1; i < polygon.length; j = i++) {
    const a = polygon[i], b = polygon[j];
    if ((a[1] > z) !== (b[1] > z) && x < (b[0] - a[0]) * (z - a[1]) / (b[1] - a[1]) + a[0]) inside = !inside;
  }
  return inside;
};
async function finished(request: APIRequestContext, id: string, stages: Set<string>): Promise<Project> {
  const deadline = Date.now() + 255_000;
  while (Date.now() < deadline) {
    const response = await request.get(`/api/projects/${id}`);
    expect(response.ok(), 'Persisted project status must remain available').toBeTruthy();
    const item = await response.json() as Project;
    stages.add(item.stage);
    if (item.state === 'completed') return item;
    if (item.state === 'failed' || item.state === 'cancelled') throw new Error(`Actual reconstruction ${item.state}: ${item.error || item.stage}`);
    await new Promise(resolve => setTimeout(resolve, 1500));
  }
  throw new Error('Actual photo analysis and Blender reconstruction did not finish within 255 seconds.');
}
async function moveAtLeast(page: Page, key: string, distance: number): Promise<number[]> {
  const before = await position(page);
  await page.locator('#viewer canvas').focus();
  await page.keyboard.down(key);
  try {
    await expect.poll(async () => {
      const current = await position(page);
      return Math.hypot(current[0] - before[0], current[2] - before[2]);
    }, { timeout: 8000, intervals: [100, 200, 400], message: `${key} must move the actual camera at least ${distance} m, including on a slow software GPU` }).toBeGreaterThanOrEqual(distance);
  } finally { await page.keyboard.up(key); }
  return position(page);
}

test.describe('production photo → Blender → GLB walkthrough', () => {
  test.skip(!production, 'Start the production-style hosted server and worker, then set TITAN_TEST_BASE_URL.');
  for (const label of ['warehouse', 'room']) {
    test(`${label}: actual upload, pending reconnect, textured model and grounded navigation`, async ({ page, request }) => {
      test.setTimeout(300_000);
      await mkdir(evidence, { recursive: true });
      const photo = fileURLToPath(new URL(`../validation/photos/${label}.jpg`, import.meta.url));
      const errors: string[] = [];
      let submissions = 0;
      const stages = new Set<string>();
      page.on('pageerror', error => errors.push(error.message));
      page.on('request', outgoing => { if (outgoing.method() === 'POST' && new URL(outgoing.url()).pathname === '/api/projects') submissions++; });
      const health = await request.get('/healthz');
      expect(health.ok()).toBeTruthy();
      const readiness = await request.get('/api/projects/status');
      expect(readiness.ok()).toBeTruthy();
      const worker = await readiness.json();
      expect(worker.configured, 'A real reconstruction worker must be connected').toBe(true);
      expect(worker.workerReachable, 'The worker must be reachable').not.toBe(false);
      expect(worker.setupRequired, 'Install Blender and real model files before integration tests').not.toBe(true);
      await page.goto('/');
      await expect(page.locator('#worker-title')).toHaveText('Reconstruction worker ready');
      await page.locator('#photo-input').setInputFiles(photo);
      await expect(page.locator('#original-photo')).toBeVisible();
      await expect(page.locator('#scene-badge')).toHaveText('ORIGINAL PHOTO');
      const uploadResponse = page.waitForResponse(response => response.request().method() === 'POST' && new URL(response.url()).pathname === '/api/projects', { timeout: 20_000 });
      const submittedAt = Date.now();
      await page.locator('#generate').click();
      const accepted = await uploadResponse;
      const acceptedAfterMs = Date.now() - submittedAt;
      expect(accepted.status()).toBe(202);
      expect(acceptedAfterMs, 'Upload must return a saved job ID before Blender finishes').toBeLessThan(10_000);
      const queued = await accepted.json() as Project;
      expect(queued.id).toMatch(/^[0-9a-f-]{36}$/);
      expect(queued.jobId).toMatch(/^[0-9a-f-]{36}$/);
      expect(['queued', 'running']).toContain(queued.state);
      stages.add(queued.stage);
      await expect.poll(() => page.evaluate(() => localStorage.getItem('titan.projects.selected.v1'))).toBe(queued.id);
      await page.reload();
      await expect(page.locator(`.project-item[data-project-id="${queued.id}"]`)).toHaveClass(/selected/);
      await expect(page.locator('#scene-name')).toHaveText(label);
      const reconnected = await request.get(`/api/projects/${queued.id}`);
      expect((await reconnected.json()).jobId).toBe(queued.jobId);
      expect(submissions, 'Reloading must reconnect instead of submitting a duplicate upload').toBe(1);
      const item = await finished(request, queued.id, stages);
      expect(item.scene?.room.floor_polygon.length).toBeGreaterThanOrEqual(3);
      expect(item.progress).toBe(100);
      expect(item.stage).toBe('completed');
      expect(stages.size).toBeGreaterThanOrEqual(2);
      for (const name of ['glb', 'blend', 'scene', 'preview', 'manifest']) expect(item.artifacts[name], `Worker must persist ${name}`).toBeTruthy();
      const manifestResponse = await request.get(item.artifacts.manifest);
      expect(manifestResponse.ok()).toBeTruthy();
      const manifest = await manifestResponse.json();
      expect(manifest.builder).toMatch(/Blender/);
      expect(manifest.blender_version).toMatch(/^\d+\.\d+/);
      expect(manifest.validation?.has_real_meshes).toBe(true);
      expect(manifest.validation?.embedded_textures).toBe(true);
      const modelResponse = await request.get(item.artifacts.glb);
      expect(modelResponse.ok()).toBeTruthy();
      const glb = await modelResponse.body();
      expect(glb.subarray(0, 4).toString()).toBe('glTF');
      expect(glb.readUInt32LE(4)).toBe(2);
      const document = JSON.parse(glb.subarray(20, 20 + glb.readUInt32LE(12)).toString());
      expect(document.meshes.length).toBeGreaterThan(2);
      expect(document.images.length).toBeGreaterThan(0);
      expect(document.images.every((image: { bufferView?: number }) => Number.isInteger(image.bufferView)), 'Textures must be embedded in the served GLB').toBe(true);
      const blendResponse = await request.get(item.artifacts.blend);
      expect(blendResponse.ok()).toBeTruthy();
      expect((await blendResponse.body()).subarray(0, 7).toString()).toBe('BLENDER');
      const previewResponse = await request.get(item.artifacts.preview);
      expect(previewResponse.ok()).toBeTruthy();
      await writeFile(`${evidence}${label}.glb`, glb);
      await writeFile(`${evidence}${label}.blend`, await blendResponse.body());
      await writeFile(`${evidence}${label}-blender.png`, await previewResponse.body());
      await writeFile(`${evidence}${label}-scene.json`, JSON.stringify(item.scene, null, 2) + '\n');
      await writeFile(`${evidence}${label}-manifest.json`, JSON.stringify(manifest, null, 2) + '\n');
      await expect(page.locator('#viewer')).toHaveAttribute('data-load-state', 'ready', { timeout: 35_000 });
      await expect(page.locator('#scene-error')).toBeHidden();
      await expect(page.locator('#error')).toBeHidden();
      await expect(page.locator('#viewer canvas')).toBeVisible();
      const meshes = Number(await page.locator('#viewer').getAttribute('data-model-mesh-count'));
      const textures = Number(await page.locator('#viewer').getAttribute('data-texture-count'));
      expect(meshes).toBeGreaterThan(2);
      expect(textures).toBeGreaterThan(0);
      await page.locator('#source-mode').click();
      await expect(page.locator('#compare-original')).toBeVisible();
      await expect.poll(() => page.locator('#comparison-photo').evaluate(image => (image as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
      const sourcePosition = await position(page);
      sourcePosition.forEach((value, axis) => expect(value).toBeCloseTo(item.scene.camera.position[axis], 3));
      expect(Number(await page.locator('#viewer').getAttribute('data-camera-aspect'))).toBeCloseTo(item.scene.camera.aspect, 4);
      await page.locator('.viewer-panel').screenshot({ path: `${evidence}${label}-source.png` });
      await page.locator('#walk-mode').click();
      await expect(page.locator('#viewer')).toHaveAttribute('data-camera-mode', 'walk');
      const start = await position(page);
      const sideways = await moveAtLeast(page, 'KeyA', 0.15);
      expect(Math.hypot(sideways[0] - start[0], sideways[2] - start[2]), 'A must move the actual camera sideways').toBeGreaterThanOrEqual(0.1);
      expect(sideways[1]).toBeCloseTo(start[1], 3);
      const walked = await moveAtLeast(page, 'KeyW', 0.5);
      await page.locator('.viewer-panel').screenshot({ path: `${evidence}${label}-walk.png` });
      const collisionsBefore = Number(await page.locator('#viewer').getAttribute('data-collision-count'));
      await page.locator('#viewer canvas').focus();
      await page.keyboard.down('KeyW');
      try {
        await expect.poll(async () => Number(await page.locator('#viewer').getAttribute('data-collision-count')), { timeout: 20_000 }).toBeGreaterThan(collisionsBefore);
      } finally { await page.keyboard.up('KeyW'); }
      const blocked = await position(page);
      expect(blocked[1]).toBeCloseTo(start[1], 3);
      expect(withinFloor([blocked[0], blocked[2]], item.scene.room.floor_polygon), 'Wall/floor collision must keep the camera inside modeled ground').toBe(true);
      const backwards = await moveAtLeast(page, 'KeyS', 0.35);
      expect(Math.hypot(backwards[0] - blocked[0], backwards[2] - blocked[2]), 'S must let the camera move back from the wall').toBeGreaterThanOrEqual(0.1);
      // Look back across the modeled room from the advanced walking position.
      // Resetting to the entry before turning would mostly show the exterior.
      const canvas = page.locator('#viewer canvas');
      const quaternionBeforeLook = await page.locator('#viewer').getAttribute('data-camera-quaternion');
      await canvas.click();
      const locked = await page.evaluate(() => document.pointerLockElement?.tagName === 'CANVAS');
      if (locked) await canvas.dispatchEvent('pointermove', { pointerType: 'mouse', movementX: Math.PI / 0.0027, movementY: 0 });
      else {
        const bounds = await canvas.boundingBox(); expect(bounds).not.toBeNull();
        // Embedded previews can use drag-to-look when pointer lock is denied.
        await page.mouse.move(bounds!.x + bounds!.width * 0.75, bounds!.y + bounds!.height * 0.5);
        await page.mouse.down();
        await page.mouse.move(bounds!.x + bounds!.width * 0.25, bounds!.y + bounds!.height * 0.5, { steps: 15 });
        await page.mouse.up();
      }
      await page.keyboard.press('Escape');
      await expect.poll(() => page.evaluate(() => document.pointerLockElement === null), { timeout: 3000, message: 'Escape must release the mouse before toolbar interaction' }).toBe(true);
      await expect.poll(() => page.locator('#viewer').getAttribute('data-camera-quaternion')).not.toBe(quaternionBeforeLook);
      const lookBack = await position(page);
      await page.locator('.viewer-panel').screenshot({ path: `${evidence}${label}-back.png` });
      await page.locator('#reset').click();
      await expect.poll(async () => { const current = await position(page); return Math.hypot(current[0] - start[0], current[1] - start[1], current[2] - start[2]); }).toBeLessThan(0.01);
      const resetPosition = await position(page);
      await page.reload();
      await expect(page.locator('#viewer')).toHaveAttribute('data-load-state', 'ready', { timeout: 35_000 });
      expect(submissions).toBe(1);
      const listing = await request.get('/api/projects');
      const projects = (await listing.json()).projects as { id: string }[];
      expect(projects.filter(project => project.id === queued.id)).toHaveLength(1);
      const signature = {
        geometry: hash(JSON.stringify({ room: item.scene.room, objects: item.scene.objects })),
        materials: hash(JSON.stringify(item.scene.materials)), image: item.scene.source!.sha256,
      };
      completed[label] = signature;
      if (label === 'room' && completed.warehouse) {
        expect(signature.image).not.toBe(completed.warehouse.image);
        expect(signature.geometry, 'Different photographs must drive different room/object geometry').not.toBe(completed.warehouse.geometry);
        expect(signature.materials, 'Different photographs must drive different material estimates').not.toBe(completed.warehouse.materials);
      }
      await writeFile(`${evidence}${label}-browser.json`, JSON.stringify({ projectId: item.id, jobId: item.jobId, acceptedAfterMs, stages: [...stages], meshes, textures, glbSha256: hash(glb), sourcePosition, start, sideways, walked, blocked, backwards, lookBack, resetPosition, signature, pageErrors: errors }, null, 2) + '\n');
      expect(errors).toEqual([]);
    });
  }

  test('authenticated production API rejects invalid photos and malformed project IDs', async ({ request }) => {
    const invalid = await request.post('/api/projects', { multipart: { photo: { name: 'invalid.jpg', mimeType: 'image/jpeg', buffer: Buffer.from('not a decodable photo') } } });
    expect(invalid.status()).toBe(422);
    expect((await invalid.json()).detail).toMatch(/image|photo|decode/i);
    const malformed = await request.get('/api/projects/not-a-project');
    expect(malformed.status()).toBe(422);
  });
});
