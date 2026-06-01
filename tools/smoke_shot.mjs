// tools/smoke_shot.mjs — screenshot each dashboard tab in light/dark + mobile.
// Uses the Chromium already cached by Playwright. Run: node tools/smoke_shot.mjs
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';
import { resolve } from 'node:path';

const OUT = '/tmp/smoke';
mkdirSync(OUT, { recursive: true });
const url = pathToFileURL(resolve('public/index.html')).href;
const tabs = ['costs', 'plan', 'activity', 'sessions', 'insights'];

const browser = await chromium.launch();
for (const [theme, w, h, tag] of [['light', 1440, 1000, 'desk'], ['dark', 1440, 1000, 'desk'], ['light', 420, 900, 'mob']]) {
  const page = await browser.newPage({ viewport: { width: w, height: h } });
  await page.goto(url, { waitUntil: 'networkidle' });
  await page.evaluate(t => {
    document.documentElement.classList.remove('theme-light', 'theme-dark');
    document.documentElement.classList.add('theme-' + t);
  }, theme);
  for (const tab of tabs) {
    await page.evaluate(name => window.activateTabByName && window.activateTabByName(name, false), tab);
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${OUT}/${tag}-${theme}-${tab}.png`, fullPage: tag !== 'mob' });
  }
  await page.close();
}
await browser.close();
console.log('screenshots in', OUT);
