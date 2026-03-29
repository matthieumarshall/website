/**
 * Utility functions for GitHub Actions lookup
 */

/**
 * Extract owner and repo from current VS Code workspace
 * Looks for .git config or git remote origin URL
 * @returns {Promise<{owner: string, repo: string}>}
 */
async function getRepositoryContext() {
  try {
    // In VS Code context, this would use the git extension or child_process
    // For now, return a helper that guides the user
    return {
      error: 'Repository context requires VS Code extension integration',
      guidance: 'Provide owner/repo explicitly or set GIT_REPO env var (e.g., "username/repo-name")'
    };
  } catch (e) {
    return { error: e.message };
  }
}

/**
 * Parse GitHub token from environment or VS Code settings
 * Priority:
 * 1. GITHUB_TOKEN env var
 * 2. GH_TOKEN env var
 * 3. VS Code GitHub extension auth
 * @returns {Promise<string|null>}
 */
async function getGitHubToken() {
  // Check environment variables
  if (process.env.GITHUB_TOKEN) {
    return process.env.GITHUB_TOKEN;
  }
  if (process.env.GH_TOKEN) {
    return process.env.GH_TOKEN;
  }

  // In VS Code context, would check extension auth
  return null;
}

/**
 * Truncate long text for readability
 * @param {string} text - Text to truncate
 * @param {number} maxLength - Max length (default: 500)
 * @returns {string}
 */
function truncate(text, maxLength = 500) {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + `\n\n... (${text.length - maxLength} more chars)`;
}

/**
 * Format JSON for markdown code block
 * @param {object} obj - Object to format
 * @returns {string}
 */
function formatJSON(obj) {
  return '```json\n' + JSON.stringify(obj, null, 2) + '\n```';
}

/**
 * Extract error message from GitHub API response
 * @param {object|string} response - API response or error
 * @returns {string}
 */
function extractErrorMessage(response) {
  if (typeof response === 'string') return response;
  if (response.message) return response.message;
  if (response.errors && Array.isArray(response.errors)) {
    return response.errors.map(e => e.message || e).join('; ');
  }
  return JSON.stringify(response);
}

module.exports = {
  getRepositoryContext,
  getGitHubToken,
  truncate,
  formatJSON,
  extractErrorMessage
};
