"""
Step 1: Ingest your knowledge base into a vector database.
-------------------------------------------------------------
Put your own writing (blog posts, notes, articles - .txt or .md files)
inside the knowledge_base/ folder, then run this script once (and again
any time you add new files):

    python ingest.py

This will:
  1. Read every .txt/.md file in knowledge_base/
  2. Split each into chunks (~500 characters, with slight overlap)
  3. Turn each chunk into an embedding (a numeric "fingerprint" of meaning)
  4. Store everything in a local vector database (./chroma_db folder)

Requirements:
  pip install chromadb langchain-text-splitters
"""

import os
import glob
import chromadb
from langchain_text_splitters import RecursiveCharacterTextSplitter

KNOWLEDGE_DIR = "knowledge_base"
DB_DIR = "chroma_db"
COLLECTION_NAME = "my_content"

CHUNK_SIZE = 500       # characters per chunk
CHUNK_OVERLAP = 50     # overlap so we don't cut ideas in half


def load_documents(folder: str) -> list[dict]:
    """Read all .txt and .md files from the folder."""
    docs = []
    paths = glob.glob(os.path.join(folder, "*.txt")) + glob.glob(os.path.join(folder, "*.md"))
    if not paths:
        raise FileNotFoundError(
            f"No .txt or .md files found in '{folder}/'. "
            f"Add some of your own writing there first."
        )
    for path in paths:
        with open(path, "r", encoding="utf-8") as f:
            docs.append({"source": os.path.basename(path), "text": f.read()})
    return docs


def chunk_documents(docs: list[dict]) -> list[dict]:
    """Split each document into overlapping chunks."""
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
    )
    chunks = []
    for doc in docs:
        pieces = splitter.split_text(doc["text"])
        for i, piece in enumerate(pieces):
            chunks.append({
                "id": f"{doc['source']}-{i}",
                "text": piece,
                "source": doc["source"],
            })
    return chunks


def store_chunks(chunks: list[dict]):
    """Embed and store chunks in a local persistent ChromaDB collection."""
    client = chromadb.PersistentClient(path=DB_DIR)
    # get_or_create_collection uses a built-in local embedding model automatically
    collection = client.get_or_create_collection(name=COLLECTION_NAME)

    collection.upsert(
        ids=[c["id"] for c in chunks],
        documents=[c["text"] for c in chunks],
        metadatas=[{"source": c["source"]} for c in chunks],
    )


if __name__ == "__main__":
    print(f"Reading documents from '{KNOWLEDGE_DIR}/'...")
    documents = load_documents(KNOWLEDGE_DIR)
    print(f"Loaded {len(documents)} document(s).")

    print("Splitting into chunks...")
    chunks = chunk_documents(documents)
    print(f"Created {len(chunks)} chunk(s).")

    print("Embedding and storing in vector database...")
    store_chunks(chunks)
    print(f"Done. Vector database saved to '{DB_DIR}/'.")
