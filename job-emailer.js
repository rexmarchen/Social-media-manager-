/**
 * job-emailer.js
 * --------------
 * Production-grade email dispatcher for Tech Job & Internship alerts.
 * Builds responsive, sleek HTML email cards and sends via Nodemailer.
 */

const nodemailer = require("nodemailer");
require("dotenv").config();

/**
 * Creates and configures the Nodemailer transporter.
 */
function createTransporter() {
  const host = process.env.SMTP_HOST || "smtp.gmail.com";
  const port = parseInt(process.env.SMTP_PORT || "465", 10);
  const secure = process.env.SMTP_SECURE !== "false"; // default true for 465
  const user = process.env.SMTP_USER;
  const pass = process.env.SMTP_PASS;

  if (!user || !pass) {
    return null;
  }

  return nodemailer.createTransport({
    host,
    port,
    secure,
    auth: {
      user,
      pass,
    },
  });
}

/**
 * Verifies SMTP connection.
 * @returns {Promise<{ready: boolean, error?: string}>}
 */
async function verifyTransporter(transporter) {
  if (!transporter) {
    return {
      ready: false,
      error: "SMTP_USER and/or SMTP_PASS are not configured in your .env file.",
    };
  }

  try {
    await transporter.verify();
    return { ready: true };
  } catch (err) {
    return {
      ready: false,
      error: `SMTP connection failed: ${err.message}. If using Gmail, make sure you generated an App Password (not your normal password).`,
    };
  }
}

/**
 * Generates responsive HTML email template for the job list.
 * @param {Array<object>} jobs
 * @param {object} meta
 * @returns {string}
 */
function buildHtmlEmail(jobs, meta = {}) {
  const scanTime = meta.scanTime || new Date().toLocaleString("en-US", { timeZone: "Asia/Kolkata" });
  const internshipCount = jobs.filter((j) => j.isInternship).length;
  const fulltimeCount = jobs.length - internshipCount;

  const jobCardsHtml = jobs
    .map((job) => {
      const typeBadgeColor = job.isInternship ? "#8b5cf6" : "#0284c7";
      const typeBadgeText = job.isInternship ? "🎓 Internship" : "💼 Tech Role";
      const domainBadge = job.domain ? `<span style="background: #334155; color: #f1f5f9; padding: 3px 8px; border-radius: 9999px; font-size: 11px; font-weight: 600; margin-left: 6px;">${job.domain}</span>` : "";

      return `
        <div style="background-color: #1e293b; border: 1px solid #334155; border-radius: 12px; padding: 18px; margin-bottom: 16px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2);">
          <div style="margin-bottom: 8px;">
            <span style="background-color: ${typeBadgeColor}; color: #ffffff; padding: 3px 10px; border-radius: 9999px; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.5px;">${typeBadgeText}</span>
            <span style="background-color: #059669; color: #ffffff; padding: 3px 10px; border-radius: 9999px; font-size: 11px; font-weight: 700; margin-left: 6px;">⏱️ ${job.postedTime}</span>
            ${domainBadge}
          </div>

          <h3 style="margin: 8px 0 4px 0; font-size: 18px; font-weight: 700; color: #ffffff; line-height: 1.3;">
            ${job.title}
          </h3>

          <div style="color: #94a3b8; font-size: 14px; margin-bottom: 12px;">
            <strong style="color: #38bdf8;">${job.company}</strong> &bull; 📍 ${job.location || "Remote / Unspecified"}
          </div>

          <div style="margin-top: 14px;">
            <a href="${job.link}" target="_blank" rel="noopener noreferrer" style="display: inline-block; background: linear-gradient(135deg, #0ea5e9 0%, #2563eb 100%); color: #ffffff; text-decoration: none; padding: 10px 18px; border-radius: 8px; font-size: 13px; font-weight: 600; text-align: center;">
              Apply on LinkedIn &rarr;
            </a>
          </div>
        </div>
      `;
    })
    .join("\n");

  return `
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>New Tech Jobs & Internships</title>
</head>
<body style="margin: 0; padding: 20px; background-color: #0f172a; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #f8fafc;">
  <div style="max-width: 640px; margin: 0 auto; background-color: #0f172a;">
    
    <!-- Header -->
    <div style="padding: 24px 0 20px 0; border-bottom: 1px solid #1e293b; margin-bottom: 24px;">
      <div style="display: inline-block; background-color: #0284c7; color: #ffffff; padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: bold; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px;">
        🚀 Fresh Tech Alerts (&lt; 12h)
      </div>
      <h1 style="margin: 0 0 8px 0; font-size: 24px; font-weight: 800; color: #ffffff;">
        ${jobs.length} New Tech Jobs & Internships
      </h1>
      <p style="margin: 0; color: #94a3b8; font-size: 14px;">
        Found <strong style="color: #c084fc;">${internshipCount} Internships</strong> and <strong style="color: #38bdf8;">${fulltimeCount} Engineering Roles</strong> posted strictly under 12 hours ago.
      </p>
      <p style="margin: 4px 0 0 0; color: #64748b; font-size: 12px;">
        Scanned at: ${scanTime} (IST)
      </p>
    </div>

    <!-- Job Cards List -->
    <div>
      ${jobCardsHtml}
    </div>

    <!-- Footer -->
    <div style="margin-top: 32px; padding-top: 20px; border-top: 1px solid #1e293b; text-align: center; color: #64748b; font-size: 12px; line-height: 1.5;">
      <p style="margin: 0 0 4px 0;">
        ⚡ Automated Tech Job & Internship Watchdog. Powered by LinkedIn Guest Engine.
      </p>
      <p style="margin: 0;">
        Only positions posted strictly under 12 hours ago are surfaced. Duplicate alerts are automatically suppressed.
      </p>
    </div>

  </div>
</body>
</html>
  `;
}

