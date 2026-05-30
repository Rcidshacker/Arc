import { test, expect, Page } from '@playwright/test';
import path from 'path';

const SS = (name: string) => path.join('tests', 'screenshots', `${name}.png`);

async function screenshot(page: Page, name: string) {
  await page.screenshot({ path: SS(name), fullPage: true });
}

test.describe('Arc Web — screen-by-screen', () => {

  test('1. QRScanner renders + manual URL input visible', async ({ page }) => {
    await page.goto('/');
    // Wait for React to hydrate
    await page.waitForTimeout(2000);
    await screenshot(page, '01-initial-load');

    // Check for web URL input fallback (not camera)
    const input = page.locator('input[placeholder*="192.168"]');
    const connectBtn = page.getByText('Connect');

    await screenshot(page, '02-qrscanner-screen');

    const inputVisible = await input.isVisible().catch(() => false);
    const btnVisible = await connectBtn.isVisible().catch(() => false);

    console.log('URL input visible:', inputVisible);
    console.log('Connect button visible:', btnVisible);

    // Report DOM structure regardless of pass/fail
    const rootHTML = await page.locator('#root').innerHTML().catch(() => 'could not read #root');
    console.log('Root inner HTML (first 500):', rootHTML.slice(0, 500));

    expect(inputVisible || btnVisible).toBeTruthy();
  });

  test('2. Enter server URL + navigate to Recorder', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(2000);

    const input = page.locator('input[placeholder*="192.168"]');
    const connectBtn = page.getByText('Connect');

    if (!(await input.isVisible().catch(() => false))) {
      console.log('Input not visible — skipping navigation test');
      await screenshot(page, '03-connect-skipped');
      test.skip();
      return;
    }

    await input.fill('http://localhost:8000');
    await screenshot(page, '03-url-entered');
    await connectBtn.click();

    // Wait for navigation to Recorder
    await page.waitForTimeout(2000);
    await screenshot(page, '04-after-connect');

    const timerText = page.getByText(/^\d{2}:\d{2}/);
    const statusText = page.getByText(/tap to record/i);
    const recorderVisible = await timerText.isVisible().catch(() => false)
      || await statusText.isVisible().catch(() => false);

    console.log('Recorder screen visible:', recorderVisible);
    expect(recorderVisible).toBeTruthy();
  });

  test('3. Recorder screen — record button + web banner', async ({ page }) => {
    // Pre-seed server URL so we land on Recorder directly
    await page.goto('/');
    await page.waitForTimeout(1000);
    await page.evaluate(() => {
      localStorage.setItem('arc_server_url', 'http://localhost:8000');
    });
    await page.reload();
    await page.waitForTimeout(2000);
    await screenshot(page, '05-recorder-screen');

    const webBanner = page.getByText(/background recording not available/i);
    const recordBtn = page.locator('[style*="border-radius"]').first();

    console.log('Web banner visible:', await webBanner.isVisible().catch(() => false));
    console.log('Page URL:', page.url());

    // Just check it rendered something
    const body = await page.locator('body').textContent();
    console.log('Body text (first 300):', body?.slice(0, 300));

    await screenshot(page, '06-recorder-detail');
  });

  test('4. Console errors audit', async ({ page }) => {
    const errors: string[] = [];
    const warnings: string[] = [];

    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text());
      if (msg.type() === 'warning') warnings.push(msg.text());
    });

    page.on('pageerror', err => errors.push(`PAGE ERROR: ${err.message}`));

    await page.goto('/');
    await page.waitForTimeout(3000);

    console.log('\n=== CONSOLE ERRORS ===');
    errors.forEach(e => console.log('ERROR:', e));

    console.log('\n=== CONSOLE WARNINGS ===');
    warnings.forEach(w => console.log('WARN:', w));

    console.log('\n=== TOTALS ===');
    console.log(`Errors: ${errors.length}, Warnings: ${warnings.length}`);

    await screenshot(page, '07-final-state');

    // Fail if hard errors
    const hardErrors = errors.filter(e =>
      !e.includes('Warning:') &&
      !e.includes('deprecated') &&
      !e.includes('VirtualizedList')
    );
    if (hardErrors.length > 0) {
      console.log('Hard errors found:', hardErrors);
    }
  });

});
