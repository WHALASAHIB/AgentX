"""
AGENTX RAG Query Tool
Usage: python scripts/rag_pipeline/query_rag.py "your question" [--top 5] [--collection NAME]
"""

import sys, json, time
from pathlib import Path
import numpy as np
import ollama

INDEX_DIR = Path("C:/Trading/rag_knowledge_base")
OLLAMA_HOST = "http://10.10.10.1:11434"
EMBED_MODEL = "nomic-embed-text"
ollama_client = ollama.Client(host=OLLAMA_HOST)


def main():
    if len(sys.argv) < 2:
        print("Usage: python query_rag.py \"your question\" [--top N] [--collection NAME]")
        sys.exit(1)

    query = sys.argv[1]
    top = 5
    collection_filter = None

    if "--top" in sys.argv:
        top = int(sys.argv[sys.argv.index("--top") + 1])
    if "--collection" in sys.argv:
        collection_filter = sys.argv[sys.argv.index("--collection") + 1]

    if not (INDEX_DIR / "agentx.index").exists():
        print("❌ No index found! Run build_knowledge_base.py first.")
        sys.exit(1)

    import faiss
    index = faiss.read_index(str(INDEX_DIR / "agentx.index"))
    with open(INDEX_DIR / "agentx_store.json") as f:
        store = json.load(f)

    texts = store["texts"]
    metadatas = store["metadatas"]

    # Filter by collection if requested
    if collection_filter:
        with open(INDEX_DIR / "collections.json") as f:
            collections = json.load(f)
        idxs = collections.get(collection_filter, [])
        if not idxs:
            print(f"❌ Collection '{collection_filter}' empty or not found")
            print(f"   Available: {list(collections.keys())}")
            sys.exit(1)
        texts = [store["texts"][i] for i in idxs]
        metadatas = [store["metadatas"][i] for i in idxs]
        # Build sub-index
        all_embs = np.array([index.reconstruct(int(i)) for i in idxs]).astype(np.float32)
        sub_index = faiss.IndexFlatIP(all_embs.shape[1])
        sub_index.add(all_embs)
        search_index = sub_index
    else:
        search_index = index

    # Embed query
    q_emb = np.array(ollama_client.embed(model=EMBED_MODEL, input=[query]).embeddings).astype(np.float32)
    faiss.normalize_L2(q_emb)

    t0 = time.time()
    scores, indices = search_index.search(q_emb, min(top, len(texts)))
    elapsed_ms = (time.time() - t0) * 1000

    print(f"\n{'='*60}")
    print(f"🔍 Query: '{query}'")
    if collection_filter:
        print(f"📦 Collection: {collection_filter} ({len(texts)} chunks)")
    else:
        print(f"📦 Index: {len(store['texts'])} chunks")
    print(f"⚡ Searched in {elapsed_ms:.0f}ms")
    print(f"{'='*60}")

    for i, (score, idx) in enumerate(zip(scores[0], indices[0])):
        meta = metadatas[idx]
        text = texts[idx]
        source = Path(meta.get("file", "?")).name
        col = meta.get("collection", "")
        key = meta.get("key", "")
        print(f"\n─── #{i+1} (confidence: {score:.3f}) ───")
        print(f"📄 [{col}] {source}")
        if key: print(f"🔑 {key}")
        preview = text[:400]
        print(f"📝 {preview}..." if len(text) > 400 else f"📝 {text}")

    print(f"\n{'='*60}")


if __name__ == "__main__":
    main()
