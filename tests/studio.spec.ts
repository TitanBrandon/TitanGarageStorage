import { test, expect, type Page } from '@playwright/test';
import { fileURLToPath } from 'node:url';

const fixture = fileURLToPath(new URL('./fixtures/captured-scene.spz', import.meta.url));

async function provider(page: Page, configured = false) {
  await page.route('**/api/worlds/status', route => route.fulfill({ json: { configured, provider: 'World Labs' } }));
}
async function selectPhoto(page: Page) {
  const image = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = 320; canvas.height = 200;
    const context = canvas.getContext('2d')!;
    context.fillStyle = '#b3c9d6'; context.fillRect(0, 0, 320, 200);
    context.fillStyle = '#e3d9c5'; context.fillRect(0, 0, 120, 200);
    context.fillStyle = '#54636b'; context.fillRect(0, 140, 320, 60);
    return canvas.toDataURL().split(',')[1];
  });
  await page.locator('#photo-input').setInputFiles({ name: 'my-garage.png', mimeType: 'image/png', buffer: Buffer.from(image, 'base64') });
}

test('starts empty, preserves the real photo and blocks generation without a key', async ({ page }) => {
  await provider(page);
  await page.goto('/');
  await expect(page.locator('#empty-state')).toBeVisible();
  await expect(page.locator('#viewer')).toHaveAttribute('data-splat-count', '0');
  await expect(page.locator('#provider-title')).toHaveText('Connect World Labs');
  await expect(page.locator('#walk-mode')).toBeDisabled();
  await selectPhoto(page);
  await expect(page.locator('#original-photo')).toBeVisible();
  await expect(page.locator('#scene-badge')).toHaveText('ORIGINAL PHOTO');
  await expect(page.locator('#generate')).toBeDisabled();
  await expect(page.getByText('Covered showroom', { exact: true })).toHaveCount(0);
  await page.screenshot({ path: 'test-results/original-photo.png', fullPage: true });
});

test('imports and visibly renders a real captured SPZ scene with working navigation', async ({ page }) => {
  test.setTimeout(120_000);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await provider(page);
  await page.goto('/');
  const canvas = page.locator('#viewer canvas');
  await page.locator('#splat-input').setInputFiles(fixture);
  await expect(page.locator('#viewer')).toHaveAttribute('data-splat-count', '30000', { timeout: 90_000 });
  await expect(page.locator('#scene-badge')).toHaveText('IMPORTED 3D SCENE');
  await expect(page.locator('#empty-state')).toBeHidden();
  await expect(page.locator('#error')).toBeHidden();
  await expect(canvas).toBeVisible();
  await page.locator('#walk-mode').click();
  await canvas.focus();
  const beforeWalk = await canvas.screenshot();
  await page.keyboard.down('KeyW');
  await page.waitForTimeout(350);
  await page.keyboard.up('KeyW');
  const afterWalk = await canvas.screenshot();
  expect(afterWalk.equals(beforeWalk), 'Walking must change the rendered camera view').toBe(false);
  await page.locator('#reset').click();
  await expect(page.locator('#flip-world')).toBeVisible();
  await page.locator('#flip-world').click();
  await expect(page.locator('#viewer')).toHaveAttribute('data-splat-count', '30000');
  await page.screenshot({ path: 'test-results/captured-splat.png', fullPage: true });
  expect(errors).toEqual([]);
});

test('mocked paid submission polls once and offers the genuine provider viewer fallback', async ({ page }) => {
  await provider(page, true);
  let submissions = 0;
  await page.route('**/api/worlds', async route => {
    submissions++;
    expect(route.request().method()).toBe('POST');
    expect(route.request().postData()).toContain('name="quality"');
    expect(route.request().postData()).toContain('plus');
    await route.fulfill({ status: 202, json: { operationId: 'test-op' } });
  });
  await page.route('**/api/worlds/operations/test-op', route => route.fulfill({ json: { state: 'ready', worldId: 'test-world', worldUrl: 'https://marble.worldlabs.ai/world/test-world' } }));
  await page.goto('/');
  await selectPhoto(page);
  await expect(page.locator('#generate')).toBeEnabled();
  await page.locator('#generate').click();
  await expect(page.locator('#open-marble')).toBeVisible();
  await expect(page.locator('#open-marble')).toHaveAttribute('href', 'https://marble.worldlabs.ai/world/test-world');
  await expect(page.locator('#viewer')).toHaveAttribute('data-splat-count', '0');
  expect(submissions).toBe(1);
});

test('refresh resumes the saved operation without a second paid submission', async ({ page }) => {
  await provider(page, true);
  let submissions = 0;
  await page.route('**/api/worlds', route => { submissions++; return route.fulfill({ status: 202, json: { operationId: 'existing-op' } }); });
  await page.route('**/api/worlds/operations/existing-op', route => route.fulfill({ json: { state: 'pending' } }));
  await page.goto('/');
  await selectPhoto(page);
  await page.locator('#generate').click();
  await expect(page.locator('#stop-checking')).toBeVisible();
  await page.reload();
  await expect(page.locator('#stop-checking')).toBeVisible();
  await expect(page.locator('#generate')).toBeDisabled();
  expect(submissions).toBe(1);
  await page.locator('#stop-checking').click();
  await expect(page.locator('#resume-checking')).toBeVisible();
});

test('uncertain submission is retained across reload instead of retrying a billable request', async ({ page }) => {
  await provider(page, true);
  let submissions = 0;
  await page.route('**/api/worlds', route => { submissions++; return route.fulfill({ status: 504, json: { detail: 'Submission timed out. World Labs may have accepted it.' } }); });
  await page.goto('/');
  await selectPhoto(page);
  await page.locator('#generate').click();
  await expect(page.locator('#error')).toContainText('may already be running');
  await page.reload();
  await expect(page.locator('#generate')).toBeDisabled();
  expect(submissions).toBe(1);
});

test('mobile layout fits and malformed photos cannot start paid generation', async ({ page }) => {
  await provider(page, true);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await page.locator('#photo-input').setInputFiles({ name: 'notes.txt', mimeType: 'text/plain', buffer: Buffer.from('not a photograph') });
  await expect(page.locator('#error')).toHaveText('Choose a JPG, PNG or WebP image.');
  await expect(page.locator('#generate')).toBeDisabled();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: 'test-results/mobile-worlds.png', fullPage: true });
});
