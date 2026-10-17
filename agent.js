/**
 * LinkedIn RAG Agent
 * ------------------
 * Retrieves context about you, drafts a post with Gemini, optionally
 * generates a supporting image, and publishes to LinkedIn.
 *
 * Required environment variables:
 * - GEMINI_API_KEY: from Google AI Studio
 * - LINKEDIN_ACCESS_TOKEN: OAuth token with w_member_social scope
 * - LINKEDIN_PERSON_URN: e.g. "urn:li:person:AbC123"
 */

// Gracefully load .env if dotenv is installed (useful for local development)
try {
  require("dotenv").config();
} catch (e) {
  // dotenv not installed, rely on system/actions environment variables
}

const fs = require("fs");
const path = require("path");
const { callGeminiResilient, callGeminiEmbeddingResilient } = require("./gemini-resilience");

// ---- CONFIG: verified active models ----
const CONFIG = {
  textModel: process.env.GEMINI_TEXT_MODEL || "gemini-3-flash-preview",
  embeddingModel: process.env.GEMINI_EMBEDDING_MODEL || "gemini-embedding-001",
  imageModel: process.env.GEMINI_IMAGE_MODEL || "imagen-3.0-generate-002",
};
// ----------------------------------------------------------------------------

const KNOWLEDGE_PATH = path.join(__dirname, "knowledge.json");
const TOPICS_PATH = path.join(__dirname, "topics.json");
const STATE_PATH = path.join(__dirname, "state.json");

function loadJSON(filePath, fallback) {
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf8"));
  } catch {
    return fallback;
  }
}

function saveJSON(filePath, data) {
  fs.writeFileSync(filePath, JSON.stringify(data, null, 2));
}

function getNextTopic() {
  const topics = loadJSON(TOPICS_PATH, []);
  if (topics.length === 0) throw new Error("topics.json is empty.");
  const state = loadJSON(STATE_PATH, { lastIndex: -1 });
  const nextIndex = (state.lastIndex + 1) % topics.length;
  saveJSON(STATE_PATH, { lastIndex: nextIndex });
  return topics[nextIndex];
}

// ---------- Embeddings + retrieval (the "RAG" part) ----------
async function embedText(text) {
  return await callGeminiEmbeddingResilient(text, CONFIG.embeddingModel);
}

function cosineSimilarity(a, b) {
  let dot = 0,
    normA = 0,
    normB = 0;
  for (let i = 0; i < a.length; i++) {
    dot += a[i] * b[i];
    normA += a[i] * a[i];
    normB += b[i] * b[i];
  }
  return dot / (Math.sqrt(normA) * Math.sqrt(normB));
}

async function retrieveContext(topic, topK = 3) {
  const knowledge = loadJSON(KNOWLEDGE_PATH, []);
  if (knowledge.length === 0) return "";

  const topicEmbedding = await embedText(topic);

  // Embed each knowledge chunk (fine for small knowledge bases; cache this
  // in a file if your knowledge base grows past ~50 entries to save calls)
  const scored = [];
  for (const chunk of knowledge) {
    const chunkEmbedding = await embedText(chunk.text);
    const score = cosineSimilarity(topicEmbedding, chunkEmbedding);
    scored.push({ ...chunk, score });
  }

  scored.sort((a, b) => b.score - a.score);
  const top = scored.slice(0, topK);
  return top.map((c) => `- ${c.text}`).join("\n");
}

