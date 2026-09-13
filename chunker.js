/**
 * chunker.js
 * ----------
 * Splits raw text into overlapping chunks suitable for embedding.
 *
 * Why overlap matters: if a chunk boundary falls in the middle of an idea,
 * pure non-overlapping splits can separate a statement from its context.
 * A small overlap (e.g. 100 characters) means each chunk carries a bit of
 * the previous chunk's tail, so retrieval doesn't lose context at the edges.
 */

const CHUNK_SIZE = 800; // target characters per chunk
const CHUNK_OVERLAP = 100; // characters repeated between consecutive chunks

function splitIntoChunks(text, chunkSize = CHUNK_SIZE, overlap = CHUNK_OVERLAP) {
  const cleaned = text.replace(/\r\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
  if (cleaned.length === 0) return [];

  const chunks = [];
  let start = 0;

  while (start < cleaned.length) {
    let end = Math.min(start + chunkSize, cleaned.length);

    // Try to break at a paragraph or sentence boundary near the target end,
    // instead of cutting a sentence in half.
    if (end < cleaned.length) {
      const paragraphBreak = cleaned.lastIndexOf("\n\n", end);
      const sentenceBreak = cleaned.lastIndexOf(". ", end);
      const boundary = Math.max(paragraphBreak, sentenceBreak);
      if (boundary > start + chunkSize * 0.5) {
        end = boundary + 1;
      }
    }

    const chunk = cleaned.slice(start, end).trim();
    if (chunk.length > 0) chunks.push(chunk);

    if (end >= cleaned.length) break;
    start = end - overlap; // step back by the overlap amount
  }

  return chunks;
}

module.exports = { splitIntoChunks };
