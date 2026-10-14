/**
 * job-monitor.js
 * --------------
 * Production-level CLI and orchestrator for Tech Job & Internship Email Alerts.
 *
 * Usage:
 *   node job-monitor.js             - Run live check, email new jobs, update state
 *   node job-monitor.js --dry-run   - Check & display fresh jobs without sending email
 *   node job-monitor.js --test-email- Test SMTP configuration and email delivery
 *   node job-monitor.js --force     - Bypass de-duplication and process all fresh jobs
 */

require("dotenv").config();
const { fetchLatestTechJobs } = require("./job-fetcher");
const jobState = require("./job-state");
const { sendJobAlertEmail, createTransporter, verifyTransporter } = require("./job-emailer");

/**
 * Runs one scan and email notification cycle.
 * @param {object} options
 * @param {boolean} [options.dryRun=false]
 * @param {boolean} [options.force=false]
 * @returns {Promise<{scanned: number, newJobsCount: number, emailSent: boolean}>}
 */
async function runJobMonitor(options = {}) {
  const isDryRun = options.dryRun || process.argv.includes("--dry-run");
  const isForce = options.force || process.argv.includes("--force");

  console.log(`\n======================================================`);
  console.log(`🔍 TECH JOB & INTERNSHIP WATCHDOG (< 12 HOURS)`);
  console.log(`Mode: ${isDryRun ? "DRY-RUN (No emails will be sent)" : "LIVE"}`);
  console.log(`Time: ${new Date().toLocaleString("en-US", { timeZone: process.env.TIMEZONE || "Asia/Kolkata" })}`);
  console.log(`======================================================\n`);

  // 1. Fetch latest tech postings strictly < 12h
  const scannedJobs = await fetchLatestTechJobs();

  if (scannedJobs.length === 0) {
    console.log(`[JobMonitor] No tech jobs under 12 hours found in this run.`);
    return { scanned: 0, newJobsCount: 0, emailSent: false };
  }

  // 2. Filter out already seen jobs (unless --force is passed)
  const unseenJobs = isForce ? scannedJobs : jobState.filterUnseen(scannedJobs);

  console.log(`\n📊 Scan Results:`);
  console.log(`   - Total strictly < 12h tech jobs found: ${scannedJobs.length}`);
  console.log(`   - Previously notified (suppressed): ${scannedJobs.length - unseenJobs.length}`);
  console.log(`   - New unseen postings: ${unseenJobs.length}\n`);

  if (unseenJobs.length === 0) {
    console.log(`[JobMonitor] ✅ All current postings have already been emailed. Zero duplicate spam.`);
    return { scanned: scannedJobs.length, newJobsCount: 0, emailSent: false };
  }

  // Display top preview in terminal
  console.log(`📋 Fresh Postings Found:`);
  unseenJobs.forEach((job, idx) => {
    const badge = job.isInternship ? "[🎓 INTERNSHIP]" : "[💼 TECH ROLE]";
    console.log(`  ${idx + 1}. ${badge} ${job.title} | ${job.company} | ${job.location} (${job.postedTime})`);
    console.log(`     Link: ${job.link}`);
  });
  console.log(``);

  if (isDryRun) {
    console.log(`[JobMonitor] [DRY RUN] Would send an email with ${unseenJobs.length} listings to: ${process.env.ALERT_EMAIL_TO || "(ALERT_EMAIL_TO not set)"}`);
    return { scanned: scannedJobs.length, newJobsCount: unseenJobs.length, emailSent: false };
  }

  // 3. Dispatch Email Alert
  const emailResult = await sendJobAlertEmail(unseenJobs);

  if (emailResult.success) {
    // 4. Mark jobs as seen only when email succeeds
    jobState.markSeen(unseenJobs);
    console.log(`[JobMonitor] 💾 Marked ${unseenJobs.length} jobs as notified in local store.`);
    return { scanned: scannedJobs.length, newJobsCount: unseenJobs.length, emailSent: true };
  } else {
    console.warn(`[JobMonitor] Email not sent (${emailResult.error || "unknown"}). Jobs remain unseen for next cycle.`);
    return { scanned: scannedJobs.length, newJobsCount: unseenJobs.length, emailSent: false };
  }
}

/**
 * Sends a sample test email to verify SMTP credentials.
 */
async function testEmailDelivery() {
  console.log(`\n--- Testing SMTP Email Connection ---`);
  const transporter = createTransporter();
  const verification = await verifyTransporter(transporter);

  if (!verification.ready) {
    console.error(`❌ SMTP Configuration Error: ${verification.error}`);
    console.log(`\nPlease configure these in your .env:`);
    console.log(`  SMTP_HOST=smtp.gmail.com`);
    console.log(`  SMTP_PORT=465`);
    console.log(`  SMTP_SECURE=true`);
    console.log(`  SMTP_USER=your_email@gmail.com`);
    console.log(`  SMTP_PASS=your_gmail_app_password`);
    console.log(`  ALERT_EMAIL_TO=recipient@gmail.com\n`);
    return;
  }

  console.log(`✅ SMTP credentials verified successfully! Sending test card...`);

  const mockJobs = [
    {
      id: "test-001",
      title: "Software Engineer Intern (Test Verification)",
      company: "Google / Example Tech",
      location: "India (Hybrid)",
      postedTime: "2 hours ago",
      link: "https://www.linkedin.com/jobs",
      isInternship: true,
      domain: "Full Stack",
    },
    {
      id: "test-002",
      title: "Junior Backend Developer (Node.js / Python)",
      company: "Stripe / Cloud Labs",
      location: "Remote",
      postedTime: "5 hours ago",
      link: "https://www.linkedin.com/jobs",
      isInternship: false,
      domain: "Backend",
    },
  ];

  const result = await sendJobAlertEmail(mockJobs);
  if (result.success) {
    console.log(`🎉 Test email delivered to ${process.env.ALERT_EMAIL_TO || process.env.SMTP_USER}! Check your inbox.`);
  } else {
    console.error(`❌ Failed to send test email: ${result.error}`);
  }
}

// Direct CLI Execution
if (require.main === module) {
  if (process.argv.includes("--test-email")) {
    testEmailDelivery();
  } else {
    runJobMonitor().catch((err) => {
      console.error("[JobMonitor] Fatal error:", err);
      process.exit(1);
    });
  }
}

module.exports = {
  runJobMonitor,
  testEmailDelivery,
};
