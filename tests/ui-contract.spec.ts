import { test, expect, type Page } from '@playwright/test';
import { fileURLToPath } from 'node:url';

// Small presentation contracts deliberately simulate an unavailable worker.
// Actual reconstruction and navigation are covered by studio.spec.ts against
// the real hosted server + Blender worker, without mocked processing results.
async function unavailableWorker(page: Page) {
  await page.route('**/api/projects/status', route => route.fulfill({ json: { configured: false, workerReachable: false, setupRequired: true, message: 'Connect a Blender worker with durable project storage.' } }));
  await page.route('**/api/projects', route => route.fulfill({ json: { projects: [] } }));
}

test('unavailable worker leaves a real uploaded photo visible and generation disabled', async ({ page }) => {
  await unavailableWorker(page);
  await page.goto('/');
  await expect(page.locator('#worker-title')).toHaveText('Reconstruction worker needed');
  await expect(page.locator('#viewer')).toHaveAttribute('data-load-state', 'empty');
  await expect(page.locator('#viewer canvas')).toBeHidden();
  await page.locator('#photo-input').setInputFiles(fileURLToPath(new URL('../validation/photos/room.jpg', import.meta.url)));
  await expect(page.locator('#original-photo')).toBeVisible();
  await expect(page.locator('#scene-badge')).toHaveText('ORIGINAL PHOTO');
  await expect(page.locator('#generate')).toBeDisabled();
  await expect(page.locator('#walk-mode')).toBeDisabled();
  await expect(page.locator('#source-mode')).toBeDisabled();
  await expect(page.locator('#worker-setup')).toBeVisible();
});

test('rejects a non-photo locally and explains the reconstruction limits', async ({ page }) => {
  await unavailableWorker(page);
  await page.goto('/');
  await page.locator('#photo-input').setInputFiles({ name: 'document.txt', mimeType: 'text/plain', buffer: Buffer.from('not an image') });
  await expect(page.locator('#error')).toHaveText('Choose a JPG, PNG or WebP image.');
  await expect(page.locator('#viewer')).toHaveAttribute('data-model-mesh-count', '0');
  await page.locator('#help').click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByRole('dialog')).toContainText('Hidden surfaces, exact dimensions');
  await page.locator('#got-it').click();
  await expect(page.getByRole('dialog')).toBeHidden();
});

test('mobile upload and worker explanation fit the viewport', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await unavailableWorker(page);
  await page.goto('/');
  await expect(page.locator('#worker-title')).toHaveText('Reconstruction worker needed');
  await expect(page.locator('#empty-upload')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.screenshot({ path: 'test-results/blender-mobile-empty.png', fullPage: true });
});
