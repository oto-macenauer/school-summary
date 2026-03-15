/**
 * Google Apps Script: Sync a shared Google Drive folder to your own Drive.
 *
 * Use case: The school shares a weekly-reports folder where you only have
 * Viewer access. This script copies (and keeps updated) all files into a
 * folder you own, so the school-summary service account can read them.
 *
 * Setup:
 *   1. Go to https://script.google.com and create a new project
 *   2. Paste this code as Code.gs
 *   3. Set SOURCE_FOLDER_ID to the shared folder ID (the one you're a viewer of)
 *   4. Set DEST_FOLDER_ID to your own Drive folder ID
 *   5. Run syncFolder() once manually (it will ask for Drive permissions)
 *   6. Run createTrigger() to set up automatic hourly sync
 */

/** Shared folder you have Viewer access to (source of truth). */
const SOURCE_FOLDER_ID = "YOUR_SOURCE_FOLDER_ID";

/** Your own folder where copies are stored (share this with the service account). */
const DEST_FOLDER_ID = "YOUR_DEST_FOLDER_ID";


// ---------------------------------------------------------------------------
// Core sync
// ---------------------------------------------------------------------------

function syncFolder() {
  const source = DriveApp.getFolderById(SOURCE_FOLDER_ID);
  const dest = DriveApp.getFolderById(DEST_FOLDER_ID);
  _syncRecursive(source, dest);
  Logger.log("Sync complete: " + new Date().toISOString());
}

/**
 * Recursively copy new/updated files and mirror subfolders.
 * Subfolders typically represent months (e.g. "Září", "Říjen").
 */
function _syncRecursive(sourceFolder, destFolder) {
  // --- Files ---
  const sourceFiles = sourceFolder.getFiles();
  const destFileMap = _getFileMap(destFolder);

  while (sourceFiles.hasNext()) {
    const file = sourceFiles.next();
    const name = file.getName();
    const sourceModified = file.getLastUpdated();

    if (destFileMap[name]) {
      const destFile = destFileMap[name];
      // Replace only if the source is newer
      if (sourceModified > destFile.getLastUpdated()) {
        destFile.setTrashed(true);
        file.makeCopy(name, destFolder);
        Logger.log("Updated: " + name);
      }
    } else {
      file.makeCopy(name, destFolder);
      Logger.log("Copied: " + name);
    }
  }

  // --- Subfolders ---
  const sourceSubfolders = sourceFolder.getFolders();
  const destFolderMap = _getFolderMap(destFolder);

  while (sourceSubfolders.hasNext()) {
    const subfolder = sourceSubfolders.next();
    const name = subfolder.getName();

    let destSubfolder;
    if (destFolderMap[name]) {
      destSubfolder = destFolderMap[name];
    } else {
      destSubfolder = destFolder.createFolder(name);
      Logger.log("Created folder: " + name);
    }

    _syncRecursive(subfolder, destSubfolder);
  }
}


// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function _getFileMap(folder) {
  const map = {};
  const files = folder.getFiles();
  while (files.hasNext()) {
    const f = files.next();
    map[f.getName()] = f;
  }
  return map;
}

function _getFolderMap(folder) {
  const map = {};
  const folders = folder.getFolders();
  while (folders.hasNext()) {
    const f = folders.next();
    map[f.getName()] = f;
  }
  return map;
}


// ---------------------------------------------------------------------------
// Trigger management
// ---------------------------------------------------------------------------

/**
 * Create an hourly trigger for syncFolder().
 * Run this function ONCE from the Apps Script editor.
 */
function createTrigger() {
  // Remove existing triggers for this function
  for (const t of ScriptApp.getProjectTriggers()) {
    if (t.getHandlerFunction() === 'syncFolder') {
      ScriptApp.deleteTrigger(t);
    }
  }

  ScriptApp.newTrigger('syncFolder')
    .timeBased()
    .everyHours(1)
    .create();

  Logger.log('Trigger created — syncFolder will run every hour');
}

/**
 * Remove all triggers created by this script.
 */
function removeTriggers() {
  for (const t of ScriptApp.getProjectTriggers()) {
    ScriptApp.deleteTrigger(t);
  }
  Logger.log('All triggers removed');
}
