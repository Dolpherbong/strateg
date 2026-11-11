"""Публичный просмотр без ввода данных, заказа и оплаты."""
from pathlib import Path
import json
import sys
from playwright.sync_api import sync_playwright

sys.stdout.reconfigure(encoding='utf-8')
project = Path(__file__).resolve().parents[3]
cache = project / '.cache'
screens = project / 'inbox' / 'screens'
screens.mkdir(exist_ok=True)
with sync_playwright() as pw:
    browser = pw.chromium.launch(channel='chrome', headless=True)
    context = browser.new_context(viewport={'width': 1440, 'height': 1000}, locale='ru-RU')
    page = context.new_page()
    try:
        page.goto('https://moskva.beeline.ru/travel-esim/', wait_until='domcontentloaded', timeout=30000)
        page.wait_for_timeout(2500)
        text = page.locator('body').inner_text(timeout=10000)
        (cache / 'beeline-browser-home.txt').write_text(text, encoding='utf-8')
        shot = screens / 'beeline-01-home.png'
        if not shot.exists():
            page.screenshot(path=str(shot), full_page=True)
        print('URL:', page.url)
        print(text[:14000])
        print('BUTTONS:', json.dumps(page.get_by_role('button').all_text_contents(), ensure_ascii=False))
        links = page.locator('a').evaluate_all('(els) => els.map(e => ({text:e.innerText, href:e.href})).filter(x => x.href.includes("esim"))')
        print('LINKS:', json.dumps(links, ensure_ascii=False))
    except Exception as exc:
        (cache / 'beeline-browser-error.txt').write_text(str(exc), encoding='utf-8')
        print(type(exc).__name__, str(exc)[:1000])
        raise
    finally:
        browser.close()
