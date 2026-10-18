import { test, expect } from '@playwright/test';

test('renders the sample and supports exploration controls and help', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.locator('#viewer canvas')).toBeVisible();
  await expect(page.locator('#scene-error')).toBeHidden();
  await expect(page.getByRole('button', { name: 'Create 3D view' })).toBeDisabled();
  await expect(page.getByRole('button', { name: 'Point cloud' })).toBeDisabled();
  await page.getByRole('button', { name: 'Walk through', exact: true }).click();
  await expect(page.locator('#walk-mode')).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('button', { name: 'Move forward' })).toBeVisible();
  await page.getByRole('button', { name: 'Move forward' }).dispatchEvent('pointerdown', { pointerId: 1 });
  await page.getByRole('button', { name: 'Move forward' }).dispatchEvent('pointerup', { pointerId: 1 });
  await page.getByRole('button', { name: 'Reset view' }).click();
  await page.getByRole('button', { name: 'Orbit', exact: true }).click();
  await expect(page.locator('#orbit-mode')).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'How it works' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByRole('button', { name: 'Let’s explore' }).click();
  await expect(page.getByRole('dialog')).toBeHidden();
  await page.screenshot({ path: 'test-results/studio-desktop.png', fullPage: true });
  expect(errors).toEqual([]);
});

test('upload performs real inference and builds a navigable photo mesh', async ({ page, request }) => {
  const health = await request.get('/api/health');
  expect(health.ok(), 'Start the Python backend before running this test').toBeTruthy();
  expect((await health.json()).ready).toBeTruthy();
  await page.goto('/');
  // A varied architectural scene exercises real depth inference, not a mocked API.
  const png = await page.evaluate(() => {
    const canvas = document.createElement('canvas');
    canvas.width = 640; canvas.height = 400;
    const ctx = canvas.getContext('2d')!;
    ctx.fillStyle = '#bed4e6'; ctx.fillRect(0, 0, 640, 400);
    ctx.fillStyle = '#c9c5b9'; ctx.fillRect(0, 0, 200, 400);
    ctx.fillStyle = '#777c7d'; ctx.beginPath(); ctx.moveTo(0, 400); ctx.lineTo(260, 160); ctx.lineTo(640, 160); ctx.lineTo(640, 400); ctx.fill();
    ctx.fillStyle = '#393e42'; ctx.fillRect(0, 0, 640, 50);
    ctx.fillStyle = '#d9d3be'; ctx.fillRect(480, 50, 24, 240);
    ctx.fillStyle = '#c84823'; ctx.fillRect(300, 200, 140, 85);
    ctx.fillStyle = '#303c45'; ctx.fillRect(310, 208, 120, 30);
    ctx.fillStyle = '#171d21'; ctx.beginPath(); ctx.arc(325, 288, 18, 0, 7); ctx.arc(415, 288, 18, 0, 7); ctx.fill();
    return canvas.toDataURL().split(',')[1];
  });
  await page.locator('#photo-input').setInputFiles({ name: 'my-space.png', mimeType: 'image/png', buffer: Buffer.from(png, 'base64') });
  await expect(page.locator('#photo-name')).toHaveText('my-space.png');
  await expect(page.locator('#generate')).toBeEnabled();
  await page.locator('#generate').click();
  await expect(page.locator('#scene-badge')).toHaveText('ESTIMATED DEPTH', { timeout: 60_000 });
  await expect(page.locator('#upload-error')).toBeHidden();
  await expect(page.locator('#scene-name')).toHaveText('my-space');
  await page.locator('#point-cloud').click();
  await expect(page.locator('#point-cloud')).toHaveAttribute('aria-pressed', 'true');
  await page.locator('#walk-mode').click();
  await expect(page.locator('#walk-mode')).toHaveAttribute('aria-pressed', 'true');
  await page.locator('#reset').click();
  await page.screenshot({ path: 'test-results/studio-photo.png', fullPage: true });
  await page.locator('#example').click();
  await expect(page.locator('#scene-badge')).toHaveText('SAMPLE SPACE');
  await expect(page.locator('#point-cloud')).toBeDisabled();
});

test('rejects invalid uploads and reports backend errors', async ({ page }) => {
  await page.goto('/');
  await page.locator('#photo-input').setInputFiles({ name: 'document.txt', mimeType: 'text/plain', buffer: Buffer.from('not an image') });
  await expect(page.locator('#upload-error')).toHaveText('Choose a JPG, PNG or WebP image.');
  const image = await page.evaluate(() => { const c = document.createElement('canvas'); c.width = 256; c.height = 256; return c.toDataURL().split(',')[1]; });
  await page.locator('#photo-input').setInputFiles({ name: 'photo.png', mimeType: 'image/png', buffer: Buffer.from(image, 'base64') });
  await page.route('**/api/depth', route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Depth model is missing. Run python -m backend.download_model.' }) }));
  await page.locator('#generate').click();
  await expect(page.locator('#upload-error')).toContainText('Depth model is missing.');
  await expect(page.locator('#generate')).toBeEnabled();
  await page.locator('#remove-photo').click();
  await expect(page.locator('#generate')).toBeDisabled();
});

test('mobile workspace fits the viewport and exposes touch movement', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  await expect(page.locator('#viewer canvas')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await page.locator('#walk-mode').click();
  await expect(page.getByRole('button', { name: 'Move forward' })).toBeVisible();
  await page.screenshot({ path: 'test-results/studio-mobile.png', fullPage: true });
});
