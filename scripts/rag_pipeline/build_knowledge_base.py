"""
AGENTX RAG Pipeline — Phase 1 (FAISS + Ollama batched embeddings)
Fast: sends up to 64 texts per API call to Ollama.
"""

import json, sys, time, hashlib, logging
from pathlib import Path
import numpy as np
import ollama

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s")
log = logging.getLogger("rag_build")

DATA_DIR = Path("C:/Trading")
INDEX_DIR = Path("C:/Trading/rag_knowledge_base")
OLLAMA_HOST = "http://10.10.10.1:11434"
EMBED_MODEL = "nomic-embed-text"
BATCH_SIZE = 64  # Send 64 texts per Ollama call

SOURCES = {
    "research":       ("research_division/reports", "*.json", "Research reports"),
    "bot_states":     ("bots/logs", "*_state.json", "Bot state files"),
    "research_state": ("research_division/state", "*.json", "Research state"),
    "config_files":   ("config", "*.json", "Configuration"),
    "backend_db":     ("backend/db", "*.json", "DB files"),
    "harness":        ("Harness", "*.md", "Harness docs"),
}

ollama_client = ollama.Client(host=OLLAMA_HOST)


def chunk_file(filepath):
    chunks = []
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except:
        return chunks
    if not content.strip():
        return chunks

    data = None
    try:
        data = json.loads(content)
    except:
        pass

    if isinstance(data, dict):
        for key, value in data.items():
            text = f"{key}: {json.dumps(value, indent=2, default=str)}"
            for i in range(0, len(text), 2000):
                chunks.append((text[i:i+2000], {"file": str(filepath), "key": key, "type": "dict"}))
    elif isinstance(data, list):
        bs = max(1, len(data) // 20)
        for i in range(0, len(data), bs):
            batch = data[i:i+bs]
            text = json.dumps(batch, indent=2, default=str)[:2000]
            chunks.append((text, {"file": str(filepath), "type": "list", "start": i}))
    else:
        for i in range(0, len(content), 2000):
            chunk = content[i:i+2000]
            if chunk.strip():
                chunks.append((chunk, {"file": str(filepath), "type": "text", "offset": i}))
    return chunks


def main():
    print("=" * 60)
    print("🚀 AGENTX RAG Pipeline — Phase 1 (Batched)")
    print("=" * 60)

    # Step 1: Collect
    print("\n📡 Collecting data...")
    all_chunks = []
    total_files = 0
    for name, (rel_path, glob_pat, desc) in SOURCES.items():
        base = DATA_DIR / rel_path
        if not base.exists():
            log.warning(f"  ⚠️  {base} missing, skip"); continue
        files = sorted(base.glob(glob_pat))
        print(f"  📁 {name} ({desc}): {len(files)} files")
        for fp in files:
            if fp.stat().st_size == 0: continue
            chks = chunk_file(fp)
            for text, meta in chks:
                meta["collection"] = name
                all_chunks.append((text, meta))
            total_files += 1

    total_chunks = len(all_chunks)
    print(f"\n📊 Files: {total_files} | Chunks: {total_chunks}")
    if not all_chunks:
        print("❌ No chunks!"); sys.exit(1)

    # Step 2: Embed in batches
    print(f"\n🧠 Embedding {total_chunks} chunks (batch size {BATCH_SIZE})...")
    INDEX_DIR.mkdir(parents=True, exist_ok=True)

    texts = [t for t, _ in all_chunks]
    metadatas = [m for _, m in all_chunks]
    ids = [hashlib.md5(f"{m['collection']}_{Path(m['file']).stem}_{i}".encode()).hexdigest()[:12]
           for i, m in enumerate(metadatas)]

    all_embeddings = []
    t0 = time.time()
    last_log = 0

    for i in range(0, total_chunks, BATCH_SIZE):
        batch_texts = texts[i:i+BATCH_SIZE]
        try:
            result = ollama_client.embed(model=EMBED_MODEL, input=batch_texts)
            all_embeddings.extend(result.embeddings)
        except Exception as e:
            log.error(f"Batch {i} failed: {e}")
            # Retry individually for this batch
            for t in batch_texts:
                try:
                    r = ollama_client.embed(model=EMBED_MODEL, input=[t])
                    all_embeddings.extend(r.embeddings)
                except:
                    all_embeddings.append([0.0] * 768)

        elapsed = time.time() - t0
        done = min(i + BATCH_SIZE, total_chunks)
        rate = done / elapsed if elapsed > 0 else 0
        eta = (total_chunks - done) / rate if rate > 0 else 0

        # Log progress every ~5%
        pct = done / total_chunks * 100
        if pct - last_log >= 5 or done == total_chunks:
            print(f"  → {done}/{total_chunks} ({pct:.0f}%) | {rate:.0f}/sec | ETA: {eta:.0f}s")
            last_log = pct

    elapsed = time.time() - t0
    print(f"  ✅ All embedded in {elapsed:.0f}s ({total_chunks/elapsed:.1f}/sec)")

    # Step 3: Build FAISS index
    print(f"\n🔨 Building FAISS index...")
    import faiss
    dim = len(all_embeddings[0])
    emb_array = np.array(all_embeddings, dtype=np.float32)

    index = faiss.IndexFlatIP(dim)
    faiss.normalize_L2(emb_array)
    index.add(emb_array)
    print(f"  ✅ Index: {index.ntotal} vectors x {dim} dims")

    # Step 4: Save
    faiss.write_index(index, str(INDEX_DIR / "agentx.index"))
    store = {
        "ids": ids, "texts": texts, "metadatas": metadatas,
        "model": EMBED_MODEL, "dim": dim, "total": len(texts),
        "created": time.strftime("%Y-%m-%d %H:%M:%S HKT"),
        "build_time_s": round(elapsed),
    }
    with open(INDEX_DIR / "agentx_store.json", "w") as f:
        json.dump(store, f, indent=2)

    # Collections map
    collections = {}
    for name in SOURCES:
        if not (DATA_DIR / SOURCES[name][0]).exists(): continue
        collections[name] = [i for i, m in enumerate(metadatas) if m.get("collection") == name]
    with open(INDEX_DIR / "collections.json", "w") as f:
        json.dump(collections, f)

    print(f"  ✅ Saved: agentx.index + agentx_store.json + collections.json")

    # Step 5: Verify
    print(f"\n🔍 Verifying...")
    for name, indices in collections.items():
        print(f"  ✅ '{name}': {len(indices)} chunks")
    print(f"  ✅ Total: {len(texts)} chunks")

    # Test queries
    print(f"\n🧪 Test queries:")
    for q in ["bot performance and P&L", "FTMO challenge rules", "trading strategy parameters", "gold phoenix performance"]:
        try:
            q_emb = np.array(ollama_client.embed(model=EMBED_MODEL, input=[q]).embeddings).astype(np.float32)
            faiss.normalize_L2(q_emb)
            scores, indices = index.search(q_emb, 2)
            print(f"  '{q}':")
            for s, idx in zip(scores[0], indices[0]):
                meta = metadatas[idx]
                print(f"    [{s:.3f}] {Path(meta.get('file','?')).name}")
        except Exception as e:
            print(f"  '{q}': error ({e})")

    print(f"\n{'='*60}")
    print(f"🎉 Knowledge base: {INDEX_DIR}")
    print(f"💡 python scripts/rag_pipeline/query_rag.py \"your question\"")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
