/**
 * agent-core.js
 * -------------
 * The generation + LinkedIn posting pipeline. Retrieval now comes from the
 * local vector database (built by ingest.js from ./documents), instead of
 * re-embedding a small JSON file on every call — this scales to however
 * many documents you feed it, and only re-embeds what's changed.
 */

const { retrieveRelevantChunks } = require("./vector-store");

const CONFIG = {
  textModel: process.env.GEMINI_TEXT_MODEL || "gemini-3.6-flash",
  imageModel: process.env.GEMINI_IMAGE_MODEL || "gemini-3.1-flash-image",
};

async function retrieveContext(topic, topK = 4) {
  const chunks = await retrieveRelevantChunks(topic, topK);
  if (chunks.length === 0) return "";
  return chunks
    .map((c) => `- (from ${c.source}, relevance ${c.score.toFixed(2)}) ${c.text}`)
    .join("\n");
}

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

  const candidateModels = Array.from(new Set([
    CONFIG.textModel,
    "gemini-3.6-flash",
    "gemini-3.8-flash",
    "gemini-3.1-flash-lite",
  ]));

  let lastError = null;
  for (const model of candidateModels) {
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
        console.warn(`[Gemini Info] Model ${model} returned ${response.status}, attempting fallback...`);
        lastError = new Error(`Gemini generateContent error (${response.status}): ${errText}`);
        continue;
      }
      const data = await response.json();
      const textPart = data.candidates?.[0]?.content?.parts?.find((p) => p.text);
      const rawText = textPart ? textPart.text : data.candidates?.[0]?.content?.parts?.[0]?.text;
      if (!rawText) throw new Error("No text returned by Gemini");
      const jsonMatch = rawText.match(/\{[\s\S]*\}/);
      if (!jsonMatch) throw new Error(`Could not parse JSON from Gemini response: ${rawText}`);
      return JSON.parse(jsonMatch[0]);
    } catch (err) {
      lastError = err;
    }
  }
  throw lastError || new Error("All candidate models failed.");
}

async function generateImage(imagePrompt) {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${CONFIG.imageModel}:generateContent`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "x-goog-api-key": process.env.GEMINI_API_KEY,
    },
    body: JSON.stringify({ contents: [{ parts: [{ text: imagePrompt }] }] }),
  });
  if (!response.ok) throw new Error(`Gemini image error: ${await response.text()}`);
  const data = await response.json();
  const imagePart = data.candidates[0].content.parts.find((p) => p.inlineData);
  if (!imagePart) throw new Error("No image returned from Gemini.");
  return Buffer.from(imagePart.inlineData.data, "base64");
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

module.exports = { runAgentForTopic, retrieveContext };