/**
 * Generates plain-text version for email clients that do not support HTML.
 * @param {Array<object>} jobs
 * @returns {string}
 */
function buildPlainTextEmail(jobs) {
  let text = `🚀 FRESH TECH JOBS & INTERNSHIPS (< 12 HOURS)\n`;
  text += `Found ${jobs.length} new positions posted strictly under 12 hours ago.\n\n`;

  jobs.forEach((job, index) => {
    const type = job.isInternship ? "[INTERNSHIP]" : "[TECH ROLE]";
    text += `${index + 1}. ${type} ${job.title}\n`;
    text += `   Company: ${job.company}\n`;
    text += `   Location: ${job.location || "N/A"}\n`;
    text += `   Posted: ${job.postedTime}\n`;
    text += `   Apply: ${job.link}\n\n`;
  });

  text += `---\nSent by LinkedIn Automation Job Monitor.\n`;
  return text;
}

/**
 * Sends the email alert with the given list of fresh jobs.
 * @param {Array<object>} jobs
 * @param {object} options
 * @returns {Promise<{success: boolean, messageId?: string, error?: string, simulated?: boolean}>}
 */
async function sendJobAlertEmail(jobs, options = {}) {
  if (!Array.isArray(jobs) || jobs.length === 0) {
    return { success: false, error: "No jobs to send." };
  }

  const transporter = createTransporter();
  const recipient = options.to || process.env.ALERT_EMAIL_TO || process.env.SMTP_USER;

  if (!transporter || !recipient) {
    console.warn(`[JobEmailer] Warning: SMTP not fully configured. Set SMTP_USER, SMTP_PASS, and ALERT_EMAIL_TO in .env.`);
    return {
      success: false,
      error: "SMTP credentials or ALERT_EMAIL_TO not found in .env.",
      simulated: true,
    };
  }

  const internshipCount = jobs.filter((j) => j.isInternship).length;
  const techCount = jobs.length - internshipCount;
  const subject = `🔥 [${jobs.length} New Tech Jobs & Internships] - Fresh < 12h (${internshipCount} Internships, ${techCount} Engineering)`;

  const html = buildHtmlEmail(jobs, {
    scanTime: new Date().toLocaleString("en-US", { timeZone: process.env.TIMEZONE || "Asia/Kolkata" }),
  });
  const text = buildPlainTextEmail(jobs);

  try {
    const info = await transporter.sendMail({
      from: `"Tech Job Watchdog" <${process.env.SMTP_USER}>`,
      to: recipient,
      subject,
      text,
      html,
    });

    console.log(`[JobEmailer] ✅ Email alert sent successfully! MessageId: ${info.messageId}`);
    return { success: true, messageId: info.messageId };
  } catch (err) {
    console.error(`[JobEmailer] ❌ Failed to send email alert:`, err.message);
    return { success: false, error: err.message };
  }
}

module.exports = {
  createTransporter,
  verifyTransporter,
  buildHtmlEmail,
  buildPlainTextEmail,
  sendJobAlertEmail,
};
