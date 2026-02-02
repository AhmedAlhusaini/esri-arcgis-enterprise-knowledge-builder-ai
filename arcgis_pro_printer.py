import os
import re
import sys
import json
import time
from urllib.parse import unquote
from playwright.sync_api import sync_playwright
from pypdf import PdfWriter

# Force UTF-8
sys.stdout.reconfigure(encoding='utf-8')

# Config
START_URL = "https://pro.arcgis.com/en/pro-app/latest/arcpy/main/arcgis-pro-arcpy-reference.htm"
OUTPUT_DIR = "05Pro_ArcPyReference"
MERGED_FILENAME = "ArcGIS_Pro_ArcPyReference.pdf"

# Aggressive CSS to reveal everything and clean print
CSS_INJECT = """
/* Reveal all accordion content */
nav.accordion-content { display: block !important; height: auto !important; max-height: none !important; visibility: visible !important; opacity: 1 !important; }
aside.js-accordion .accordion-section { display: block !important; }
/* Hide unwanted elements */
#onetrust-banner-sdk, #onetrust-consent-sdk { display: none !important; }
/* Hide ALL headers (we inject specific content manually) */
header, footer, .site-header, .esri-footer, .global-footer, .grid-container > .column-24 { display: none !important; }
h1 { display: block !important; visibility: visible !important; opacity: 1 !important; color: black !important; }
aside.js-accordion, .column-5, .share-buttons, .feedback-container { display: none !important; }
/* Expand main content */
.column-17, .column-19, [class*="column-"] { width: 100% !important; margin: 0 !important; float: none !important; }
div[role="main"] { width: 100% !important; margin: 0 !important; }

/* Style for injected breadcrumbs */
.injected-breadcrumb { font-size: 10pt; color: #666; margin-bottom: 10px; }
.injected-breadcrumb a { color: #666; text-decoration: none; }
.injected-breadcrumb .crumb:after { content: " > "; margin: 0 5px; }
.injected-breadcrumb .crumb:last-child:after { content: ""; }
body { background-color: white !important; -webkit-print-color-adjust: exact; }
"""

def clean_filename(name):
    name = unquote(name)
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    name = name.replace(" ", "_").strip()
    return name[:80]

def merge_pdfs(root_dir, output_file):
    entries = []
    for root, dirs, files in os.walk(root_dir):
        for f in files:
            if f.endswith(".pdf"):
                entries.append(os.path.join(root, f))
    entries.sort()
    
    if not entries: return
    print(f"\n📦 Merging {len(entries)} pages into {output_file}...")
    
    merger = PdfWriter()
    for p in entries:
        try: merger.append(p)
        except: pass
        
    with open(output_file, "wb") as f_out:
        merger.write(f_out)
    print(f"✅ Created Combined PDF: {output_file}")