// ---------- Text generation ----------
async function generatePost(topic, context) {
  const prompt = `You are Anshu Pal, a B.Tech student in Artificial Intelligence and Machine Learning at CGC University, actively learning full-stack development and building real-world software projects.
Your flagship project is REXION — an AI-powered web platform focused on simplifying job discovery and application workflows.

TOPIC: ${topic}

VERIFIED CONTEXT ABOUT THE AUTHOR & PROJECTS (Ground your post strictly in this; never invent facts, statistics, benchmarks, or fake production deployments):
${context || "(no additional context available)"}

HUMAN WRITING & VOICE STANDARDS (STRICT):
1. Positioning:
   - An aspiring AI/ML and full-stack developer who learns by building, experiments with technology, solves real engineering problems, and documents genuine progress.
   - Speak like a real engineer talking to peers — thoughtful, raw, practical, and grounded.
   - Whenever relevant, communicate: 1. The problem, 2. The approach, 3. The trade-off or challenge, 4. The outcome or lesson.
2. Structure & Length:
   - 110-170 words.
   - Hook: Start directly with a concrete observation, debugging moment, or architectural trade-off. Never use "In today's fast-paced world", "I am excited to share", or "Have you ever wondered".
   - Body: 2-3 short, mobile-friendly paragraphs. Avoid robotic bulleted lists.
   - Conclusion: End with a genuine, low-friction engineering question that developers or recruiters would naturally want to comment on.
   - Hashtags: 3-5 specific, relevant hashtags (e.g. #AIML #FullStack #MERNStack #SoftwareEngineering #Python).
3. BANNED AI WORDS (NEVER USE):
   - delve, tapestry, testament, beacon, game-changer, revolutionize, embark, landscape, bespoke, leverage, seamless, transformative, supercharge, dive into, in today's world, thrilled to announce.

Visual Decision:
Decide if a clean technical graphic (e.g., an architectural diagram, code flow, or minimal visual) meaningfully aids understanding. Only set needs_image to true if genuinely beneficial.

Respond with ONLY valid JSON in this exact shape:
{
  "post_text": "<full post text with clean line breaks and hashtags>",
  "primary_keyword": "<primary technical keyword>",
  "skills_demonstrated": ["<skill1>", "<skill2>"],
  "needs_image": false,
  "image_prompt": "<detailed image prompt if needs_image is true, or empty string>"
}`;

function isValidImageBuffer(buffer) {
  if (!buffer || !Buffer.isBuffer(buffer) || buffer.length < 4096) {
    return false;
  }
  const isJpeg = buffer[0] === 0xFF && buffer[1] === 0xD8 && buffer[2] === 0xFF;
  const isPng = buffer[0] === 0x89 && buffer[1] === 0x50 && buffer[2] === 0x4E && buffer[3] === 0x47;
  return isJpeg || isPng;
}

  const result = await callGeminiResilient({
    prompt,
    expectJson: true,
    temperature: 0.7,
    maxOutputTokens: 2048,
    timeoutMs: 25000,
  });

  const parsed = result.data;
  if (parsed && typeof parsed.post_text === "string" && parsed.post_text.trim().length > 40) {
    return {
      post_text: parsed.post_text.trim(),
      needs_image: Boolean(parsed.needs_image),
      image_prompt: typeof parsed.image_prompt === "string" ? parsed.image_prompt.trim() : "",
    };
  }

  throw new Error("Invalid or incomplete post_text in JSON response");
}

// ---------- Image generation ----------
async function generateImage(imagePrompt) {
  if (!imagePrompt || !imagePrompt.trim()) {
    throw new Error("Empty image prompt provided.");
  }

  const configuredImageModel = process.env.GEMINI_IMAGE_MODEL || "imagen-3.0-generate-002";
  const candidateImageModels = Array.from(
    new Set([
      configuredImageModel,
      "imagen-3.0-generate-002",
      "gemini-3.1-flash-image",
    ].filter(Boolean))
  );

  let lastErr = null;
  for (const model of candidateImageModels) {
    try {
      const isImagen = model.startsWith("imagen");
      const endpoint = isImagen
        ? `https://generativelanguage.googleapis.com/v1beta/models/${model}:predict`
        : `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`;

      const requestBody = isImagen
        ? {
            instances: [{ prompt: imagePrompt }],
            parameters: { sampleCount: 1, aspectRatio: "1:1", outputOptions: { mimeType: "image/jpeg" } },
          }
        : {
            contents: [{ parts: [{ text: imagePrompt }] }],
          };

      const response = await fetch(endpoint, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-goog-api-key": process.env.GEMINI_API_KEY,
        },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        lastErr = new Error(`Gemini image generation error (${response.status}): ${await response.text()}`);
        continue;
      }

      const data = await response.json();
      let buffer = null;

      // Check Imagen response format
      if (data.predictions?.[0]?.bytesBase64Encoded) {
        buffer = Buffer.from(data.predictions[0].bytesBase64Encoded, "base64");
      } else {
        const imagePart = data.candidates?.[0]?.content?.parts?.find((p) => p.inlineData);
        if (imagePart?.inlineData?.data) {
          buffer = Buffer.from(imagePart.inlineData.data, "base64");
        }
      }

      if (buffer && isValidImageBuffer(buffer)) {
        return buffer;
      }
      lastErr = new Error(`Image model ${model} did not return a valid image buffer.`);
    } catch (err) {
      lastErr = err;
    }
  }

  throw lastErr || new Error("All candidate image models failed.");
}

async function getAuthorUrn() {
  let urn = (process.env.LINKEDIN_PERSON_URN || "").trim();
  if (urn) {
    return urn.startsWith("urn:li:person:") ? urn : `urn:li:person:${urn}`;
  }
  // Auto-resolve URN from LinkedIn access token if not configured in environment
  const response = await fetch("https://api.linkedin.com/v2/userinfo", {
    headers: { Authorization: `Bearer ${process.env.LINKEDIN_ACCESS_TOKEN}` },
  });
  if (!response.ok) {
    throw new Error(`LinkedIn userinfo error (${response.status}): ${await response.text()}`);
  }
  const data = await response.json();
  if (!data.sub) {
    throw new Error("Unable to retrieve LinkedIn person ID (sub) from userinfo.");
  }
  return `urn:li:person:${data.sub}`;
}

