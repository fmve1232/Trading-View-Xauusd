// Browser audit of the site at phone / tablet / desktop sizes: console errors, failed requests, horizontal overflow,
// overlapping or clipped text in key panels, decision label presence, stale / closed-market labelling. Screenshots at scale 1.
const { chromium } = require('playwright');
(async () => {
  const out = process.argv[2]; const base = 'http://127.0.0.1:8765/';
  const browser = await chromium.launch();
  const sizes = [['phone', 390, 844], ['tablet', 768, 1024], ['desktop', 1440, 900]];
  const report = {};
  for (const [name, w, h] of sizes) {
    const ctx = await browser.newContext({ viewport: { width: w, height: h }, deviceScaleFactor: 1 });
    const page = await ctx.newPage();
    const errors = [], failed = [];
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text().slice(0, 200)); });
    page.on('pageerror', e => errors.push('PAGEERROR ' + String(e).slice(0, 200)));
    page.on('response', r => { if (r.status() >= 400) failed.push(r.status() + ' ' + r.url().replace(base, '')); });
    await page.goto(base + 'index.html', { waitUntil: 'networkidle' });
    await page.waitForTimeout(2500);
    const m = await page.evaluate(() => {
      const de = document.documentElement;
      const overflowX = de.scrollWidth - window.innerWidth;
      const wide = [...document.querySelectorAll('body *')].filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.right > window.innerWidth + 2 && getComputedStyle(e).position !== 'fixed'; })
        .slice(0, 8).map(e => (e.id ? '#' + e.id : e.tagName.toLowerCase() + '.' + [...e.classList].join('.')) + ' right=' + Math.round(e.getBoundingClientRect().right));
      const clipped = [...document.querySelectorAll('body *')].filter(e => { const s = getComputedStyle(e); return e.children.length === 0 && e.textContent.trim().length > 3 && (s.overflow === 'hidden' || s.textOverflow === 'ellipsis') && e.scrollWidth > e.clientWidth + 1; }).slice(0, 8).map(e => e.textContent.trim().slice(0, 50));
      const txt = document.body.innerText;
      const has = k => txt.includes(k);
      return { overflowX, wide, clipped, height: de.scrollHeight, words: { WAIT: has('WAIT'), 'NO TRADE': has('NO TRADE'), BUY: has('BUY'), SELL: has('SELL'), stale: /stale|STALE|closed|CLOSED|not live|NOT LIVE/.test(txt), 'NOT CALIBRATED': /NOT CALIBRATED|not calibrated/.test(txt), probability: /probabilit/i.test(txt), UNVERIFIED: /UNVERIFIED/.test(txt) }, sections: [...document.querySelectorAll('h2, h3, .card-title, summary')].slice(0, 60).map(e => e.textContent.trim().slice(0, 40)) };
    });
    await page.screenshot({ path: `${out}/${name}_top.png` });
    await page.screenshot({ path: `${out}/${name}_full.png`, fullPage: true });
    report[name] = { errors: errors.slice(0, 10), failed: [...new Set(failed)].slice(0, 12), ...m };
    await ctx.close();
  }
  await browser.close();
  console.log(JSON.stringify(report, null, 1));
})();
