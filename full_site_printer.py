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
START_URL = "https://esri.github.io/arcgis-cookbook/"
OUTPUT_DIR = "Outputs/06ArcGIS Enterprise In The Cloud/ArcGIS Cookbook"
MERGED_FILENAME = "Outputs/06ArcGIS Enterprise In The Cloud/ArcGIS Cookbook.pdf"

# Aggressive CSS to reveal everything and clean print
CSS_INJECT = """
/* Reveal all accordion content */
nav.accordion-content { display: block !important; height: auto !important; max-height: none !important; visibility: visible !important; opacity: 1 !important; }
aside.js-accordion .accordion-section { display: block !important; }

/* Reveal Calcite components & Shadow DOM equivalents (Cookbook/Enterprise) */
calcite-tree, calcite-tree-item, [calcite-hydrated-hidden] { visibility: visible !important; display: block !important; opacity: 1 !important; height: auto !important; max-height: none !important; pointer-events: auto !important; }
calcite-accordion, calcite-accordion-item, calcite-panel, calcite-block { visibility: visible !important; display: block !important; opacity: 1 !important; height: auto !important; max-height: none !important; }
.calcite-tree-children, [slot="children"], [slot="content"] { display: block !important; visibility: visible !important; opacity: 1 !important; }

/* Hide unwanted elements */
#onetrust-banner-sdk, #onetrust-consent-sdk { display: none !important; }
/* Hide ALL headers (we inject specific content manually) */
header, footer, .site-header, .esri-footer, .global-footer { display: none !important; }
h1 { display: block !important; visibility: visible !important; opacity: 1 !important; color: black !important; }

/* Hide sidebars from PDF print out */
aside.js-accordion, .column-5, .share-buttons, .feedback-container, .shell-panel, calcite-shell-panel { display: none !important; }
.column-17 { width: 100% !important; margin: 0 !important; }

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
    with open("full_hierarchy.txt", "w", encoding="utf-8") as f:
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
                    
                    // SKIP Headers
                    if (child.classList.contains('accordion-title') || ['H3','H4'].includes(child.tagName)) continue;

                    // CASE 1: GROUP (Accordion/Header Container or Calcite Group)
                    let headerEl = child.querySelector('.accordion-title') || child.querySelector('h3') || child.querySelector('h4');
                    let isCalciteGroup = child.tagName === 'CALCITE-TREE-ITEM' && child.hasAttribute('has-children');
                    let isGroup = child.classList.contains('accordion-section') || headerEl || isCalciteGroup;
                    
                    if (isGroup) {
                        let groupTitle = "";
                        if (isCalciteGroup) {
                            // Extract direct text for Calcite Tree group
                            let textContent = "";
                            for (let node of child.childNodes) {
                                if (node.nodeType === Node.TEXT_NODE) textContent += node.textContent;
                            }
                            groupTitle = textContent.trim();
                            if (!groupTitle) {
                                let link = child.querySelector(':scope > a');
                                if (link) groupTitle = link.innerText.trim() || link.textContent.trim();
                            }
                        } else {
                            let titleEl = headerEl || child;
                            groupTitle = titleEl.innerText.trim() || titleEl.textContent.trim();
                        }
                        
                        let contentEl = child.querySelector('.accordion-content') || child.querySelector('calcite-tree');
                        let container = contentEl ? contentEl : child;
                        
                        let subItems = parseNode(container, level + 1);
                        subItems = subItems.filter(i => i.title !== groupTitle);
                        
                        if (subItems.length > 0 || child.classList.contains('accordion-section') || isCalciteGroup) {
                             items.push({ type: 'group', title: groupTitle, children: subItems });
                             continue;
                        }
                    }
                    
                    // CASE 2: LI WRAPPER OR CALCITE LEAF
                    if (child.tagName === 'LI' || (child.tagName === 'CALCITE-TREE-ITEM' && !child.hasAttribute('has-children'))) {
                        let link = child.querySelector(':scope > a');
                        if (!link) {
                            items = items.concat(parseNode(child, level)); 
                            continue;
                        }
                        let title = link.innerText.trim() || link.textContent.trim();
                        let url = link.href;
                        let subContainer = Array.from(child.children).filter(c => c !== link);
                        let subItems = [];
                        subContainer.forEach(c => subItems = subItems.concat(parseNode(c, level + 1)));
                        
                        if (subItems.length > 0) {
                            items.push({ type: 'group', title: title, url: url, children: subItems });
                        } else {
                            // Check for Collapsed Hint
                            let isCollapsed = link.hasAttribute('data-collapsed') || link.classList.contains('icon-ui-right');
                            items.push({ type: 'link', title: title, url: url, is_collapsed: isCollapsed });
                        }
                        continue;
                    }

                    // CASE 3: FLATTEN WRAPPERS
                    if (['NAV','DIV','UL','CALCITE-TREE'].includes(child.tagName)) {
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
            
            let root = document.querySelector('aside.js-accordion') || document.querySelector('.shell-panel .toc calcite-tree') || document.querySelector('calcite-tree');
            if (!root) return [];
            return parseNode(root, 0);
        }""")
        
        # Save Debug JSON
        with open("sidebar_debug.json", "w", encoding="utf-8") as f:
            json.dump(tree, f, indent=2)
        
        # ------------------------------------------------------------------
        # HELPER: SCRAPE ACTIVE CHILDREN (LAZY LOAD)
        # ------------------------------------------------------------------

        def get_active_children(pg):
            return pg.evaluate("""() => {
                let items = [];
                
                // 1. Try to find if active item is now a HEADER (Accordion Title)
                // In some views, clicking a link promotes it to a section header.
                let activeHeader = document.querySelector('.accordion-title.is-active, .accordion-section.is-active > .accordion-title');
                if (activeHeader) {
                    let section = activeHeader.closest('.accordion-section');
                    let content = section.querySelector('.accordion-content');
                    if (content) {
                        content.querySelectorAll('a').forEach(a => {
                             let isCollapsed = a.hasAttribute('data-collapsed') || a.classList.contains('icon-ui-right');
                             items.push({ type: 'link', title: a.innerText.trim(), url: a.href, is_collapsed: isCollapsed });
                        });
                        return items;
                    }
                }

                // 2. Standard Link: Check for Indented Siblings
                // FIX: Select the DEEPEST active link, not just the first one.
                let allActive = Array.from(document.querySelectorAll('aside.js-accordion a.is-active'));
                let activeLink = allActive[allActive.length - 1]; // Last one is deepest
                
                if (!activeLink) return [];
                
                let activeRect = activeLink.getBoundingClientRect();
                let activeLeft = activeRect.left;
                
                // Get all links in the sidebar
                let allLinks = Array.from(document.querySelectorAll('aside.js-accordion a'));
                let startIndex = allLinks.indexOf(activeLink);
                
                if (startIndex === -1) return [];
                
                // Scan forward
                for (let i = startIndex + 1; i < allLinks.length; i++) {
                    let link = allLinks[i];
                    
                    // Skip if hidden
                    if (link.offsetParent === null) continue;
                    
                    let linkRect = link.getBoundingClientRect();
                    
                    // HEURISTIC: Indentation > Active Link Indentation (+ margin)
                    // Or if it's in a strictly nested container (UL inside LI)
                    
                    let isNested = (linkRect.left > activeLeft + 2); // At least 2px indented
                    let isSameGroup = (link.closest('.accordion-section') === activeLink.closest('.accordion-section'));
                    
                    // If we hit a new section, stop
                    if (!isSameGroup) break;
                    
                    if (isNested) {
                        let isCollapsed = link.hasAttribute('data-collapsed') || link.classList.contains('icon-ui-right');
                        items.push({ type: 'link', title: link.innerText.trim(), url: link.href, is_collapsed: isCollapsed });
                    } else {
                        // Returned to same level or higher -> Stop
                        break;
                    }
                }
                
                // 3. Fallback: Check for immediate sibling container (Link + Nav pattern)
                // This catches the case where indentation might be subtle but DOM is structurally clear
                if (items.length === 0) {
                     let siblingNav = activeLink.nextElementSibling;
                     if (siblingNav && ['NAV','UL','DIV'].includes(siblingNav.tagName)) {
                         siblingNav.querySelectorAll('a').forEach(a => {
                             let isCollapsed = a.hasAttribute('data-collapsed') || a.classList.contains('icon-ui-right');
                             items.push({ type: 'link', title: a.innerText.trim(), url: a.href, is_collapsed: isCollapsed });
                         });
                     }
                }
                
                return items;
            }""")

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

        # ------------------------------------------------------------------
        # INTEGRITY TRACKER
        # ------------------------------------------------------------------
        expected_pdfs = {} # path -> url
        
        def process_items(items, parent_path, level):
            idx = 1
            for item in items:
                safe_title = clean_filename(item['title'])
                
                # Check for LAZY DEEPENING condition
                is_lazy_folder = (item['type'] == 'link') and item.get('is_collapsed', False)
                
                if item['type'] == 'group' or is_lazy_folder:
                    # Unified Indexing for ALL levels (User Request)
                    folder_name = f"{idx:03d}_{safe_title}"
                    idx += 1 
                    
                    new_path = os.path.join(parent_path, folder_name)
                    os.makedirs(new_path, exist_ok=True)
                    print(f"\n📂 Entering: {folder_name}")
                    
                    # LOG HIERARCHY
                    with open("full_hierarchy.txt", "a", encoding="utf-8") as f:
                        f.write(f"{'  '*level}📂 {folder_name}\n")
                    
                    # For Lazy Folders, index page
                    if is_lazy_folder and 'url' in item:
                        landing_url = item['url']
                        pdf_name = f"000_Introduction.pdf"
                        pdf_path = os.path.join(new_path, pdf_name)
                        expected_pdfs[pdf_path] = landing_url
                        
                        if landing_url.split('#')[0] not in visited:
                             visited.add(landing_url.split('#')[0])
                             print(f"  ⚡ Printing Index: {pdf_name}")
                             try:
                                print_page(page, landing_url, pdf_path, item['title'])
                                
                                # SCRAPE CHILDREN NOW
                                print(f"  🔍 Checking for hidden children...")
                                lazy_children = get_active_children(page)
                                if lazy_children:
                                    print(f"  ✅ Found {len(lazy_children)} lazy children!")
                                    process_items(lazy_children, new_path, level + 1)
                                    
                             except Exception as e:
                                print(f"  ❌ Error: {e}")
                    
                    if 'children' in item:
                        process_items(item['children'], new_path, level + 1)
                    
                elif item['type'] == 'link':
                    if item['url'].split('#')[0] in visited:
                        idx += 1
                        continue
                    visited.add(item['url'].split('#')[0])
                    
                    pdf_name = f"{idx:03d}_{safe_title}.pdf"
                    idx += 1
                    pdf_path = os.path.join(parent_path, pdf_name)
                    expected_pdfs[pdf_path] = item['url']
                    
                    # LOG HIERARCHY
                    with open("full_hierarchy.txt", "a", encoding="utf-8") as f:
                        f.write(f"{'  '*level}📄 {pdf_name}\n")
                    
                    print(f"  ⚡ Printing: '{item['title']}' -> {pdf_name}")
                    try:
                        print_page(page, item['url'], pdf_path, item['title'])
                    except Exception as e:
                         print(f"  ❌ Error: {e}")

        def print_page(pg, url, path, title):
             pg.goto(url, wait_until="networkidle", timeout=60000)
             pg.evaluate("document.querySelectorAll('details').forEach(e => e.open = true)")
             # INJECT TITLE
             # INJECT HEADER (Breadcrumbs + Title)
             pg.evaluate(f"""() => {{
                let title = {json.dumps(title)};
                let content = document.querySelector('main') || document.querySelector('.column-17') || document.body;
                
                // 1. Prepare Content Elements
                let targetH1 = document.querySelector('header.trailer-1 h1') || document.querySelector('h1');
                let breadcrumbs = document.querySelector('nav.breadcrumbs');

                // 2. Insert TITLE (Prepend first, so it ends up below breadcrumbs)
                if (targetH1) {{
                    // Clone and clean up style
                    let newH1 = targetH1.cloneNode(true);
                    newH1.style.cssText = 'display: block !important; font-size: 24pt !important; font-weight: bold !important; margin-bottom: 20px !important; color: #000 !important; page-break-after: avoid !important; visibility: visible !important; opacity: 1 !important;';
                    content.prepend(newH1);
                }} else {{
                    // Fallback Title
                    let h1 = document.createElement('h1');
                    h1.innerText = title;
                    h1.style.cssText = 'display: block !important; font-size: 24pt !important; font-weight: bold !important; margin-bottom: 20px !important; color: #000 !important; page-break-after: avoid !important;';
                    content.prepend(h1);
                }}

                // 3. Insert BREADCRUMBS (Prepend last, so it stays at very top)
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
            if not os.path.exists(path) or os.path.getsize(path) < 1000: # <1KB is suspicious
                missing.append((path, url))
        
        if missing:
            print(f"⚠️ Found {len(missing)} missing or corrupted files. Retrying...")
            for path, url in missing:
                print(f"  🔄 Retrying: {os.path.basename(path)}")
                try:
                    # Determine title from path or fallback
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
