/**
 * GitHub Actions Run Lookup
 *
 * Fetches workflow run results from GitHub API and collects:
 * - Run summary (status, workflow, branch, trigger)
 * - Failed job details
 * - Full step logs with error messages
 *
 * Usage:
 *   const results = await fetchActionRun(inputString, token, owner, repo);
 *   console.log(results.formatted);
 */

const https = require('https');
const querystring = require('querystring');

/**
 * Parse user input for PR number or run ID
 * @param {string} input - "42", "#42", or run ID number
 * @returns {object} - { type: 'pr'|'run', value: number }
 */
function parseInput(input) {
  const trimmed = input.trim().replace(/^#/, '');
  const num = parseInt(trimmed, 10);

  if (isNaN(num)) {
    throw new Error(`Invalid input: "${input}". Expected PR number (e.g., #42) or run ID.`);
  }

  // Heuristic: run IDs are typically quite large (>10 digits), PR numbers smaller
  // If ambiguous, try PR first, fall back to run ID
  if (trimmed.length > 8) {
    return { type: 'run', value: num };
  }

  return { type: 'pr', value: num };
}

/**
 * Make authenticated HTTPS request to GitHub API
 * @param {string} path - API path (e.g., /repos/owner/repo/actions/runs)
 * @param {string} token - GitHub API token
 * @param {string} method - HTTP method (default: GET)
 * @param {object} body - Request body for POST/PATCH
 * @returns {Promise<object>} - Parsed JSON response
 */
function makeRequest(path, token, method = 'GET', body = null) {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'api.github.com',
      port: 443,
      path: path,
      method: method,
      headers: {
        'Authorization': `token ${token}`,
        'User-Agent': 'copilot-github-actions-lookup',
        'Accept': 'application/vnd.github.v3+json'
      }
    };

    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => {
        if (res.statusCode >= 400) {
          reject(new Error(`GitHub API error ${res.statusCode}: ${data}`));
          return;
        }
        try {
          resolve(JSON.parse(data));
        } catch (e) {
          reject(new Error(`Failed to parse response: ${data}`));
        }
      });
    });

    req.on('error', reject);
    if (body) req.write(JSON.stringify(body));
    req.end();
  });
}

/**
 * Get workflow run ID from PR number
 * @param {string} owner - GitHub org/user
 * @param {string} repo - Repository name
 * @param {number} prNumber - Pull request number
 * @param {string} token - GitHub API token
 * @returns {Promise<number>} - Latest run ID for the PR
 */
async function getRunIdFromPR(owner, repo, prNumber, token) {
  const path = `/repos/${owner}/${repo}/pulls/${prNumber}`;
  const pr = await makeRequest(path, token);

  if (!pr.head || !pr.head.sha) {
    throw new Error(`PR #${prNumber} not found or missing head commit`);
  }

  // Fetch runs filtered by head SHA
  const runsPath = `/repos/${owner}/${repo}/actions/runs?head_sha=${pr.head.sha}&sort=created&order=desc&per_page=1`;
  const runsData = await makeRequest(runsPath, token);

  if (!runsData.workflow_runs || runsData.workflow_runs.length === 0) {
    throw new Error(`No workflow runs found for PR #${prNumber}`);
  }

  return runsData.workflow_runs[0].id;
}

/**
 * Format run summary as markdown
 * @param {object} run - Workflow run object from GitHub API
 * @returns {string} - Formatted markdown summary
 */