// ---------- LinkedIn: image upload ----------
async function uploadImageToLinkedIn(imageBuffer) {
  if (!isValidImageBuffer(imageBuffer)) {
    throw new Error("Cannot upload invalid or empty image buffer to LinkedIn.");
  }

  const authorUrn = await getAuthorUrn();
  const accessToken = process.env.LINKEDIN_ACCESS_TOKEN;

  // Step 1: register the upload
  const initResponse = await fetch("https://api.linkedin.com/rest/images?action=initializeUpload", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
      "LinkedIn-Version": process.env.LINKEDIN_VERSION || "202603",
      "X-Restli-Protocol-Version": "2.0.0",
    },
    body: JSON.stringify({
      initializeUploadRequest: { owner: authorUrn },
    }),
  });

  if (!initResponse.ok) {
    throw new Error(`LinkedIn image init error (${initResponse.status}): ${await initResponse.text()}`);
  }

  const initData = await initResponse.json();
  const uploadUrl = initData.value.uploadUrl;
  const imageUrn = initData.value.image;

  // Step 2: PUT the raw image bytes to the returned upload URL
  const uploadResponse = await fetch(uploadUrl, {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${accessToken}`,
      "Content-Type": "image/jpeg",
    },
    body: imageBuffer,
  });

  if (!uploadResponse.ok) {
    throw new Error(`LinkedIn image upload error (${uploadResponse.status}): ${await uploadResponse.text()}`);
  }

  return imageUrn; // e.g. "urn:li:image:C4E10..."
}

// ---------- LinkedIn: publish post ----------
function sanitizeLinkedInCommentary(text) {
  if (!text || typeof text !== "string") return "";
  let cleaned = text
    .replace(/```[a-zA-Z0-9_-]*\n?/g, "")
    .replace(/```/g, "")
    .replace(/`([^`\n]+)`/g, "$1")
    .replace(/`/g, "");
  cleaned = cleaned.replace(/\r\n/g, "\n").replace(/\n{3,}/g, "\n\n");
  return cleaned.trim();
}

async function publishPost(text, imageUrn) {
  const authorUrn = await getAuthorUrn();
  const accessToken = process.env.LINKEDIN_ACCESS_TOKEN;

  const body = {
    author: authorUrn,
    commentary: sanitizeLinkedInCommentary(text),
    visibility: "PUBLIC",
    distribution: {
      feedDistribution: "MAIN_FEED",
      targetEntities: [],
      thirdPartyDistributionChannels: [],
    },
    lifecycleState: "PUBLISHED",
    isReshareDisabledByAuthor: false,
  };

  if (imageUrn) {
    body.content = {
      media: { id: imageUrn },
    };
  }

  const response = await fetch("https://api.linkedin.com/rest/posts", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
      "X-Restli-Protocol-Version": "2.0.0",
      "LinkedIn-Version": process.env.LINKEDIN_VERSION || "202603",
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(`LinkedIn post error (${response.status}): ${await response.text()}`);
  }

  return response.headers.get("x-restli-id");
}

// ---------- Orchestration ----------
async function main() {
  for (const key of ["GEMINI_API_KEY", "LINKEDIN_ACCESS_TOKEN"]) {
    if (!process.env[key]) throw new Error(`Missing required environment variable: ${key}`);
  }

  const topic = getNextTopic();
  console.log(`[Agent] Topic selected: "${topic}"`);

  console.log("[Agent] Performing RAG retrieval from knowledge base...");
  const context = await retrieveContext(topic);
  console.log(`[Agent] Retrieved context:\n${context || "(None)"}\n`);

  console.log("[Agent] Generating LinkedIn post with Gemini...");
  const { post_text, needs_image, image_prompt } = await generatePost(topic, context);
  console.log(`\n--- Generated Post Draft ---\n${post_text}\n----------------------------\n`);
  console.log(`Needs image: ${needs_image}`);

  let imageUrn = null;
  if (needs_image && image_prompt) {
    try {
      console.log(`[Agent] Generating image for prompt: "${image_prompt}"`);
      const imageBuffer = await generateImage(image_prompt);
      console.log(`[Agent] Uploading image (${imageBuffer.length} bytes) to LinkedIn...`);
      imageUrn = await uploadImageToLinkedIn(imageBuffer);
      console.log(`[Agent] Image uploaded successfully. Asset URN: ${imageUrn}`);
    } catch (imgErr) {
      console.warn(`[Agent Warning] Could not generate/upload image (${imgErr.message}). Falling back to text-only post.`);
      imageUrn = null;
    }
  }

  console.log("[Agent] Publishing post to LinkedIn...");
  const postId = await publishPost(post_text, imageUrn);
  console.log(`[Agent] Published successfully! Post ID / Restli ID: ${postId}`);
}

if (require.main === module) {
  main().catch((err) => {
    console.error("[Agent Error]:", err.message);
    process.exit(1);
  });
}

module.exports = {
  getNextTopic,
  embedText,
  retrieveContext,
  generatePost,
  generateImage,
  uploadImageToLinkedIn,
  publishPost,
  CONFIG,
};
