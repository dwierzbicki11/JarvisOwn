// Optional browser regression: node tests/study_ui.cjs (requires Playwright + Chromium).
// HTTP responses are deterministic; this test never calls a live model or device.
const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({headless: true});
  try {
    const context = await browser.newContext({viewport: {width: 1024, height: 1000}});
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const html = fs.readFileSync(path.join(__dirname, '../gui/study.html'), 'utf8');
    let current = null, recent = [], posts = [];
    const receipts = new Map();
    await context.route('http://jarvis.test/**', async route => {
      const request = route.request(), url = new URL(request.url());
      let body;
      if (url.pathname === '/study') return route.fulfill({contentType: 'text/html', body: html});
      if (url.pathname === '/api/study/session') body = {current, recent};
      else if (url.pathname === '/api/command') {
        posts.push(request.postDataJSON().text);
        const id = posts.length;
        receipts.set(id, {id, state: 'processing', answer: null});
        body = {id, ok: true};
      } else if (url.pathname.startsWith('/api/commands/')) body = receipts.get(Number(url.pathname.split('/').at(-1)));
      else throw Error('Unexpected URL: ' + url);
      await route.fulfill({contentType: 'application/json', body: JSON.stringify(body)});
    });
    const ready = id => page.waitForFunction(id => !document.getElementById(id).disabled, id);
    const finish = async (answer, readyId) => {
      const id = posts.length;
      receipts.set(id, {id, state: 'done', answer});
      await ready(readyId);
    };

    await page.goto('http://jarvis.test/study');
    await ready('start');
    await page.locator('#subject').selectOption('programowanie');
    await page.locator('#goal').fill('Pętle w Pythonie');
    await page.locator('#start').click();
    await page.waitForFunction(() => sessionStorage.getItem('jarvis-study-command'));
    assert.equal(posts.length, 1);
    assert.match(posts[0], /programowanie; quiz; podstawowy; Pętle w Pythonie/);
    assert.equal(await page.locator('#start').isDisabled(), true);

    current = {id: 1, subject: 'programowanie', mode: 'quiz', level: 'podstawowy', state: 'active',
      goal: 'Pętle w Pythonie', exam: 0, question: '<img src=x onerror="window.injected=true"> Co wypisze pętla?',
      feedback: '', awaiting_answer: 1, correct: 0, partial: 0, wrong: 0, hints: 0, skipped: 0,
      started_at: '2026-10-08T10:00:00Z'};
    recent = [current];
    // A reload must retain the receipt without re-sending the start request.
    await page.reload();
    await finish('Pytanie gotowe.', 'send-answer');
    assert.equal(posts.length, 1);
    assert.equal(await page.locator('#question img').count(), 0);
    assert.match(await page.locator('#question').textContent(), /<img/);
    assert.equal(await page.evaluate(() => window.injected), undefined);

    const code = 'for i in range(3):\n    print(i)';
    await page.locator('#answer').fill(code);
    await page.locator('#send-answer').click();
    await page.waitForFunction(() => sessionStorage.getItem('jarvis-study-command'));
    assert.equal(posts[1], 'odpowiedź w sesji: ' + code);
    await finish('Model jest teraz niedostępny.', 'send-answer');
    assert.equal(await page.locator('#answer').inputValue(), code);
    assert.match(await page.locator('#notice').textContent(), /niedostępny/);

    await page.locator('#send-answer').click();
    await page.waitForFunction(() => sessionStorage.getItem('jarvis-study-command'));
    current.awaiting_answer = 0;
    current.correct = 1;
    current.feedback = 'Poprawnie.';
    await finish('Ocena modelu: poprawna.', 'next');
    assert.equal(await page.locator('#answer').inputValue(), '');
    assert.equal(await page.locator('#send-answer').isDisabled(), true);
    assert.match(await page.locator('#score').textContent(), /Poprawne: 1/);

    await page.locator('#pause').click();
    await page.waitForFunction(() => sessionStorage.getItem('jarvis-study-command'));
    current.state = 'paused';
    await finish('Sesja wstrzymana.', 'resume');
    assert.equal(await page.locator('#next').isDisabled(), true);
    await page.locator('#resume').click();
    await page.waitForFunction(() => sessionStorage.getItem('jarvis-study-command'));
    current.state = 'active';
    await finish('Sesja wznowiona.', 'next');

    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    if (process.env.JARVIS_UI_SCREENSHOT) await page.screenshot({path: process.env.JARVIS_UI_SCREENSHOT, fullPage: true});
    await page.locator('#stop').click();
    await page.waitForFunction(() => sessionStorage.getItem('jarvis-study-command'));
    current.state = 'finished';
    current = null;
    await finish('Sesja zakończona.', 'start');
    assert.equal(await page.locator('#session').isVisible(), false);
    assert.match(await page.locator('#history').textContent(), /zakończona/);
    assert.deepEqual(errors, []);
    console.log('PASS: tutoring panel, receipts/reload, model failure, multiline answer, score, pause/resume, mobile layout, safe rendering.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