function formatRunSummary(run) {
  const status = run.status === 'completed' ? run.conclusion : run.status;
  const statusEmoji = {
    'success': '✅',
    'failure': '❌',
    'neutral': '⏸️',
    'cancelled': '🚫',
    'skipped': '⏭️',
    'timed_out': '⏱️',
    'action_required': '⚠️',
    'in_progress': '⏳',
    'queued': '⌛',
    'requested': '📋',
    'waiting': '⏳'
  }[status] || '❓';

  const createdAt = new Date(run.created_at).toLocaleString();
  const duration = Math.round((new Date(run.updated_at) - new Date(run.created_at)) / 1000);

  return `
## Workflow Run Summary

${statusEmoji} **Status**: ${status.toUpperCase()}
📋 **Workflow**: ${run.name}
🔢 **Run ID**: [\`${run.id}\`](${run.html_url})
🌿 **Branch**: \`${run.head_branch}\`
⚡ **Event**: ${run.event}
📅 **Created**: ${createdAt}
⏱️ **Duration**: ${Math.floor(duration / 60)}m ${duration % 60}s
👤 **Actor**: ${run.actor?.login || 'unknown'}
🔗 **View on GitHub**: [${run.html_url}](${run.html_url})
`;
}

/**
 * Format detailed job logs as markdown
 * @param {array} jobs - Array of job objects from GitHub API
 * @param {string} owner - GitHub org/user
 * @param {string} repo - Repository name
 * @param {number} runId - Run ID
 * @param {string} token - GitHub API token
 * @returns {Promise<string>} - Formatted markdown with job details
 */
async function formatJobDetails(jobs, owner, repo, runId, token) {
  if (!jobs || jobs.length === 0) {
    return '\n## Jobs\nNo jobs found.';
  }

  let output = '\n## Job Details\n';

  for (const job of jobs) {
    const statusEmoji = {
      'success': '✅',
      'failure': '❌',
      'skipped': '⏭️',
      'cancelled': '🚫'
    }[job.conclusion] || '❓';

    output += `\n### ${statusEmoji} ${job.name}\n`;
    output += `- **Status**: ${job.conclusion || job.status}\n`;
    output += `- **Run number**: ${job.run_number}\n`;
    output += `- **Started**: ${new Date(job.started_at).toLocaleString()}\n`;
    output += `- **Completed**: ${new Date(job.completed_at).toLocaleString()}\n`;

    // Only fetch logs for failed or errored jobs
    if (job.conclusion === 'failure' || job.conclusion === 'cancelled') {
      try {
        const logsUrl = `/repos/${owner}/${repo}/actions/jobs/${job.id}/logs`;
        const logs = await makeRequest(logsUrl, token);
        if (logs) {
          output += `\n#### Logs\n\`\`\`\n${logs.slice(0, 2000)}\n...\n\`\`\`\n`;
        }
      } catch (e) {
        output += `\n#### Logs\nFailed to fetch logs: ${e.message}\n`;
      }
    }
  }

  return output;
}

/**
 * Main function: fetch and format GitHub Actions run results
 * @param {string} input - User input (PR number or run ID)
 * @param {string} token - GitHub API token
 * @param {string} owner - GitHub org/user
 * @param {string} repo - Repository name
 * @returns {Promise<object>} - { summary, details, formatted }
 */
async function fetchActionRun(input, token, owner, repo) {
  if (!token) {
    throw new Error('GitHub token not available. Set GITHUB_TOKEN environment variable or authenticate with GitHub extension.');
  }

  const parsed = parseInput(input);
  let runId = parsed.value;

  // If PR number, fetch the corresponding run ID
  if (parsed.type === 'pr') {
    console.log(`Fetching latest run for PR #${runId}...`);
    runId = await getRunIdFromPR(owner, repo, runId, token);
  }

  console.log(`Fetching run details for ID ${runId}...`);

  // Fetch run summary
  const run = await makeRequest(
    `/repos/${owner}/${repo}/actions/runs/${runId}`,
    token
  );

  // Fetch jobs in the run
  const jobsData = await makeRequest(
    `/repos/${owner}/${repo}/actions/runs/${runId}/jobs`,
    token
  );

  const jobs = jobsData.jobs || [];

  // Format output
  const summary = formatRunSummary(run);
  const jobDetails = await formatJobDetails(jobs, owner, repo, runId, token);

  return {
    summary,
    jobDetails,
    formatted: summary + jobDetails,
    raw: { run, jobs }
  };
}

module.exports = {
  parseInput,
  getRunIdFromPR,
  formatRunSummary,
  formatJobDetails,
  fetchActionRun
};
