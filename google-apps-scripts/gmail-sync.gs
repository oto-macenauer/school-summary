/**
 * Gmail → Google Drive Sync Script
 *
 * Exports Gmail messages matching a search query to a Google Drive folder
 * as Markdown files with YAML frontmatter. The school-summary backend
 * reads these files via the Google Drive API and stores them locally.
 *
 * Setup:
 *   1. Open https://script.google.com and create a new project
 *   2. Paste this entire file as Code.gs
 *   3. Update the CONFIG object below
 *   4. Run createTrigger() once to set up automatic syncing
 *   5. Run initialSync() once to export existing messages
 */

/** @type {Object} Configuration — edit these values */
const CONFIG = {
  /**
   * Google Drive folder ID where markdown files will be saved.
   * The service account used by school-summary must have access to this folder.
   * Find the ID in the folder URL: https://drive.google.com/drive/folders/<FOLDER_ID>
   */
  MAIL_FOLDER_ID: 'YOUR_MAIL_FOLDER_ID',

  /**
   * Gmail search query. Only messages matching this query are exported.
   *
   * Examples:
   *   'label:school'
   *   'from:@skola.cz'
   *   'from:ucitel@skola.cz OR from:reditel@skola.cz'
   *   'to:rodic@gmail.com label:school'
   *   '{from:@skola.cz from:@bakalari.cz}'
   */
  GMAIL_QUERY: 'label:school',

  /** Maximum messages to process per trigger run (avoids execution time limits). */
  MAX_MESSAGES: 50,

  /** How often the trigger runs, in minutes. */
  TRIGGER_INTERVAL_MINUTES: 15,
};


// ---------------------------------------------------------------------------
// Core sync function
// ---------------------------------------------------------------------------

/**
 * Fetch new Gmail messages and save them as Markdown files in Drive.
 * Tracks processed message IDs in Script Properties to avoid duplicates.
 */
function syncGmailToDrive() {
  const folder = DriveApp.getFolderById(CONFIG.MAIL_FOLDER_ID);
  const props = PropertiesService.getScriptProperties();

  // Load set of already-processed Gmail message IDs
  const raw = props.getProperty('processedIds') || '[]';
  const processed = new Set(JSON.parse(raw));

  const threads = GmailApp.search(CONFIG.GMAIL_QUERY, 0, CONFIG.MAX_MESSAGES);
  let synced = 0;

  for (const thread of threads) {
    for (const msg of thread.getMessages()) {
      const id = msg.getId();
      if (processed.has(id)) continue;

      const md = _messageToMarkdown(msg);
      const name = _generateFilename(msg);
      folder.createFile(name, md, 'text/plain');

      processed.add(id);
      synced++;
    }
  }

  // Persist IDs — keep the most recent 10 000 to stay within quota
  const kept = Array.from(processed).slice(-10000);
  props.setProperty('processedIds', JSON.stringify(kept));

  if (synced > 0) {
    Logger.log('Synced %s new message(s) to Drive', synced);
  }
}


// ---------------------------------------------------------------------------
// Markdown conversion
// ---------------------------------------------------------------------------

/**
 * Convert a GmailMessage to a Markdown string with YAML frontmatter.
 *
 * The frontmatter format matches what the school-summary backend expects
 * in MailMessage.from_markdown():
 *   - subject, from, date (ISO 8601)
 *
 * @param {GmailMessage} msg
 * @returns {string}
 */
function _messageToMarkdown(msg) {
  const subject = msg.getSubject() || '(Bez předmětu)';
  const from = msg.getFrom() || '(Neznámý odesílatel)';
  const date = msg.getDate().toISOString();

  // Prefer plain-text body; fall back to stripped HTML
  let body = msg.getPlainBody();
  if (!body) {
    body = msg.getBody()
      .replace(/<br\s*\/?>/gi, '\n')
      .replace(/<\/p>/gi, '\n\n')
      .replace(/<[^>]+>/g, '')
      .replace(/&nbsp;/g, ' ')
      .replace(/&amp;/g, '&')
      .replace(/&lt;/g, '<')
      .replace(/&gt;/g, '>')
      .replace(/&quot;/g, '"');
  }

  return [
    '---',
    'subject: "' + _escapeYaml(subject) + '"',
    'from: "' + _escapeYaml(from) + '"',
    'date: "' + date + '"',
    '---',
    '',
    body.trim(),
  ].join('\n');
}

/**
 * Build a filename from the message date and subject.
 * Format: YYYY-MM-DD_HHMMSS_sanitised-subject.md
 *
 * @param {GmailMessage} msg
 * @returns {string}
 */
function _generateFilename(msg) {
  const d = msg.getDate();
  const pad = (n) => String(n).padStart(2, '0');
  const dateStr = [
    d.getFullYear(),
    pad(d.getMonth() + 1),
    pad(d.getDate()),
  ].join('-')
    + '_'
    + [pad(d.getHours()), pad(d.getMinutes()), pad(d.getSeconds())].join('');

  const subj = (msg.getSubject() || 'bez-predmetu')
    .replace(/[\/\\:*?"<>|]/g, '')
    .replace(/\s+/g, '_')
    .substring(0, 50);

  return dateStr + '_' + subj + '.md';
}

/** Escape double quotes inside a YAML quoted string. */
function _escapeYaml(s) {
  return s.replace(/\\/g, '\\\\').replace(/"/g, '\\"');
}


// ---------------------------------------------------------------------------
// Trigger management
// ---------------------------------------------------------------------------

/**
 * Create a time-driven trigger that runs syncGmailToDrive() periodically.
 * Run this function ONCE from the Apps Script editor.
 */
function createTrigger() {
  // Remove any existing triggers for this function first
  const existing = ScriptApp.getProjectTriggers();
  for (const t of existing) {
    if (t.getHandlerFunction() === 'syncGmailToDrive') {
      ScriptApp.deleteTrigger(t);
    }
  }

  ScriptApp.newTrigger('syncGmailToDrive')
    .timeBased()
    .everyMinutes(CONFIG.TRIGGER_INTERVAL_MINUTES)
    .create();

  Logger.log(
    'Trigger created — syncGmailToDrive will run every %s minutes',
    CONFIG.TRIGGER_INTERVAL_MINUTES
  );
}

/**
 * Remove all triggers created by this script.
 */
function removeTriggers() {
  const triggers = ScriptApp.getProjectTriggers();
  for (const t of triggers) {
    ScriptApp.deleteTrigger(t);
  }
  Logger.log('All triggers removed');
}


// ---------------------------------------------------------------------------
// Manual helpers
// ---------------------------------------------------------------------------

/**
 * Run once to export all existing messages that match the query.
 * Same as the trigger function, but useful for a first-time backfill.
 */
function initialSync() {
  syncGmailToDrive();
}

/**
 * Reset the processed-IDs tracker. After calling this, the next sync
 * will re-export all matching messages (potentially creating duplicates
 * in Drive — you may want to clear the folder first).
 */
function resetProcessedIds() {
  PropertiesService.getScriptProperties().deleteProperty('processedIds');
  Logger.log('Processed IDs cleared');
}
