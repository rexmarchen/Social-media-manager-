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

function isValidImageBuffer(buffer) {
  if (!buffer || !Buffer.isBuffer(buffer) || buffer.length < 4096) {
    return false;
  }
  // Validate JPEG (0xFF, 0xD8, 0xFF) or PNG (0x89, 0x50, 0x4E, 0x47) signatures
  const isJpeg = buffer[0] === 0xFF && buffer[1] === 0xD8 && buffer[2] === 0xFF;
  const isPng = buffer[0] === 0x89 && buffer[1] === 0x50 && buffer[2] === 0x4E && buffer[3] === 0x47;
  return isJpeg || isPng;
}

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function generatePost(topic, context) {
  const prompt = `You are Anshu Pal, a computer science student, software builder, and engineer.
You are writing a short, authentic LinkedIn post sharing a real engineering insight from your work.

TOPIC: ${topic}

RETRIEVED TECHNICAL CONTEXT FROM YOUR REPOSITORIES & MEMORY (Ground your post strictly in this context):
${context || "(no relevant context found)"}

HUMAN WRITING & VOICE GUIDELINES (STRICT):
1. Voice & Tone:
   - Write in first-person ("I", "my team", "when I was building...")
   - Speak like a passionate developer talking to peers over coffee — raw, thoughtful, and practical.
   - Be honest about trade-offs, architecture decisions, and things that were tricky or broke.
2. Structure & Length:
   - Length: 120-170 words.
   - Hook: Start directly with a concrete observation, problem, or technical realization. Never use generic intro phrases like "In today's fast-paced world", "I am thrilled/excited to share", or "Have you ever wondered".
   - Body: 2-3 natural, short paragraphs with comfortable line breaks. Avoid robotic bulleted lists.
   - Ending: End with a genuine, low-friction engineering question that developers would actually want to answer in comments.
   - Hashtags: 2-3 clean, specific dev hashtags at the end (e.g. #softwareengineering #webdev #reactjs).
3. BANNED AI WORDS (NEVER USE THESE):
   - delve, tapestry, testament, beacon, game-changer, revolutionize, embark, landscape, bespoke, leverage, seamless, transformative, supercharge, dive into, in today's world.

Decision: Decide if a simple supporting graphic or diagram meaningfully enhances this post. Only set needs_image to true if visual aid is truly valuable.

Respond with ONLY valid JSON in this exact structure:
{
  "post_text": "<the complete humanized post text with line breaks and hashtags>",
  "needs_image": false,
  "image_prompt": ""
}`;

const { callGeminiResilient } = require("./gemini-resilience");

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

  throw new Error("Invalid or truncated post_text received from model.");
}

async function generateImage(imagePrompt) {
  if (!imagePrompt || !imagePrompt.trim()) {
    throw new Error("Empty image prompt provided.");
  }

  const configuredImageModel = process.env.GEMINI_IMAGE_MODEL || "gemini-3.1-flash-image";
  const candidateImageModels = Array.from(
    new Set([
      configuredImageModel,
      "gemini-3.1-flash-image",
      "gemini-3-pro-image",
      "imagen-3.0-generate-002",
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

      const controller = new AbortController();
      const timeoutHandle = setTimeout(() => controller.abort(), 15000);

      let response;
      try {
        response = await fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-goog-api-key": process.env.GEMINI_API_KEY,
          },
          body: JSON.stringify(requestBody),
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timeoutHandle);
      }

      if (!response.ok) {
        lastErr = new Error(`Image generation error for ${model} (${response.status}): ${await response.text()}`);
        continue;
      }

      const data = await response.json();
      let buffer = null;

      // Check Imagen response format
      if (data.predictions?.[0]?.bytesBase64Encoded) {
        buffer = Buffer.from(data.predictions[0].bytesBase64Encoded, "base64");
      } else {
        // Check Gemini generateContent response format
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
  if (!isValidImageBuffer(imageBuffer)) {
    throw new Error("Cannot upload invalid or empty image buffer to LinkedIn.");
  }

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
    headers: { Authorization: `Bearer ${accessToken}`, "Content-Type": "image/jpeg" },
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
