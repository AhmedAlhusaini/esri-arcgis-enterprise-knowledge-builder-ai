# ArcGIS Documentation Scraper & Compiler

*Turn scattered web documentation into a unified, AI-ready Knowledge Base.*

This project is a high-performance scraping engine specifically designed to traverse, capture, and compile complex ArcGIS Enterprise documentation into clean, structured PDFs. It handles the quirks of modern dynamic websites—lazy-loaded sidebars, hidden headers, and deep nesting—to produce a single, comprehensive "Master Guide" for offline use or LLM ingestion , Custom GPTs , or just for your own knowledge base.

*This project sounds simple , I know but belive me it multiplies into a lot of other projects. Also multiplay your productivity and troubleshooting into x5 at least.*

> **Again ; Why this matters:** Building a local knowledge base (for RAG, NotebookLM, or custom GPTs) requires clean data. This tool multiplies your productivity x5 by automating the "gather" phase of learning and documentation.

---

## 🚀 Key Features

- **Hybrid Tree Parser**: Combines static DOM analysis with active CSS crawling to map the entire site structure, even parts hidden behind "click-to-expand" menus.
- **Deep Recursion**: Intelligent traversal that detects and expands "lazy" folders to infinite depth, ensuring no child page is left behind.
- **precision PDF Rendering**:
    - **Header Injection**: Automatically extracts Breadcrumbs and the *correct* Page Title (even from hidden hero banners) and injects them into the PDF for perfect context.
    - **Zero Duplicates**: Smartly hides redundant web headers while preserving the content hierarchy.
- **Auto-Merge**: Instantly combines hundreds of captured pages into a single, bookmarked PDF file.

---

## 📋 How to Use

### 1. Setup
Ensure you have Python 3.8+ and the necessary dependencies:

```bash
pip install playwright pypdf
playwright install chromium
```

### 2. Configure
Open `full_site_printer.py` and set your target:

```python
# Config Section
START_URL = "https://enterprise.arcgis.com/en/server/latest/develop/windows/about-extending-services.htm"
OUTPUT_DIR = "04Server/Develop"  # Where the individual PDFs will go
MERGED_FILENAME = "ArcGIS For Server Develop Guide.pdf" # Final output name
```

### 3. Run
```bash
python full_site_printer.py
```

The script will:
1.  **Analyze** the sidebar structure.
2.  **Crawl** every page, printing them to PDF.
3.  **Merge** them all into one file in the root directory.

---

## 🧠 Technical Walkthrough

This isn't just a simple link follower. It allows for **Smart Traversal**:

### 1. The Structure Analysis
The script doesn't just click links blindly. It first parses the `aside.js-accordion` sidebar to build a JSON tree of the documentation hierarchy. It identifies:
- **Groups**: Sections that contain children.
- **Lazy Links**: Links that *look* like files but expand into folders when clicked.

### 2. The "Active State" Heuristic
To solve the "Deep Nesting" problem (where sidebars only load children when you visit the parent), the script uses a robust heuristic:
- It visits a page.
- It scans the sidebar for the "active" link.
- It checks for **indentation** and **DOM structure** changes to detect if new children have suddenly appeared.
- If they have, it recursively adds them to the crawl queue.

### 3. Precision Printing
Web pages are terrible for printing. This script applies a "print stylesheet" on the fly:
- **Hides** global navigation, detailed footers, and cookie banners.
- **Injects** a clean header stack: `[Breadcrumbs] > [Page Title]`.
- **Relocates** titles: It finds the H1 (even if hidden in a Hero banner) and moves it to the main content area so your PDF title matches the web page exactly.

---

## 📂 Project Structure

- **`full_site_printer.py`**: The core engine. Contains the crawler, printer, and merger logic.
- **`archive/`**: Contains legacy scripts (`dump_sidebar.py`, `manual_merge.py`) kept for reference.
- **`Outputs/`**: Temporary storage for raw scraped PDFs.
- **`full_hierarchy.txt`**: A generated log showing the tree structure found during the scan.

---

## 🔮 Future Enhancements

- **Parallel Processing**: Use `asyncio` to scrape multiple pages concurrently (speed boost).
- **Markdown Export**: Output clean Markdown instead of PDF for easier RAG ingestion.
- **Incremental Updates**: Only re-scrape pages that have changed since the last run.
- **Config file**: Move configuration to a `.env` or `yaml` file for easier swapping of documentation sets.

---

## 🤝 Contributing

This tool was built with passion to solve a real pain point. If you have ideas for optimization or new features (like supporting other documentation sites), please fork and submit a PR!

1.  Fork the Project
2.  Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3.  Commit your Changes
4.  Push to the Branch
5.  Open a Pull Request

## Author 
*Ahmed Tarek Alhusainy*

*Happy Studying , Happy Preparing For ESRI Cetificates & Happy Leverage AI into your knowledage Base !*

