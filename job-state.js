/**
 * job-state.js
 * ------------
 * Persistent de-duplication store for tech job and internship alerts.
 * Ensures the user NEVER receives duplicate email notifications.
 * Prunes records older than 14 days automatically.
 */

const fs = require("fs");
const path = require("path");

const STATE_FILE = path.join(__dirname, "jobs-seen.json");
const MAX_AGE_MS = 14 * 24 * 60 * 60 * 1000; // 14 days

class JobStateStore {
  constructor(filePath = STATE_FILE) {
    this.filePath = filePath;
    this.seenJobs = this._load();
  }

  _load() {
    try {
      if (fs.existsSync(this.filePath)) {
        const raw = fs.readFileSync(this.filePath, "utf8");
        const parsed = JSON.parse(raw);
        if (Array.isArray(parsed)) {
          return parsed;
        }
      }
    } catch (err) {
      console.warn(`[JobState] Warning: Failed to load ${this.filePath}, resetting:`, err.message);
    }
    return [];
  }

  _save() {
    try {
      // Auto-prune entries older than 14 days
      const cutoff = Date.now() - MAX_AGE_MS;
      this.seenJobs = this.seenJobs.filter(
        (job) => job.seenAt && new Date(job.seenAt).getTime() > cutoff
      );

      fs.writeFileSync(this.filePath, JSON.stringify(this.seenJobs, null, 2), "utf8");
    } catch (err) {
      console.error(`[JobState] Error saving state to ${this.filePath}:`, err.message);
    }
  }

  /**
   * Check if a job ID has already been notified.
   * @param {string} jobId
   * @returns {boolean}
   */
  hasSeen(jobId) {
    if (!jobId) return false;
    return this.seenJobs.some((j) => String(j.id) === String(jobId));
  }

  /**
   * Mark a list of jobs as seen.
   * @param {Array<{id: string, title?: string, company?: string}>} jobs
   */
  markSeen(jobs) {
    if (!Array.isArray(jobs) || jobs.length === 0) return;
    const now = new Date().toISOString();

    for (const job of jobs) {
      if (job.id && !this.hasSeen(job.id)) {
        this.seenJobs.push({
          id: String(job.id),
          title: job.title || "",
          company: job.company || "",
          seenAt: now,
        });
      }
    }

    this._save();
  }

  /**
   * Filter an array of jobs, returning only previously unseen jobs.
   * @param {Array<{id: string}>} jobs
   * @returns {Array<{id: string}>}
   */
  filterUnseen(jobs) {
    if (!Array.isArray(jobs)) return [];
    return jobs.filter((job) => !this.hasSeen(job.id));
  }

  /**
   * Return count of stored seen jobs.
   */
  count() {
    return this.seenJobs.length;
  }
}

module.exports = new JobStateStore();
