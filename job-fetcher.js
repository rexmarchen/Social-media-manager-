/**
 * job-fetcher.js
 * --------------
 * Production-level tech job & internship scraper for LinkedIn public guest search.
 * Enforces:
 *   1. Strict 12-hour recency (API parameter f_TPR=r43200 + secondary text validator).
 *   2. Strict tech domain validation (positive match for engineering/tech, negative rejection).
 *   3. Role categorization (Internship vs Full-time, Tech domain tagging).
 */

const USER_AGENTS = [
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
  "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
];

// Target search queries
const DEFAULT_QUERIES = [
  "Software Engineer Intern",
  "Web Development Intern",
  "Frontend Developer Intern",
  "Backend Developer Intern",
  "Full Stack Developer",
  "Software Engineer",
  "Node.js Developer",
  "React Developer",
  "Python Developer",
  "AI Engineer Intern",
  "Machine Learning Intern",
  "Cloud DevOps Engineer",
];

// Strict positive tech keywords
const TECH_POSITIVE_KEYWORDS = [
  "software", "developer", "engineer", "frontend", "front-end", "backend", "back-end",
  "fullstack", "full-stack", "full stack", "web dev", "react", "angular", "vue",
  "node", "nodejs", "javascript", "typescript", "python", "golang", "rust", "java",
  "c++", "c#", ".net", "cloud", "devops", "sre", "aws", "azure", "docker", "kubernetes",
  "data engineer", "data scientist", "machine learning", "deep learning", "ai", "artificial intelligence",
  "nlp", "computer vision", "llm", "qa automation", "sdet", "mobile developer", "android", "ios",
  "flutter", "react native", "security engineer", "cybersecurity", "intern", "internship"
];

// Strict negative keywords to filter out non-tech postings
const NON_TECH_NEGATIVE_KEYWORDS = [
  "sales", "business development", "bdr", "sdr", "account executive",
  "telecaller", "recruiter", "talent acquisition", "human resources", "hr manager", "hr intern",
  "digital marketing", "marketing executive", "seo specialist", "content writer", "copywriter",
  "social media manager", "customer care", "customer support", "call center",
  "financial analyst", "accountant", "audit", "store manager", "legal counsel", "paralegal",
  "nurse", "medical officer", "pharmacist", "civil engineer", "mechanical engineer"
];

function getRandomUserAgent() {
  return USER_AGENTS[Math.floor(Math.random() * USER_AGENTS.length)];
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function cleanText(text) {
  if (!text) return "";
  return text
    .replace(/<[^>]*>/g, "")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Validates that the posting age is STRICTLY UNDER 12 HOURS.
 * Rejects 12 hours ago, 13 hours ago, 1 day ago, etc.
 * @param {string} timeText e.g. "2 hours ago", "45 minutes ago", "Just now"
 * @returns {boolean}
 */
function isStrictlyUnder12Hours(timeText) {
  if (!timeText) return false;
  const lower = timeText.toLowerCase().trim();

  // Fresh items: minutes, seconds, just now
  if (
    lower.includes("minute") ||
    lower.includes("min") ||
    lower.includes("sec") ||
    lower.includes("just now") ||
    lower.includes("moments ago")
  ) {
    return true;
  }

  // Hours: extract numeric value
  const hourMatch = lower.match(/(\d+)\s*(?:hour|hr)s?\s*ago/);
  if (hourMatch) {
    const hours = parseInt(hourMatch[1], 10);
    // Strictly under 12 hours (< 12)
    return hours >= 0 && hours < 12;
  }

  // If it mentions days, weeks, months, or anything else, reject immediately
  return false;
}

/**
 * Validates that the role is genuinely tech-related.
 * @param {string} title
 * @returns {boolean}
 */
function isStrictlyTechRole(title) {
  if (!title) return false;
  const lower = title.toLowerCase();

  // Check negative keywords first
  for (const neg of NON_TECH_NEGATIVE_KEYWORDS) {
    // Avoid false rejection if word like "software" or "tech" is also in title
    if (lower.includes(neg)) {
      const hasTechOverride = lower.includes("software") || lower.includes("developer") || lower.includes("engineer");
      if (!hasTechOverride) {
        return false;
      }
    }
  }

  // Check positive tech keywords
  for (const pos of TECH_POSITIVE_KEYWORDS) {
    if (lower.includes(pos)) {
      return true;
    }
  }

  return false;
}

/**
 * Determine category & internship status.
 */
function categorizeJob(title) {
  const lower = title.toLowerCase();
  const isInternship =
    lower.includes("intern") ||
    lower.includes("internship") ||
    lower.includes("trainee") ||
    lower.includes("co-op") ||
    lower.includes("apprentice");

  let domain = "Software Engineering";
  if (lower.includes("frontend") || lower.includes("front-end") || lower.includes("react") || lower.includes("vue")) {
    domain = "Frontend";
  } else if (lower.includes("backend") || lower.includes("back-end") || lower.includes("node") || lower.includes("python") || lower.includes("java")) {
    domain = "Backend";
  } else if (lower.includes("fullstack") || lower.includes("full-stack") || lower.includes("full stack")) {
    domain = "Full Stack";
  } else if (lower.includes("ai") || lower.includes("machine learning") || lower.includes("data scientist") || lower.includes("llm")) {
    domain = "AI & Data";
  } else if (lower.includes("cloud") || lower.includes("devops") || lower.includes("aws") || lower.includes("docker")) {
    domain = "Cloud & DevOps";
  } else if (lower.includes("mobile") || lower.includes("android") || lower.includes("ios") || lower.includes("flutter")) {
    domain = "Mobile";
  }

  return { isInternship, domain };
}

/**
 * Parse job cards out of the LinkedIn guest search HTML response.
 * @param {string} html
 * @returns {Array<object>}
 */
function parseLinkedInJobsHtml(html) {
  const jobs = [];
  const cardRegex = /<div class="base-card[^"]*"(?:(?!<div class="base-card)[\s\S])*?<\/li>/gi;
  let match;

  while ((match = cardRegex.exec(html)) !== null) {
    const cardHtml = match[0];

    // 1. Extract URN / Job ID
    const urnMatch = cardHtml.match(/data-entity-urn="urn:li:jobPosting:(\d+)"/i);
    const id = urnMatch ? urnMatch[1] : null;

    // 2. Extract Link
    const linkMatch = cardHtml.match(/<a class="base-card__full-link[^"]*" href="([^"]+)"/i);
    let link = linkMatch ? linkMatch[1] : null;
    if (link) {
      // Clean tracking query params for a clean, direct apply link
      link = link.split("?")[0];
    }

    // 3. Extract Title
    const titleMatch = cardHtml.match(/<h3 class="base-search-card__title">([\s\S]*?)<\/h3>/i);
    const title = titleMatch ? cleanText(titleMatch[1]) : "";

    // 4. Extract Company
    const companyMatch = cardHtml.match(/<h4 class="base-search-card__subtitle">([\s\S]*?)<\/h4>/i);
    const company = companyMatch ? cleanText(companyMatch[1]) : "";

    // 5. Extract Location
    const locationMatch = cardHtml.match(/<span class="job-search-card__location">([\s\S]*?)<\/span>/i);
    const location = locationMatch ? cleanText(locationMatch[1]) : "";

    // 6. Extract Time text
    const timeMatch = cardHtml.match(/<time[^>]*>([\s\S]*?)<\/time>/i);
    const postedTime = timeMatch ? cleanText(timeMatch[1]) : "";

    // 7. Extract Company Logo (if available)
    const logoMatch = cardHtml.match(/<img[^>]+data-delayed-url="([^"]+)"/i) || cardHtml.match(/<img[^>]+src="([^"]+)"/i);
    const logoUrl = logoMatch ? logoMatch[1] : null;

    if (id && title && link) {
      jobs.push({
        id,
        title,
        company,
        location,
        postedTime,
        link,
        logoUrl,
      });
    }
  }

  return jobs;
}

