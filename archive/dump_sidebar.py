from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://enterprise.arcgis.com/en/portal/latest/use/get-started-portal.htm", wait_until="networkidle")
        
        # Expand
        page.evaluate("document.querySelectorAll('.accordion-section:not(.is-active)').forEach(s => s.classList.add('is-active'))")
        
        html = page.evaluate("""() => {
            let el = document.querySelector('aside.js-accordion');
            return el ? el.outerHTML : 'Not Found';
        }""")
        
        with open("sidebar_dump.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("Done.")
        browser.close()

if __name__ == "__main__":
    run()
