"""
Paper figure captured from the dashboard (the blind-accuracy scatter), so the paper and the dashboard show the same charts.

Each card is lifted out of the built page, stripped of what only makes sense on the web (title,
toggles, the NDVI slider), and screenshotted at 4x. The LaTeX caption carries the explanation.

Usage (from the repo root, after `npm run build` in dashboard/):
    python -m http.server 8765 --bind 127.0.0.1 --directory dashboard/out &
    uv run --no-project --with playwright python dashboard/scripts/paper_figures.py docs/figures
"""
import sys
from playwright.sync_api import sync_playwright
out = sys.argv[1]

ISOLATE = """([title, width, twoCol]) => {
  const h3 = [...document.querySelectorAll('.card h3')].find(e => e.textContent.trim() === title);
  const card = h3.closest('.card');
  const host = document.createElement('div');
  host.id = 'paperhost';
  host.style.cssText = `position:absolute;left:0;top:0;width:${width}px;z-index:99999;background:#fff;padding:0`;
  document.body.appendChild(host);
  host.appendChild(card);
  [...document.body.children].forEach(c => { if (c !== host && c.tagName !== 'SCRIPT') c.style.display = 'none'; });
  card.querySelectorAll('h3, .sub, .controls, .calc, .note, .table-view').forEach(e => e.remove());
  card.style.cssText += ';height:auto;min-height:0;border:none;box-shadow:none;background:#fff;padding:4px 6px;margin:0';
  if (twoCol) {
    const kids = [...card.children];
    const left = document.createElement('div'), right = document.createElement('div');
    kids.forEach(k => {
      if (k.matches('ol.steps') || k.matches('.formula')) left.appendChild(k);
      else if (k.matches('.takeaway') || k.querySelector('svg')) right.appendChild(k);
      else k.remove();
    });
    card.style.cssText += ';display:grid;grid-template-columns:1.05fr 1fr;column-gap:26px;align-items:start';
    card.append(left, right);
    left.querySelector('.formula').style.margin = '6px 0 0';
    right.querySelector('.takeaway').style.margin = '6px 0 0';
  } else {
    const t = card.querySelector('.takeaway'); if (t) t.remove();
  }
  window.scrollTo(0, 0);
  window.dispatchEvent(new Event('resize'));
}"""

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    for title, name, width, two in [
        ("Satellite estimate against the field value", "fig_dash_blind", 560, False),
    ]:
        pg = b.new_page(viewport={"width": 1300, "height": 1000}, device_scale_factor=4, color_scheme="light")
        pg.goto("http://127.0.0.1:8765/", wait_until="networkidle")
        pg.evaluate("document.documentElement.setAttribute('data-theme','light')")
        pg.evaluate(ISOLATE, [title, width, two])
        pg.wait_for_timeout(600)
        pg.locator("#paperhost").screenshot(path=f"{out}/{name}.png")
        print(name, pg.locator("#paperhost").bounding_box())
        pg.close()
    b.close()
