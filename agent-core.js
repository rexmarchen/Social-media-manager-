/**
 * agent-core.js
 * -------------
 * The generation + LinkedIn posting pipeline. Retrieval now comes from the
 * local vector database (built by ingest.js from ./documents), instead of
 * re-embedding a small JSON file on every call — this scales to however
 * many documents you feed it, and only re-embeds what's changed.
 */

const { retrieveRelevantChunks } = require("./vector-store");
const { findRelevantMemories, getRecentMemories, addMemory } = require("./mongo-store");
const { researchTopicForPost, markRepoAsPosted } = require("./ai-researcher");

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

  // Prioritize reliable, ultra-responsive models to prevent 503 capacity errors
  const configuredModel = process.env.GEMINI_TEXT_MODEL;
  const candidateModels = Array.from(
    new Set([
      "gemini-3.5-flash-lite",
      "gemini-3.5-flash",
      "gemini-3.6-flash",
      "gemini-3.7-flash",
      configuredModel,
    ].filter(Boolean))
  );

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
  const candidateImageModels = Array.from(
    new Set([
      CONFIG.imageModel,
      "imagen-3.0-generate-002",
      "gemini-3.1-flash-image",
      "gemini-2.5-flash-image",
    ].filter(Boolean))
  );

  let lastErr = null;
  for (const model of candidateImageModels) {
    try {
      const isImagen = model.startsWith("imagen");
      const url = isImagen
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

      const response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-goog-api-key": process.env.GEMINI_API_KEY,
        },
        body: JSON.stringify(requestBody),
      });

      if (!response.ok) {
        lastErr = new Error(`Image generation error for ${model} (${response.status}): ${await response.text()}`);
        continue;
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

/**
 * Fully autonomous AI research & RAG publishing workflow:
 * 1. Researches across all user repositories to pick an interesting, diverse project
 * 2. Ideates an authentic engineering angle and retrieves RAG context from vector DB
 * 3. Generates high-impact post text
 * 4. Image handling: NO static banner photos. Only generates a custom image if AI truly requests visual aid.
 * 5. Publishes to LinkedIn and updates MongoDB state to avoid repeating the same repo.
 */
async function generateAutonomousPost(targetRepoName = null) {
  const research = await researchTopicForPost(targetRepoName);
  console.log(`[Autonomous Agent] Researched project "${research.repoName}": ${research.topicTitle}`);

  const promptTopic = `${research.topicTitle} (${research.repoName} in ${research.language})`;
  const { post_text, needs_image, image_prompt } = await generatePost(promptTopic, research.ragContext);

  let imageUrn = null;
  if (needs_image && image_prompt) {
    console.log(`[Autonomous Agent] Generating unique visual graphic for this topic...`);
    try {
      const imageBuffer = await generateImage(image_prompt);
      imageUrn = await uploadImageToLinkedIn(imageBuffer);
      console.log(`[Autonomous Agent] Custom image uploaded to LinkedIn. URN: ${imageUrn}`);
    } catch (imgErr) {
      console.warn("[Autonomous Agent] Optional image generation skipped:", imgErr.message);
    }
  } else {
    console.log(`[Autonomous Agent] Clean text post selected (no unnecessary photos attached).`);
  }

  const postId = await publishPost(post_text, imageUrn);

  // Mark repository as posted to ensure rotation across all projects
  await markRepoAsPosted(research.repoName);

  // Save to MongoDB memories
  try {
    await addMemory(
      `LinkedIn post published about ${research.repoName} (${research.topicTitle}): ${post_text}`,
      "published_post",
      `linkedin:${research.repoKey}`,
      { repoName: research.repoName, topic: research.topicTitle, postId }
    );
  } catch (err) {
    console.warn("Could not save published post memory:", err.message);
  }

  return {
    postId,
    postText: post_text,
    hadImage: Boolean(imageUrn),
    repoName: research.repoName,
    topicTitle: research.topicTitle,
  };
}

module.exports = {
  runAgentForTopic,
  generateAutonomousPost,
  retrieveContext,
  generatePost,
  generateImage,
  uploadImageToLinkedIn,
  publishPost,
};
