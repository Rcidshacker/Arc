/**
 * Arc Web smoke test — uses playwright-core + locally installed Chromium.
 * Run: node tests/run-tests.js
 */
const { chromium } = require('C:\\Users\\Lenovo\\AppData\\Roaming\\npm\\node_modules\\@playwright\\mcp\\node_modules\\playwright-core');
const path = require('path');
const fs = require('fs');

const BASE = 'http://localhost:8081';
const SS_DIR = path.join(__dirname, 'screenshots');
fs.mkdirSync(SS_DIR, { recursive: true });

async function ss(page, name) {
  const file = path.join(SS_DIR, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  console.log(`  📸 ${name}.png`);
}

async function run() {
  const browser = await chromium.launch({
    headless: true,
    executablePath: String.raw`C:\Users\Lenovo\AppData\Local\ms-playwright\chromium-1223\chrome-win64\chrome.exe`,
  });

  const errors = [];
  const warnings = [];

  try {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const page = await ctx.newPage();

    page.on('console', msg => {
      const t = msg.type();
      if (t === 'error') errors.push(msg.text());
      if (t === 'warning') warnings.push(msg.text());
    });
    page.on('pageerror', e => errors.push(`PAGE ERROR: ${e.message}`));

    // ── Test 1: initial load ──────────────────────────────────────────────
    console.log('\n[1] Initial load');
    await page.goto(BASE, { waitUntil: 'networkidle', timeout: 15000 });
    await page.waitForTimeout(2000);
    await ss(page, '01-initial-load');

    const rootHTML = await page.$eval('#root', el => el.innerHTML).catch(() => 'no #root');
    console.log('  #root length:', rootHTML.length);
    console.log('  #root snippet:', rootHTML.slice(0, 300));

    // ── Test 2: QRScanner web fallback ────────────────────────────────────
    console.log('\n[2] QRScanner screen check');
    await ss(page, '02-qrscanner');

    const inputEl = await page.$('input[placeholder*="192.168"]');
    const connectEl = await page.getByText('Connect').elementHandle().catch(() => null);
    console.log('  URL input present:', !!inputEl);
    console.log('  Connect button present:', !!connectEl);

    // ── Test 3: connect + navigate to Recorder ───────────────────────────
    console.log('\n[3] Connect flow');
    if (inputEl) {
      await inputEl.fill('http://localhost:8000');
      await ss(page, '03-url-entered');
      if (connectEl) await connectEl.click();
      await page.waitForTimeout(2000);
      await ss(page, '04-after-connect');

      const bodyText = await page.locator('body').textContent();
      console.log('  Body text:', bodyText?.slice(0, 200));
    } else {
      console.log('  Skipped — no input visible');
    }

    // ── Test 4: seed localStorage + reload → Recorder ────────────────────
    console.log('\n[4] Recorder screen (seeded URL)');
    await page.evaluate(() => {
      localStorage.setItem('arc_server_url', 'http://localhost:8000');
    });
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForTimeout(2000);
    await ss(page, '05-recorder-screen');

    const bodyText2 = await page.locator('body').textContent();
    console.log('  Body text:', bodyText2?.slice(0, 300));

    // ── Console summary ───────────────────────────────────────────────────
    console.log('\n=== CONSOLE ERRORS ===');
    if (errors.length === 0) console.log('  none');
    errors.forEach(e => console.log(' ', e));

    console.log('\n=== CONSOLE WARNINGS (first 10) ===');
    if (warnings.length === 0) console.log('  none');
    warnings.slice(0, 10).forEach(w => console.log(' ', w));
    if (warnings.length > 10) console.log(`  ...and ${warnings.length - 10} more`);

    await ctx.close();
  } finally {
    await browser.close();
  }
}

run().catch(err => {
  console.error('FATAL:', err.message);
  process.exit(1);
});
