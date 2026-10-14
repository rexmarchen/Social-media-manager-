/**
 * gemini-resilience.js
 * --------------------
 * Production-level Gemini API client with:
 * 1. Automatic Request Timeouts via AbortSignal
 * 2. Exponential Backoff with Decorrelated Jitter for 503 (High Demand) & 429 (Rate Limits)
 * 3. Dynamic Model Cascading (transparent fallback across active Google Gemini models)
 * 4. Model Cooldown / Circuit Breaker (avoids hammering temporarily overloaded models)
 * 5. Robust JSON response extraction & repair
 * 6. Embedding generation with retry protection
 */

try {
  require("dotenv").config();
} catch (e) {
  // Gracefully fallback if dotenv is not installed
}

// Default high-availability model hierarchy
const DEFAULT_TEXT_MODELS = [
  process.env.GEMINI_TEXT_MODEL,
  "gemini-flash-lite-latest",
  "gemini-3.5-flash",
  "gemini-3.5-flash-lite",
  "gemini-3.1-flash-lite",
  "gemini-flash-latest",
  "gemini-3.6-flash",
  "gemini-3.8-flash",
].filter(Boolean);

// Cooldown tracker: modelName -> expiration timestamp (ms)
const modelCooldowns = new Map();
const COOLDOWN_DURATION_MS = 3 * 60 * 1000; // 3 minutes cooldown for a failing model

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

/**
 * Calculates exponential backoff with jitter
 * @param {number} attempt - 1-based attempt index
 * @param {number} baseMs - base delay (default 2000ms)
 * @param {number} maxMs - max delay cap (default 15000ms)
 */
function getJitteredBackoff(attempt, baseMs = 2000, maxMs = 15000) {
  const expDelay = Math.min(maxMs, baseMs * Math.pow(2, attempt - 1));
  // Full jitter: between 50% and 100% of expDelay
  return Math.floor(expDelay * (0.5 + Math.random() * 0.5));
}

/**
 * Check if an error code is retryable (transient server or rate limit issues)
 */
function isRetryableStatus(status) {
  return [429, 500, 502, 503, 504].includes(status);
}

/**
 * Returns model candidates ordered by health (active models first, cooled-down models at the end)
 */
function getSortedCandidateModels(overrideModels = null) {
  const rawList = overrideModels && overrideModels.length > 0 ? overrideModels : DEFAULT_TEXT_MODELS;
  const uniqueModels = Array.from(new Set(rawList.filter(Boolean)));
  const now = Date.now();

  const healthy = [];
  const inCooldown = [];

  for (const model of uniqueModels) {
    const cooldownExpires = modelCooldowns.get(model);
    if (cooldownExpires && cooldownExpires > now) {
      inCooldown.push(model);
    } else {
      healthy.push(model);
    }
  }

  // Healthy models run first, in-cooldown models run as last-ditch fallback
  return [...healthy, ...inCooldown];
}

/**
 * Mark a model as temporarily overloaded (e.g. on 503 or 429)
 */
function recordModelFailure(model, reason = "overloaded") {
  const expiresAt = Date.now() + COOLDOWN_DURATION_MS;
  modelCooldowns.set(model, expiresAt);
  console.warn(`[Gemini Resilience] Model "${model}" put in temporary cooldown for 3m (${reason}).`);
}

/**
 * Robustly parses and extracts JSON from Gemini output
 */