def run():
    if os.path.exists(OUTPUT_DIR):
        import shutil
        try: shutil.rmtree(OUTPUT_DIR)
        except: pass
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Init Hierarchy Log
    with open("pro_hierarchy.txt", "w", encoding="utf-8") as f:
        f.write("🌳 Full Detected Hierarchy\n==========================\n")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        print(f"🚀 Analyzing Site Structure from: {START_URL}")
        try:
            page.goto(START_URL, wait_until="networkidle", timeout=60000)
        except:
            print("⚠️ Timeout loading page, proceeding with DOM parse anyway...")
        
        # ------------------------------------------------------------------
        # HYBRID TREE PARSER
        # ------------------------------------------------------------------
        tree = page.evaluate("""() => {
            function parseNode(node, level) {
                let items = [];
                let children = Array.from(node.children);
                
                for (let i = 0; i < children.length; i++) {
                    let child = children[i];
                    
                    // SKIP Headers that are just titles (handled in group check)
                    if (child.classList.contains('accordion-title') || ['H3','H4'].includes(child.tagName)) continue;

                    // CASE 1: GROUP (Accordion/Header Container)
                    // Pro uses h4.accordion-title inside div.accordion-section
                    let headerEl = child.querySelector('.accordion-title') || child.querySelector('h3') || child.querySelector('h4');
                    let isGroup = child.classList.contains('accordion-section') || (headerEl && child.querySelector('.accordion-content'));
                    
                    if (isGroup) {
                        let titleEl = headerEl || child;
                        let groupTitle = titleEl.innerText.trim();
                        let contentEl = child.querySelector('.accordion-content');
                        let container = contentEl ? contentEl : child;
                        
                        let subItems = parseNode(container, level + 1);
                        subItems = subItems.filter(i => i.title !== groupTitle);
                        
                        // Check if needs expansion (empty children but has data-url or just is section)
                        let needsExpansion = child.hasAttribute('data-url') || (subItems.length === 0 && child.classList.contains('accordion-section'));
                        
                        if (subItems.length > 0 || needsExpansion) {
                             items.push({ type: 'group', title: groupTitle, children: subItems, needs_expansion: needsExpansion });
                             continue;
                        }
                    }
                    
                    // CASE 2: LI WRAPPER (Common in older docs, Pro uses div/nav mostly but good to keep)
                    if (child.tagName === 'LI') {
                        let link = child.querySelector(':scope > a');
                        if (!link) {
                            items = items.concat(parseNode(child, level)); 
                            continue;
                        }
                        let title = link.innerText.trim();
                        let url = link.href;
                        let subContainer = Array.from(child.children).filter(c => c !== link);
                        let subItems = [];
                        subContainer.forEach(c => subItems = subItems.concat(parseNode(c, level + 1)));
                        
                        if (subItems.length > 0) {
                            items.push({ type: 'group', title: title, url: url, children: subItems });
                        } else {
                            let isCollapsed = link.hasAttribute('data-collapsed') || link.classList.contains('icon-ui-right');
                            items.push({ type: 'link', title: title, url: url, is_collapsed: isCollapsed });
                        }
                        continue;
                    }

                    // CASE 3: FLATTEN WRAPPERS
                    if (['NAV','DIV','UL'].includes(child.tagName)) {
                        items = items.concat(parseNode(child, level));
                        continue;
                    }
                    
                    // CASE 4: LOOSE LINK
                    if (child.tagName === 'A') {
                         let isCollapsed = child.hasAttribute('data-collapsed') || child.classList.contains('icon-ui-right');
                         items.push({ type: 'link', title: child.innerText.trim(), url: child.href, is_collapsed: isCollapsed });
                    }
                }
                return items;
            }
            
            let root = document.querySelector('aside.js-accordion');
            if (!root) return [];
            return parseNode(root, 0);
        }""")
        
        # Save Debug JSON
        with open("pro_sidebar_debug.json", "w", encoding="utf-8") as f:
            json.dump(tree, f, indent=2)
        
        # ------------------------------------------------------------------
        # HELPER: SCRAPE ACTIVE CHILDREN (LAZY LOAD)
        # ------------------------------------------------------------------
        def get_active_children(pg):
            return pg.evaluate("""() => {
                // Re-use parseNode logic roughly
                function parseNode(node, level) {
                    let items = [];
                    let children = Array.from(node.children);
                    
                    for (let i = 0; i < children.length; i++) {
                        let child = children[i];
                        
                        if (['H1','H2','H3','H4','H5'].includes(child.tagName) || child.classList.contains('accordion-title')) continue;

                        if (child.classList.contains('accordion-section')) {
                             // Recurse into section content
                             let content = child.querySelector('.accordion-content') || child;
                             items = items.concat(parseNode(content, level + 1));
                             continue;
                        }
                        
                        if (child.tagName === 'LI') {
                            let link = child.querySelector(':scope > a');
                            if (link) {
                                let title = link.innerText.trim();
                                let url = link.href;
                                let isCollapsed = link.hasAttribute('data-collapsed') || link.classList.contains('icon-ui-right');
                                items.push({ type: 'link', title: title, url: url, is_collapsed: isCollapsed });
                            }
                            // Recurse for nested lists
                             let subContainer = Array.from(child.children).filter(c => c.tagName === 'UL' || c.tagName === 'DIV');
                             subContainer.forEach(c => items = items.concat(parseNode(c, level + 1)));
                            continue;
                        }
                        
                         // General Containers
                        if (['NAV','DIV','UL'].includes(child.tagName)) {
                            items = items.concat(parseNode(child, level));
                            continue;
                        }

                        // Direct Link
                        if (child.tagName === 'A') {
                             let isCollapsed = child.hasAttribute('data-collapsed') || child.classList.contains('icon-ui-right');
                             items.push({ type: 'link', title: child.innerText.trim(), url: child.href, is_collapsed: isCollapsed });
                        }
                    }
                    return items;
                }

                let items = [];
                
                // 1. Find the Active Element
                let activeEl = document.querySelector('.is-active');
                if (!activeEl) return [];

                // 2. Identify Scope (The Section/Container we are in)
                // If we are in an accordion content, we want everything in that content.
                let sectionContent = activeEl.closest('.accordion-content');
                let sectionWrapper = activeEl.closest('.accordion-section');
                
                // If NO specific section found (rare), maybe just siblings?
                let targetContainer = sectionContent || sectionWrapper;
                
                if (targetContainer) {
                    // We found a container. Parse it fully.
                    // This returns ALL siblings (including the active one).
                    // The python side handles deduplication of the active one via 'visited' set.
                    items = parseNode(targetContainer, 0);
                } else {
                     // Fallback: Just look for immediate sibling links if we are loose
                     // e.g. Side-nav-link
                     let parent = activeEl.parentElement;
                     if (parent) items = parseNode(parent, 0);
                }

                return items;
            }""")

        def get_expanded_group_children(pg, title):
            return pg.evaluate(f"""() => {{
                let headers = Array.from(document.querySelectorAll('.accordion-title'));
                let target = headers.find(h => h.innerText.trim() === {json.dumps(title)});
                if (!target) return [];
                let section = target.closest('.accordion-section');
                if (!section) return [];
                let content = section.querySelector('.accordion-content') || section.querySelector('nav');
                if (!content) return [];
                
                let items = [];
                content.querySelectorAll('a').forEach(a => {{
                     let isCollapsed = a.hasAttribute('data-collapsed') || a.classList.contains('icon-ui-right');
                     items.push({{ type: 'link', title: a.innerText.trim(), url: a.href, is_collapsed: isCollapsed }});
                }});
                return items;
            }}""")

        # ------------------------------------------------------------------
        # PRINT STRUCTURE PREVIEW
        # ------------------------------------------------------------------
        print("\n🌳 Detected Hierarchy (Preview):")
        
        def print_preview(items, indent=0):
            idx = 1
            for item in items:
                prefix = f"{idx:03d}" if indent > 0 else "---" 
                if item['type'] == 'group':
                    print(f"{'  '*indent}📂 [{prefix}] {item['title']}")
                    print_preview(item['children'], indent + 1)
                else:
                    print(f"{'  '*indent}📄 [{prefix}] {item['title']}")
                idx += 1
                
        print_preview(tree)
        print("\n⚡ Starting Hybrid Crawl...")

        # ------------------------------------------------------------------
        # CRAWLER
        # ------------------------------------------------------------------
        visited = set()
        expected_pdfs = {}
        
        def process_items(items, parent_path, level):
            idx = 1
            # Track first group for intro injection
            first_group_seen = False

            for item in items:
                # SPECIAL CASE: Intro is the first group at root level
                is_intro_group = False
                if level == 0 and item['type'] == 'group' and not first_group_seen:
                    is_intro_group = True
                    first_group_seen = True
                
                safe_title = clean_filename(item['title'])
                is_lazy_folder = (item['type'] == 'link') and item.get('is_collapsed', False)
                
                if item['type'] == 'group' or is_lazy_folder:
                    folder_name = f"{idx:03d}_{safe_title}"
                    idx += 1 
                    
                    new_path = os.path.join(parent_path, folder_name)
                    os.makedirs(new_path, exist_ok=True)
                    print(f"\n📂 Entering: {folder_name}")
                    
                    with open("pro_hierarchy.txt", "a", encoding="utf-8") as f:
                        f.write(f"{'  '*level}📂 {folder_name}\n")
                    
                    # 1. SPECIAL INTRO HANDLING
                    if is_intro_group:
                         pdf_name = f"000_Introduction.pdf"
                         pdf_path = os.path.join(new_path, pdf_name)
                         print(f"  ⚡ Printing Intro Page (Start URL): {pdf_name}")
                         try:
                             print_page(page, START_URL, pdf_path, item['title'])
                             visited.add(START_URL.split('#')[0])
                         except Exception as e:
                             print(f"  ❌ Error printing intro: {e}")

                    # 2. DYNAMIC EXPANSION (NEW)
                    if item.get('needs_expansion', False) and not item.get('children'):
                         print(f"  ⚡ Expanding Lazy Group: '{item['title']}'")
                         try:
                             # 1. Click ONLY if collapsed
                             page.evaluate(f"""() => {{
                                 let headers = Array.from(document.querySelectorAll('.accordion-title'));
                                 let target = headers.find(h => h.innerText.trim() === {json.dumps(item['title'])});
                                 if (target) {{
                                     let section = target.closest('.accordion-section');
                                     // If generic section or explicitly collapsed, click it.
                                     // Check if content is visible?
                                     let content = section.querySelector('.accordion-content');
                                     if (!content || content.style.display === 'none' || section.getAttribute('data-collapsed') === 'true') {{
                                         target.click();
                                     }}
                                 }}
                             }}""")
                             
                             # 2. Wait for content load (Network + DOM)
                             # Many of these trigger a fetch for a .js file
                             try:
                                 page.wait_for_load_state("networkidle", timeout=5000)
                             except: pass

                             # 3. Wait for 'a' tags to appear inside that specific section
                             # Find the section again by title text to be safe
                             try:
                                 xpath = f"//h4[contains(@class, 'accordion-title') and contains(normalize-space(.), {json.dumps(item['title'])})]/ancestor::div[contains(@class, 'accordion-section')]//nav//a"
                                 page.wait_for_selector(xpath, state="attached", timeout=5000)
                             except:
                                 print("    ⚠️ Wait for children timed out, checking anyway...")

                             # 4. Scrape new children
                             expanded_children = get_expanded_group_children(page, item['title'])
                             if expanded_children:
                                  print(f"  ✅ Found {len(expanded_children)} children after expansion")
                                  item['children'] = expanded_children
                             else:
                                  print(f"  ⚠️ No children found after expansion for {item['title']}")
                                  
                         except Exception as e:
                             print(f"  ❌ Failed to expand: {e}")

                    # 3. Lazy Folder Handling (Links)
                    if is_lazy_folder and 'url' in item:
                        landing_url = item['url']
                        # Intro PDF inside folder
                        pdf_name = f"000_Introduction.pdf"
                        pdf_path = os.path.join(new_path, pdf_name)
                        expected_pdfs[pdf_path] = landing_url
                        
                        if landing_url.split('#')[0] not in visited:
                             visited.add(landing_url.split('#')[0])
                             print(f"  ⚡ Printing Index: {pdf_name}")
                             try:
                                print_page(page, landing_url, pdf_path, item['title'])
                                
                                # Recursive check
                                print(f"  🔍 Checking for hidden children/siblings...")
                                lazy_children = get_active_children(page)
                                if lazy_children:
                                    print(f"  ✅ Found {len(lazy_children)} lazy children!")
                                    process_items(lazy_children, new_path, level + 1)
                                    
                             except Exception as e:
                                print(f"  ❌ Error: {e}")
                        else:
                             print(f"  🔍 Checking for hidden children (Visited)...")
                             try:
                                 page.goto(landing_url, wait_until="domcontentloaded")
                                 lazy_children = get_active_children(page)
                                 if lazy_children:
                                     process_items(lazy_children, new_path, level + 1)
                             except: pass

                    if 'children' in item:
                        process_items(item['children'], new_path, level + 1)
                    
                elif item['type'] == 'link':
                    # Only skip if truly redundant and don't burn an index
                    if item['url'].split('#')[0] in visited:
                        # Do NOT increment idx if skipped
                        continue
                    visited.add(item['url'].split('#')[0])
                    
                    pdf_name = f"{idx:03d}_{safe_title}.pdf"
                    idx += 1
                    pdf_path = os.path.join(parent_path, pdf_name)
                    expected_pdfs[pdf_path] = item['url']
                    
                    with open("pro_hierarchy.txt", "a", encoding="utf-8") as f:
                        f.write(f"{'  '*level}📄 {pdf_name}\n")
                    
                    print(f"  ⚡ Printing: '{item['title']}' -> {pdf_name}")
                    try:
                        print_page(page, item['url'], pdf_path, item['title'])
                    except Exception as e:
                         print(f"  ❌ Error: {e}")


        def print_page(pg, url, path, title):
             pg.goto(url, wait_until="networkidle", timeout=60000)
             pg.evaluate("document.querySelectorAll('details').forEach(e => e.open = true)")
             
             # INJECT BREADCRUMBS & TITLE
             pg.evaluate(f"""() => {{
                let title = {json.dumps(title)};
                // Possible main content containers in Pro docs
                let content = document.querySelector('div[role="main"]') || document.querySelector('.column-19') || document.querySelector('.column-17') || document.querySelector('main') || document.body;
                
                let targetH1 = document.querySelector('h1');
                let breadcrumbs = document.querySelector('nav.breadcrumbs');

                if (targetH1) {{
                    let newH1 = targetH1.cloneNode(true);
                    newH1.style.cssText = 'display: block !important; font-size: 24pt !important; font-weight: bold !important; margin-bottom: 20px !important; color: #000 !important; page-break-after: avoid !important; visibility: visible !important; opacity: 1 !important;';
                    content.prepend(newH1);
                }} else {{
                    let h1 = document.createElement('h1');
                    h1.innerText = title;
                    h1.style.cssText = 'display: block !important; font-size: 24pt !important; font-weight: bold !important; margin-bottom: 20px !important; color: #000 !important; page-break-after: avoid !important;';
                    content.prepend(h1);
                }}

                if (breadcrumbs) {{
                    let newBC = breadcrumbs.cloneNode(true);
                    newBC.classList.add('injected-breadcrumb');
                    newBC.style.cssText = 'display: block !important; font-size: 10pt !important; color: #666 !important; margin-bottom: 10px !important; visibility: visible !important; opacity: 1 !important;';
                    content.prepend(newBC);
                }}
             }}""")
             pg.add_style_tag(content=CSS_INJECT)
             pg.pdf(path=path, format="A4", margin={"top":"1cm","bottom":"1cm","left":"1cm","right":"1cm"})

        process_items(tree, OUTPUT_DIR, 0)
        
        # ------------------------------------------------------------------
        # VERIFICATION & RETRY
        # ------------------------------------------------------------------
        print("\n🕵️ Starting Integrity Check...")
        missing = []
        for path, url in expected_pdfs.items():
            if not os.path.exists(path) or os.path.getsize(path) < 1000:
                missing.append((path, url))
        
        if missing:
            print(f"⚠️ Found {len(missing)} missing or corrupted files. Retrying...")
            for path, url in missing:
                print(f"  🔄 Retrying: {os.path.basename(path)}")
                try:
                    fname = os.path.basename(path).replace(".pdf", "")
                    title = " ".join(fname.split("_")[1:])
                    print_page(page, url, path, title)
                    print("     ✅ Recovered!")
                except Exception as e:
                    print(f"     ❌ Retry Failed: {e}")
        else:
            print("✅ Integrity Check Passed: All files present.")

        browser.close()

    merge_pdfs(OUTPUT_DIR, MERGED_FILENAME)

if __name__ == "__main__":
    run()
