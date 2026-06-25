# PageIndex — Vectorless RAG for Financial Documents

## Overview

PageIndex is a **vectorless RAG engine** — it builds a hierarchical tree index of documents
instead of embedding chunks into a vector database. This makes it ideal for financial documents
where structure matters: SEC filings, earnings reports, and strategy research papers.

**How it works:**
1. Parse the document (PDF or Markdown) into a structured tree of sections/subsections
2. Optionally generate LLM summaries for each node
3. Use the tree index for agentic QA — the agent reads the tree, identifies relevant pages,
   and retrieves the exact content needed

**No vector database required.** No chunking strategies to tune.

---

## Setup

### Prerequisites
- Python 3.12+ (available at `/c/Users/nryur/AppData/Local/Programs/Python/Python312/python.exe`)
- An LLM API key (OpenAI, Anthropic, or any litellm-supported provider) for summaries

### Files in this directory

| File | Purpose |
|------|---------|
| `run_pageindex.py` | CLI runner — drops into the PageIndex repo's `run_pageindex.py` |
| `.env.template` | Copy to `.env` and add your API key |
| `sample_financial_doc.md` | Example earnings report for testing |
| `results/` | Output directory for indexed document structures |
| `workspace/` | PageIndexClient workspace (persists indexed documents) |

### Quick Start

```bash
# 1. Set up your API key
cp .env.template .env
# Edit .env to set OPENAI_API_KEY=your-key-here

# 2. Index a financial document
cd /c/Trading/research_division/pageindex-data
python run_pageindex.py --md_path sample_financial_doc.md

# 3. For PDF documents (e.g., SEC filings):
python run_pageindex.py --pdf_path /path/to/AAPL_10K_2025.pdf
```

### Configuration

Edit `/c/Trading/research_division/repos/PageIndex/pageindex/config.yaml` to set:
- `model`: Default LLM model (e.g., `gpt-4o`, `anthropic/claude-sonnet-4-6`)
- `retrieve_model`: Model for retrieval queries (defaults to `model`)
- `toc_check_page_num`: Pages to scan for table of contents (PDF only)
- `max_page_num_each_node`: Max pages per tree node (PDF only)
- `if_add_node_summary`: Generate LLM summaries per section
- `if_add_node_text`: Include full text in the index

---

## Usage with Financial Documents

### SEC Filings (10-K, 10-Q, 8-K)

```bash
# Index a 10-K filing
python run_pageindex.py --pdf_path "../sec_filings/AAPL_10K_2025.pdf" \
    --model "gpt-4o" \
    --if-add-node-summary yes \
    --if-add-node-text no

# Output: ./results/AAPL_10K_2025_structure.json
```

The structure JSON contains a hierarchical tree with sections like:
- Business Overview
- Risk Factors
- Management's Discussion and Analysis
- Financial Statements

### Earnings Reports

```bash
python run_pageindex.py --md_path "../earnings/NVDA_Q4_2025.md" \
    --if-add-node-text yes
```

The markdown parser automatically detects headers (##, ###) and builds the tree.

### Strategy Research

For research notes, white papers, or strategy documents in Markdown:

```bash
python run_pageindex.py --md_path "../research/hft_strategy.md" \
    --if-thinning yes \
    --thinning-threshold 3000 \
    --if-add-node-summary yes
```

---

## Programmatic API (PageIndexClient)

For integration with agent frameworks (like OpenAI Agents SDK), use the client API:

```python
import json
from pageindex import PageIndexClient

# Create client with persistent workspace
client = PageIndexClient(
    workspace="./pageindex-workspace",
    model="gpt-4o",
    api_key="your-openai-key"  # or set OPENAI_API_KEY env var
)

# 1. Index a document
doc_id = client.index("/path/to/10k_filing.pdf")
print(f"Indexed: {doc_id}")

# 2. Get document metadata
doc = client.get_document(doc_id)
print(doc)  # {"doc_id": "...", "doc_name": "...", "page_count": 150, ...}

# 3. Get tree structure (without text, to save tokens)
structure = json.loads(client.get_document_structure(doc_id))

# 4. Retrieve specific page content
content = client.get_page_content(doc_id, "15-22")
```

### Agentic QA Workflow

```python
from pageindex import PageIndexClient

client = PageIndexClient(workspace="./workspace")
doc_id = client.index("10k_filing.pdf")

# Get structure to find relevant sections
structure = client.get_document_structure(doc_id)
print(structure)  # Shows tree: Risk Factors -> pages 12-18

# Get specific content
content = client.get_page_content(doc_id, "14-16")
print(content)  # Text from pages 14-16
```

For a full agent example with the OpenAI Agents SDK, see:
`examples/agentic_vectorless_rag_demo.py` in the PageIndex repo.

---

## Architecture

```
Financial Document (PDF/MD)
         │
         ▼
   PageIndex Parser
         │
         ├── PDF: Extract pages, detect TOC, build section tree
         └── MD:  Parse headers, build hierarchy, thin if needed
         │
         ▼
   Tree Index (JSON)
   ┌─────────────────────────┐
   │ doc_name, doc_desc      │
   │ structure: [            │
   │   {title, node_id,      │
   │    summary, text,       │
   │    nodes: [...]}        │
   │ ]                       │
   └─────────────────────────┘
         │
         ▼
   Agentic Retrieval
   ┌─────────────────────────┐
   │ 1. Get document()       │ ← metadata, page count
   │ 2. Get structure()      │ ← browse tree index
   │ 3. Get page_content()   │ ← retrieve tight ranges
   └─────────────────────────┘
```

## Key Differences from Vector RAG

| Feature | PageIndex (Vectorless) | Traditional Vector RAG |
|---------|----------------------|----------------------|
| Setup | No vector DB needed | Requires vector DB + embeddings |
| Document structure | Preserved as tree | Lost in chunking |
| Retrieval | LLM reasons over index | Cosine similarity on chunks |
| Financial docs | Ideal (hierarchical) | Poor (table/chunk mismatch) |
| Cold start | Instant | Need to index + embed |
| Context cost | Tree structure (small) | Many chunks (large) |

---

## Troubleshooting

**"No module named 'pageindex'"**
→ Ensure PYTHONPATH includes the repo: `export PYTHONPATH=/c/Trading/repos/PageIndex:$PYTHONPATH`

**DLL load failed for pymupdf**
→ The default PDF parser is `PyPDF2`, which works without pymupdf. Only switch to `PyMuPDF`
  if you specifically need it and have the VC++ Redistributables installed.

**LLM API errors during indexing**
→ PageIndex needs an LLM for TOC detection and summaries. Set OPENAI_API_KEY in `.env` or
  pass `--if-add-node-summary no` to skip summary generation (structural parsing still works).

**PDF processing is slow**
→ Increase `--max-pages-per-node` and `--max-tokens-per-node` to reduce LLM calls.
  Or use the `--toc-check-pages` argument to limit TOC scanning.