function extractAndParseJson(rawText) {
  if (!rawText || typeof rawText !== "string") {
    throw new Error("Empty text received from model.");
  }

  // 1. Try direct parse
  try {
    return JSON.parse(rawText.trim());
  } catch {}

  // 2. Strip markdown code fences (```json ... ``` or ``` ...)
  const stripped = rawText
    .replace(/^```json\s*/i, "")
    .replace(/^```\s*/, "")
    .replace(/```$/g, "")
    .trim();

  try {
    return JSON.parse(stripped);
  } catch {}

  // 3. Extract JSON object substring
  const jsonMatch = rawText.match(/\{[\s\S]*\}/);
  if (jsonMatch) {
    try {
      return JSON.parse(jsonMatch[0]);
    } catch {}
  }

  throw new Error(`Unable to extract valid JSON from Gemini output. Raw snippet: ${rawText.slice(0, 200)}`);
}

/**
 * Production-level Gemini generateContent call with retry, backoff, timeout, and cascading
 *
 * @param {Object} options
 * @param {string} options.prompt - Text prompt
 * @param {string} [options.systemInstruction] - Optional system instruction
 * @param {boolean} [options.expectJson=false] - Whether to parse response as JSON
 * @param {number} [options.temperature=0.7] - Model temperature
 * @param {number} [options.maxOutputTokens=2048] - Max output tokens
 * @param {number} [options.timeoutMs=25000] - Request timeout per attempt (default 25s)
 * @param {number} [options.maxRetriesPerModel=2] - Max retries per candidate model
 * @param {string[]} [options.candidateModels] - Optional explicit candidate models list
 * @returns {Promise<{ text: string, data: any, modelUsed: string }>}
 */
async function callGeminiResilient({
  prompt,
  systemInstruction = null,
  expectJson = false,
  temperature = 0.7,
  maxOutputTokens = 2048,
  timeoutMs = 25000,
  maxRetriesPerModel = 2,
  candidateModels = null,
}) {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    throw new Error("GEMINI_API_KEY is missing from environment variables.");
  }

  const modelsToTry = getSortedCandidateModels(candidateModels);
  let lastError = null;

  for (const model of modelsToTry) {
    for (let attempt = 1; attempt <= maxRetriesPerModel; attempt++) {
      try {
        const url = `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`;

        const requestBody = {
          contents: [{ parts: [{ text: prompt }] }],
          generationConfig: {
            temperature,
            maxOutputTokens,
          },
        };

        if (expectJson) {
          requestBody.generationConfig.responseMimeType = "application/json";
        }

        if (systemInstruction) {
          requestBody.systemInstruction = {
            parts: [{ text: systemInstruction }],
          };
        }

        const controller = new AbortController();
        const timeoutHandle = setTimeout(() => controller.abort(), timeoutMs);

        let response;
        try {
          response = await fetch(url, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "x-goog-api-key": apiKey,
            },
            body: JSON.stringify(requestBody),
            signal: controller.signal,
          });
        } finally {
          clearTimeout(timeoutHandle);
        }

        if (!response.ok) {
          const errText = await response.text();
          const status = response.status;
          lastError = new Error(`Gemini generateContent error (${status}) on model ${model}: ${errText}`);

          if (isRetryableStatus(status)) {
            // Put model in cooldown if 503 or 429
            if (status === 503 || status === 429) {
              recordModelFailure(model, `status ${status}`);
            }

            if (attempt < maxRetriesPerModel) {
              const backoffMs = getJitteredBackoff(attempt, 2000, 8000);
              console.warn(
                `[Gemini Resilience] Model ${model} returned ${status} (attempt ${attempt}/${maxRetriesPerModel}). Retrying in ${backoffMs}ms...`
              );
              await sleep(backoffMs);
              continue;
            }
          }

          // If not retryable or retries exhausted for this model, break to next candidate model
          break;
        }

        const data = await response.json();
        const rawText = data.candidates?.[0]?.content?.parts?.[0]?.text;
        if (!rawText) {
          throw new Error(`Empty response content from Gemini model ${model}.`);
        }

        let parsedJson = null;
        if (expectJson) {
          parsedJson = extractAndParseJson(rawText);
        }

        // Successfully got response!
        return {
          text: rawText.trim(),
          data: parsedJson,
          modelUsed: model,
        };
      } catch (err) {
        lastError = err;
        const isTimeout = err.name === "AbortError" || err.message?.includes("aborted");

        if (isTimeout) {
          recordModelFailure(model, "request timeout");
          console.warn(`[Gemini Resilience] Request to model ${model} timed out after ${timeoutMs}ms.`);
          break; // Move to faster fallback model immediately on timeout
        }

        if (attempt < maxRetriesPerModel) {
          const backoffMs = getJitteredBackoff(attempt, 1500, 5000);
          console.warn(
            `[Gemini Resilience] Error with model ${model} (${err.message}). Retrying in ${backoffMs}ms...`
          );
          await sleep(backoffMs);
        }
      }
    }
  }

  throw lastError || new Error("All Gemini candidate models failed to produce a valid response.");
}

/**
 * Resilient Embedding generation with automatic retry and backoff
 *
 * @param {string} text - text to embed
 * @param {string} [model] - embedding model
 * @param {number} [timeoutMs=15000] - timeout
 * @returns {Promise<number[]>} embedding vector
 */
async function callGeminiEmbeddingResilient(text, model = null, timeoutMs = 15000) {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    throw new Error("GEMINI_API_KEY is missing from environment variables.");
  }

  const embeddingModel = model || process.env.GEMINI_EMBEDDING_MODEL || "gemini-embedding-001";
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${embeddingModel}:embedContent`;

  let lastError = null;
  for (let attempt = 1; attempt <= 3; attempt++) {
    try {
      const controller = new AbortController();
      const timeoutHandle = setTimeout(() => controller.abort(), timeoutMs);

      let response;
      try {
        response = await fetch(url, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "x-goog-api-key": apiKey,
          },
          body: JSON.stringify({ content: { parts: [{ text }] } }),
          signal: controller.signal,
        });
      } finally {
        clearTimeout(timeoutHandle);
      }

      if (!response.ok) {
        const errText = await response.text();
        lastError = new Error(`Embedding error (${response.status}): ${errText}`);
        if (isRetryableStatus(response.status) && attempt < 3) {
          const delay = getJitteredBackoff(attempt, 1500, 6000);
          await sleep(delay);
          continue;
        }
        throw lastError;
      }

      const data = await response.json();
      if (!data.embedding?.values) {
        throw new Error("No embedding values in API response.");
      }
      return data.embedding.values;
    } catch (err) {
      lastError = err;
      if (attempt < 3) {
        const delay = getJitteredBackoff(attempt, 1500, 5000);
        await sleep(delay);
      }
    }
  }

  throw lastError || new Error(`Failed to generate embedding for model ${embeddingModel}.`);
}

module.exports = {
  callGeminiResilient,
  callGeminiEmbeddingResilient,
  extractAndParseJson,
  DEFAULT_TEXT_MODELS,
};
