/**
 * Google Apps Script: Sync shared folder to your own Drive.
 *
 * Setup:
 * 1. Go to https://script.google.com and create a new project
 * 2. Paste this code
 * 3. Set SOURCE_FOLDER_ID to the shared folder ID (the one you're a viewer of)
 * 4. Set DEST_FOLDER_ID to your own Drive folder ID
 * 5. Run syncFolder() once manually (it will ask for Drive permissions)
 * 6. Set up a trigger: Edit > Triggers > Add Trigger
 *    - Function: syncFolder
 *    - Event source: Time-driven
 *    - Type: Hour timer (every 1 hour)
 */

const SOURCE_FOLDER_ID = "1uITr259T-4DH_HrpA6Q3l848cN-HmO8f";  // shared folder
const DEST_FOLDER_ID = "";  // your own folder — fill this in

function syncFolder() {
  const source = DriveApp.getFolderById(SOURCE_FOLDER_ID);
  const dest = DriveApp.getFolderById(DEST_FOLDER_ID);
  syncRecursive(source, dest);
  Logger.log("Sync complete: " + new Date().toISOString());
}

function syncRecursive(sourceFolder, destFolder) {
  // Sync files
  const sourceFiles = sourceFolder.getFiles();
  const destFileNames = getFileMap(destFolder);

  while (sourceFiles.hasNext()) {
    const file = sourceFiles.next();
    const name = file.getName();
    const sourceModified = file.getLastUpdated();

    if (destFileNames[name]) {
      const destFile = destFileNames[name];
      // Update only if source is newer
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

  // Sync subfolders (month folders like December, January, etc.)
  const sourceSubfolders = sourceFolder.getFolders();
  const destFolderNames = getFolderMap(destFolder);

  while (sourceSubfolders.hasNext()) {
    const subfolder = sourceSubfolders.next();
    const name = subfolder.getName();

    let destSubfolder;
    if (destFolderNames[name]) {
      destSubfolder = destFolderNames[name];
    } else {
      destSubfolder = destFolder.createFolder(name);
      Logger.log("Created folder: " + name);
    }

    syncRecursive(subfolder, destSubfolder);
  }
}

function getFileMap(folder) {
  const map = {};
  const files = folder.getFiles();
  while (files.hasNext()) {
    const f = files.next();
    map[f.getName()] = f;
  }
  return map;
}

function getFolderMap(folder) {
  const map = {};
  const folders = folder.getFolders();
  while (folders.hasNext()) {
    const f = folders.next();
    map[f.getName()] = f;
  }
  return map;
}
