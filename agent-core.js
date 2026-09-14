/**
 * agent-core.js
 * -------------
 * The generation + LinkedIn posting pipeline. Retrieval now comes from the
 * local vector database (built by ingest.js from ./documents), instead of
 * re-embedding a small JSON file on every call — this scales to however
 * many documents you feed it, and only re-embeds what's changed.
 */

const { retrieveRelevantChunks } = require("./vector-store");
const { findRelevantMemories, getRecentMemories } = require("./mongo-store");

const CONFIG = {
  textModel: process.env.GEMINI_TEXT_MODEL || "gemini-3.6-flash",
  imageModel: process.env.GEMINI_IMAGE_MODEL || "gemini-3.1-flash-image",
};

async function retrieveContext(topic, topK = 4) {
  const contextParts = [];

  // 1. Retrieve semantic memories from MongoDB Atlas (learnings, projects, GitHub)
  try {
    const memories = await findRelevantMemories(topic, topK);
    for (const m of memories) {
      if (m.score > 0.45) {
        contextParts.push(`- [Cloud Memory - ${m.type}] ${m.content}`);
      }
    }
  } catch (err) {
    console.warn("[Memory Warning] Could not retrieve MongoDB memories:", err.message);
  }

  // 2. Retrieve local document chunks if available
  try {
    const chunks = await retrieveRelevantChunks(topic, topK);
    for (const c of chunks) {
      contextParts.push(`- [Doc Chunk - from ${c.source}] ${c.text}`);
    }
  } catch (err) {
    // Local vector store might be empty on fresh cloud deploys
  }

  // 3. If context is empty, supply the latest 2 real-life memories
  if (contextParts.length === 0) {
    try {
      const recent = await getRecentMemories(2);
      for (const r of recent) {
        contextParts.push(`- [Recent Activity - ${r.type}] ${r.content}`);
      }
    } catch {}
  }

  return contextParts.join("\n");
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function generatePost(topic, context) {
  const prompt = `You are drafting a LinkedIn post for a computer science student who wants to build a professional, authentic personal brand — not generic marketing copy.

TOPIC: ${topic}

CONTEXT RETRIEVED FROM THE AUTHOR'S OWN DOCUMENTS (use this to keep the voice authentic and specific — do not contradict it, and prefer concrete details from it over generic claims; if it's not relevant to the topic, rely on the topic alone):
${context || "(no relevant context found)"}

Write a LinkedIn post following these rules:
- 100-180 words
- Open with a specific, concrete hook — not "In today's world" or "I'm excited to share"
- Sound like a real student/engineer talking, not a corporate brand account
- Use at least one concrete detail from the context above if it's genuinely relevant
- Include one short line break for readability
- End with a genuine question that invites comments (not "Thoughts?")
- Add 3-5 relevant, specific hashtags at the very end (not #motivation #hustle)

Then decide: would a simple supporting image meaningfully improve this specific post? Most posts do NOT need one — only say yes if it clearly adds value.

Respond with ONLY valid JSON in this exact shape, nothing else:
{
  "post_text": "<the full post text>",
  "needs_image": true or false,
  "image_prompt": "<a concise text-to-image prompt, or empty string if needs_image is false>"
}`;

  // Prioritize reliable, stable models.
  // gemini-3.8-flash frequently throws 503 Unavailable / High Demand, so it is deprioritized.
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
          body: JSON.stringify({ contents: [{ parts: [{ text: prompt }] }] }),
        });

        if (!response.ok) {
          const errText = await response.text();
          lastError = new Error(`Gemini generateContent error (${response.status}): ${errText}`);
          // If temporary high demand (503) or rate limit (429), retry before moving to next model
          if ((response.status === 503 || response.status === 429) && attempt < maxRetries) {
            console.warn(`[Gemini Warning] Model ${model} returned ${response.status} (attempt ${attempt}/${maxRetries}), retrying in 1.5s...`);
            await sleep(1500 * attempt);
            continue;
          }
          console.warn(`[Gemini Info] Model ${model} returned ${response.status}, attempting next fallback model...`);
          break; // proceed to next candidate model
        }

        const data = await response.json();
        const textPart = data.candidates?.[0]?.content?.parts?.find((p) => p.text);
        const rawText = textPart ? textPart.text : data.candidates?.[0]?.content?.parts?.[0]?.text;
        if (!rawText) throw new Error("No text returned by Gemini");

        const jsonMatch = rawText.match(/\{[\s\S]*\}/);
        if (jsonMatch) {
          try {
            return JSON.parse(jsonMatch[0]);
          } catch {
            // If JSON fails to parse, fall back to plain text below
          }
        }

        return {
          post_text: rawText.replace(/```json|```/g, "").trim(),
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

async function generateImage(imagePrompt) {
  const candidateImageModels = Array.from(new Set([
    CONFIG.imageModel,
    "gemini-3.1-flash-image",
    "gemini-3-pro-image",
    "gemini-2.5-flash-image",
  ]));

  let lastErr = null;
  for (const model of candidateImageModels) {
    try {
      const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`;
      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-goog-api-key": process.env.GEMINI_API_KEY,
        },
        body: JSON.stringify({ contents: [{ parts: [{ text: imagePrompt }] }] }),
      });
      if (!response.ok) {
        lastErr = new Error(`Gemini image error (${response.status}): ${await response.text()}`);
        continue;
      }
      const data = await response.json();
      const imagePart = data.candidates?.[0]?.content?.parts?.find((p) => p.inlineData);
      if (!imagePart) continue;
      return Buffer.from(imagePart.inlineData.data, "base64");
    } catch (err) {
      lastErr = err;
    }
  }
  throw lastErr || new Error("All image candidate models failed.");
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

async function uploadImageToLinkedIn(imageBuffer) {
  const authorUrn = await getAuthorUrn();
  const accessToken = process.env.LINKEDIN_ACCESS_TOKEN;

  const initResponse = await fetch(
    "https://api.linkedin.com/rest/images?action=initializeUpload",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
        "LinkedIn-Version": process.env.LINKEDIN_VERSION || "202603",
        "X-Restli-Protocol-Version": "2.0.0",
      },
      body: JSON.stringify({ initializeUploadRequest: { owner: authorUrn } }),
    }
  );
  if (!initResponse.ok) throw new Error(`LinkedIn image init error: ${await initResponse.text()}`);
  const initData = await initResponse.json();
  const uploadUrl = initData.value.uploadUrl;
  const imageUrn = initData.value.image;

  const uploadResponse = await fetch(uploadUrl, {
    method: "PUT",
    headers: { Authorization: `Bearer ${accessToken}` },
    body: imageBuffer,
  });
  if (!uploadResponse.ok) throw new Error(`LinkedIn image upload error (${uploadResponse.status})`);

  return imageUrn;
}

async function publishPost(text, imageUrn) {
  const authorUrn = await getAuthorUrn();
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
  if (imageUrn) body.content = { media: { id: imageUrn } };

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
  if (!response.ok) throw new Error(`LinkedIn post error: ${await response.text()}`);
  return response.headers.get("x-restli-id");
}

async function runAgentForTopic(topic) {
  const context = await retrieveContext(topic);
  const { post_text, needs_image, image_prompt } = await generatePost(topic, context);

  let imageUrn = null;
  if (needs_image && image_prompt) {
    try {
      const imageBuffer = await generateImage(image_prompt);
      imageUrn = await uploadImageToLinkedIn(imageBuffer);
    } catch (imgErr) {
      console.warn("Optional image generation skipped:", imgErr.message);
    }
  }

  const postId = await publishPost(post_text, imageUrn);

  return { postId, postText: post_text, hadImage: Boolean(imageUrn) };
}

module.exports = {
  runAgentForTopic,
  retrieveContext,
  generatePost,
  uploadImageToLinkedIn,
  publishPost,
};
