#!/usr/bin/env python3
"""
PageIndex — Vectorless RAG Runner for Research & Innovation
=============================================================

Process financial documents (SEC filings, earnings reports, strategy research)
into a hierarchical tree index for agentic QA. No vector embeddings needed —
uses LLM reasoning over the structured index.

Usage:
  # Process a PDF document (e.g. SEC filing)
  python run_pageindex.py --pdf_path /path/to/filing.pdf

  # Process a Markdown document (e.g. research notes)
  python run_pageindex.py --md_path /path/to/strategy.md

  # With custom LLM model (overrides config.yaml)
  python run_pageindex.py --pdf_path filing.pdf --model "anthropic/claude-sonnet-4-6"

Options:
  --pdf_path PATH           Path to the PDF file (SEC filing, earnings report)
  --md_path PATH            Path to the Markdown file (strategy research, notes)
  --model MODEL             LLM model to use (e.g. gpt-4o, anthropic/claude-sonnet-4-6)
  --toc-check-pages N       Pages to scan for table of contents (PDF, default: 20)
  --max-pages-per-node N    Max pages per tree node (PDF, default: 10)
  --max-tokens-per-node N   Max tokens per tree node (PDF, default: 20000)
  --if-add-node-id yes|no   Add node IDs to output (default: yes)
  --if-add-node-summary yes|no  Generate LLM summaries per node (default: yes)
  --if-add-doc-description yes|no  Generate doc description (default: no)
  --if-add-node-text yes|no Include full text in nodes (default: no)

Examples:
  python run_pageindex.py --pdf_path "../../sec_filings/AAPL_10K_2025.pdf"
  python run_pageindex.py --md_path "../../research/hft_strategy.md"
  python run_pageindex.py --pdf_path "report.pdf" --model "gpt-4o" --if-add-node-summary yes

Output:
  Results are saved as ./results/<filename>_structure.json

For the PageIndexClient API (programmatic use with agents), see:
  from pageindex import PageIndexClient
  client = PageIndexClient(workspace="./pageindex-workspace")
  doc_id = client.index("filing.pdf")
  print(client.get_document_structure(doc_id))
  print(client.get_page_content(doc_id, "5-7"))
"""

import sys
import os

# Ensure the PageIndex package is on the path
_REPO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         os.pardir, "repos", "PageIndex")
_REPO_DIR = os.path.abspath(_REPO_DIR)
if os.path.isdir(os.path.join(_REPO_DIR, "pageindex")):
    sys.path.insert(0, _REPO_DIR)
else:
    # Fallback: try parent directory
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Run the main PageIndex runner
runner_path = os.path.join(_REPO_DIR, "run_pageindex.py")
if os.path.isfile(runner_path):
    # Pass through all arguments
    exec(open(runner_path).read())
else:
    print(f"ERROR: PageIndex runner not found at {runner_path}")
    print("Make sure the PageIndex repo is cloned at the expected location.")
    sys.exit(1)
