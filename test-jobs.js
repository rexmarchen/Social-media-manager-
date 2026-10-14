/**
 * test-jobs.js
 * ------------
 * Automated verification test suite for Job & Internship Watchdog.
 */

const assert = require("assert");
const { isStrictlyUnder12Hours, isStrictlyTechRole, categorizeJob, parseLinkedInJobsHtml } = require("./job-fetcher");
const { buildHtmlEmail, buildPlainTextEmail } = require("./job-emailer");
const jobState = require("./job-state");

console.log("=== Running Tech Job & Internship Watchdog Test Suite ===");

// 1. Test 12-Hour Recency Validator
console.log("\n[Test 1] 12-Hour Recency Validator:");
assert.strictEqual(isStrictlyUnder12Hours("Just now"), true, "Should accept 'Just now'");
assert.strictEqual(isStrictlyUnder12Hours("15 minutes ago"), true, "Should accept minutes ago");
assert.strictEqual(isStrictlyUnder12Hours("1 hour ago"), true, "Should accept 1 hour ago");
assert.strictEqual(isStrictlyUnder12Hours("11 hours ago"), true, "Should accept 11 hours ago");
assert.strictEqual(isStrictlyUnder12Hours("12 hours ago"), false, "Must reject 12 hours ago");
assert.strictEqual(isStrictlyUnder12Hours("13 hours ago"), false, "Must reject 13 hours ago");
assert.strictEqual(isStrictlyUnder12Hours("1 day ago"), false, "Must reject 1 day ago");
assert.strictEqual(isStrictlyUnder12Hours("3 days ago"), false, "Must reject 3 days ago");
assert.strictEqual(isStrictlyUnder12Hours("1 week ago"), false, "Must reject 1 week ago");
console.log("  ✅ Strictly < 12h recency validator passed all boundary tests.");

// 2. Test Tech Role Filter
console.log("\n[Test 2] Tech Role Domain Validator:");
assert.strictEqual(isStrictlyTechRole("Software Engineer Intern"), true, "Should accept Software Engineer Intern");
assert.strictEqual(isStrictlyTechRole("Full Stack Developer"), true, "Should accept Full Stack Developer");
assert.strictEqual(isStrictlyTechRole("Python / AI Trainee"), true, "Should accept Python / AI Trainee");
assert.strictEqual(isStrictlyTechRole("React Frontend Developer"), true, "Should accept React Frontend Developer");
assert.strictEqual(isStrictlyTechRole("Cloud DevOps Engineer"), true, "Should accept Cloud DevOps Engineer");
assert.strictEqual(isStrictlyTechRole("Sales Executive"), false, "Must reject Sales Executive");
assert.strictEqual(isStrictlyTechRole("HR Manager"), false, "Must reject HR Manager");
assert.strictEqual(isStrictlyTechRole("Customer Care Representative"), false, "Must reject Customer Care");
console.log("  ✅ Tech domain validator correctly filters tech vs non-tech roles.");

// 3. Test Categorization
console.log("\n[Test 3] Job Categorization & Tagging:");
const internCat = categorizeJob("Software Developer Intern");
assert.strictEqual(internCat.isInternship, true, "Should detect internship");
assert.strictEqual(internCat.domain, "Software Engineering");

const aiCat = categorizeJob("AI & Machine Learning Research Trainee");
assert.strictEqual(aiCat.isInternship, true, "Should detect internship");
assert.strictEqual(aiCat.domain, "AI & Data");

const fullstackCat = categorizeJob("Senior Full Stack Developer");
assert.strictEqual(fullstackCat.isInternship, false, "Should detect non-internship");
assert.strictEqual(fullstackCat.domain, "Full Stack");
console.log("  ✅ Job categorization correctly identifies internships and domains.");

// 4. Test Email HTML & Text Builder
console.log("\n[Test 4] Email Template Generation:");
const sampleJobs = [
  {
    id: "9999001",
    title: "Fullstack Engineering Intern",
    company: "Acme Tech",
    location: "Bengaluru, India",
    postedTime: "3 hours ago",
    link: "https://linkedin.com/jobs/view/9999001",
    isInternship: true,
    domain: "Full Stack",
  },
  {
    id: "9999002",
    title: "Junior Backend Developer",
    company: "CloudScale Inc",
    location: "Remote",
    postedTime: "8 hours ago",
    link: "https://linkedin.com/jobs/view/9999002",
    isInternship: false,
    domain: "Backend",
  }
];

const html = buildHtmlEmail(sampleJobs);
assert(html.includes("Acme Tech"), "HTML must include company name");
assert(html.includes("3 hours ago"), "HTML must include posting time");
assert(html.includes("Fullstack Engineering Intern"), "HTML must include title");
assert(html.includes("Apply on LinkedIn"), "HTML must include apply CTA button");

const text = buildPlainTextEmail(sampleJobs);
assert(text.includes("[INTERNSHIP]"), "Text fallback must include internship tag");
assert(text.includes("CloudScale Inc"), "Text fallback must include company");
console.log("  ✅ Email HTML and plain-text templates generated successfully.");

// 5. Test De-duplication State
console.log("\n[Test 5] De-duplication State Store:");
const testJob = { id: "test-dedup-100", title: "Test Engineer", company: "Test Co" };
const unseenBefore = jobState.filterUnseen([testJob]);
assert.strictEqual(unseenBefore.length, 1, "Should identify new unseen job");

jobState.markSeen([testJob]);
const unseenAfter = jobState.filterUnseen([testJob]);
assert.strictEqual(unseenAfter.length, 0, "Must suppress previously marked job");
console.log("  ✅ De-duplication correctly suppresses seen jobs.");

console.log("\n=======================================================");
console.log("🎉 ALL TESTS PASSED SUCCESSFULLY!");
console.log("=======================================================\n");