/**
 * Fetch jobs for a single keyword query and location strictly under 12 hours.
 * @param {string} query
 * @param {string} location
 * @returns {Promise<Array<object>>}
 */
async function fetchJobsForQuery(query, location = "India") {
  // f_TPR=r43200 restricts to past 12 hours (43200 seconds)
  const encodedQuery = encodeURIComponent(query);
  const encodedLocation = encodeURIComponent(location);
  const url = `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=${encodedQuery}&location=${encodedLocation}&f_TPR=r43200&start=0`;

  try {
    const res = await fetch(url, {
      headers: {
        "User-Agent": getRandomUserAgent(),
        Accept: "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Cache-Control": "no-cache",
      },
    });

    if (!res.ok) {
      console.warn(`[JobFetcher] Query "${query}" in "${location}" returned status ${res.status}`);
      return [];
    }

    const html = await res.text();
    const rawJobs = parseLinkedInJobsHtml(html);

    // Apply strict filters: strictly < 12 hours and strictly tech
    const filtered = [];
    for (const job of rawJobs) {
      if (!isStrictlyUnder12Hours(job.postedTime)) {
        continue;
      }
      if (!isStrictlyTechRole(job.title)) {
        continue;
      }

      const { isInternship, domain } = categorizeJob(job.title);
      filtered.push({
        ...job,
        isInternship,
        domain,
        queriedFor: query,
        searchLocation: location,
      });
    }

    return filtered;
  } catch (err) {
    console.error(`[JobFetcher] Error fetching query "${query}":`, err.message);
    return [];
  }
}

/**
 * Main fetch function: iterates over queries and configured locations,
 * deduplicating within the batch and enforcing strict tech and 12-hour criteria.
 * @param {object} options
 * @param {Array<string>} [options.queries]
 * @param {Array<string>} [options.locations]
 * @returns {Promise<Array<object>>}
 */
async function fetchLatestTechJobs(options = {}) {
  const queries = options.queries || DEFAULT_QUERIES;
  const locationsEnv = process.env.JOB_SEARCH_LOCATIONS || "India,Remote";
  const locations = options.locations || locationsEnv.split(",").map((s) => s.trim()).filter(Boolean);

  console.log(`[JobFetcher] Starting scan across ${queries.length} tech queries and ${locations.length} locations...`);
  console.log(`[JobFetcher] Recency constraint: STRICTLY < 12 HOURS (f_TPR=r43200 + validator).`);

  const seenBatchIds = new Set();
  const allFreshJobs = [];

  for (const location of locations) {
    for (const query of queries) {
      const results = await fetchJobsForQuery(query, location);

      for (const job of results) {
        if (!seenBatchIds.has(job.id)) {
          seenBatchIds.add(job.id);
          allFreshJobs.push(job);
        }
      }

      // Small randomized delay between requests to be polite and reliable
      await delay(1200 + Math.floor(Math.random() * 800));
    }
  }

  // Sort by internships first, then domain
  allFreshJobs.sort((a, b) => {
    if (a.isInternship && !b.isInternship) return -1;
    if (!a.isInternship && b.isInternship) return 1;
    return a.domain.localeCompare(b.domain);
  });

  console.log(`[JobFetcher] Scan complete. Found ${allFreshJobs.length} strictly < 12h tech jobs & internships.`);
  return allFreshJobs;
}

module.exports = {
  fetchLatestTechJobs,
  fetchJobsForQuery,
  isStrictlyUnder12Hours,
  isStrictlyTechRole,
  categorizeJob,
  DEFAULT_QUERIES,
};
