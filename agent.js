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

// ---- CONFIG: verify these model IDs in Google AI Studio before running ----
const CONFIG = {
  textModel: process.env.GEMINI_TEXT_MODEL || "gemini-3.6-flash",
  embeddingModel: process.env.GEMINI_EMBEDDING_MODEL || "gemini-embedding-001",
  imageModel: process.env.GEMINI_IMAGE_MODEL || "gemini-3.1-flash-image",
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
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${CONFIG.embeddingModel}:embedContent`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-goog-api-key": process.env.GEMINI_API_KEY,
    },
    body: JSON.stringify({
      content: { parts: [{ text }] },
    }),
  });

  if (!response.ok) {
    throw new Error(`Embedding error (${response.status}): ${await response.text()}`);
  }

  const data = await response.json();
  return data.embedding.values; // array of floats
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
  const prompt = `You are drafting a LinkedIn post for a computer science student who wants to build a professional, authentic personal brand — not generic marketing copy.

TOPIC: ${topic}

CONTEXT ABOUT THE AUTHOR (use this to keep the voice authentic and specific — do not contradict it, and prefer concrete details from it over generic claims):
${context || "(no additional context available)"}

Write a LinkedIn post following these rules:
- 100-180 words
- Open with a specific, concrete hook — not "In today's world" or "I'm excited to share"
- Sound like a real student/engineer talking, not a corporate brand account
- Use at least one concrete detail from the context above if relevant
- Include one short line break for readability
- End with a genuine question that invites comments (not "Thoughts?")
- Add 3-5 relevant, specific hashtags at the very end (not #motivation #hustle)

Then decide: would a simple supporting image (e.g. a diagram, a relevant illustration, or a conceptual graphic) meaningfully improve this specific post? Most posts do NOT need one — only say yes if it clearly adds value.

Respond with ONLY valid JSON in this exact shape, nothing else:
{
  "post_text": "<the full post text>",
  "needs_image": true or false,
  "image_prompt": "<a concise text-to-image prompt describing the image, or empty string if needs_image is false>"
}`;

  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const configuredModel = process.env.GEMINI_TEXT_MODEL;
  const preferredPrimary = configuredModel && configuredModel !== "gemini-3.8-flash"
    ? configuredModel
    : "gemini-3.6-flash";

  const candidateModels = Array.from(new Set([
    preferredPrimary,
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.8-flash",
  ]));

  let lastError = null;
  for (const model of candidateModels) {
    const maxRetries = 2;
    for (let attempt = 1; attempt <= maxRetries; attempt++) {
      try {
        const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`;
        const response = await fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-goog-api-key": process.env.GEMINI_API_KEY,
          },
          body: JSON.stringify({
            contents: [{ parts: [{ text: prompt }] }],
            generationConfig: {
              responseMimeType: "application/json",
              maxOutputTokens: 2048,
            },
          }),
        });

        if (!response.ok) {
          const errText = await response.text();
          lastError = new Error(`Gemini generateContent error (${response.status}): ${errText}`);
          if ((response.status === 503 || response.status === 429) && attempt < maxRetries) {
            console.warn(`[Gemini Warning] Model ${model} returned ${response.status}, retrying in 1.5s...`);
            await sleep(1500 * attempt);
            continue;
          }
          console.warn(`[Gemini Info] Model ${model} returned ${response.status}, attempting fallback...`);
          break;
        }

        const data = await response.json();
        const rawText = data.candidates?.[0]?.content?.parts?.[0]?.text;
        if (!rawText) throw new Error("Empty or invalid response received from Gemini.");

        const cleaned = rawText.replace(/```json/gi, "").replace(/```/g, "").trim();
        const jsonMatch = cleaned.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          try {
            return JSON.parse(jsonMatch[0]);
          } catch {}
        }
        return {
          post_text: cleaned,
          needs_image: false,
          image_prompt: "",
        };
      } catch (err) {
        lastError = err;
        if (attempt < maxRetries) {
          await sleep(1000 * attempt);
          continue;
        }
        break;
      }
    }
  }

  throw lastError || new Error("All candidate models failed.");
}

// ---------- Image generation ----------
async function generateImage(imagePrompt) {
  // Support both Imagen (predict) and Multimodal generateContent endpoints depending on model naming
  const isImagen = CONFIG.imageModel.startsWith("imagen");
  const endpoint = isImagen
    ? `https://generativelanguage.googleapis.com/v1beta/models/${CONFIG.imageModel}:predict`
    : `https://generativelanguage.googleapis.com/v1beta/models/${CONFIG.imageModel}:generateContent`;

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
    throw new Error(`Gemini image generation error (${response.status}): ${await response.text()}`);
  }

  const data = await response.json();

  // Check Imagen response format
  if (data.predictions?.[0]?.bytesBase64Encoded) {
    return Buffer.from(data.predictions[0].bytesBase64Encoded, "base64");
  }

  // Check Gemini generateContent response format
  const imagePart = data.candidates?.[0]?.content?.parts?.find((p) => p.inlineData);
  if (imagePart?.inlineData?.data) {
    return Buffer.from(imagePart.inlineData.data, "base64");
  }

  throw new Error("No image bytes returned in Gemini response: " + JSON.stringify(data));
}

// ---------- LinkedIn: image upload ----------
async function uploadImageToLinkedIn(imageBuffer) {
  const authorUrn = process.env.LINKEDIN_PERSON_URN;
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
async function publishPost(text, imageUrn) {
  const authorUrn = process.env.LINKEDIN_PERSON_URN;
  const accessToken = process.env.LINKEDIN_ACCESS_TOKEN;

  const body = {
    author: authorUrn,
    commentary: text,
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
  for (const key of ["GEMINI_API_KEY", "LINKEDIN_ACCESS_TOKEN", "LINKEDIN_PERSON_URN"]) {
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
