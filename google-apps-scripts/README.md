# Google Apps Scripts Setup

This folder contains the automation scripts that feed data into the
**school-summary** application. Two separate Apps Script projects are needed:

| Script | Purpose | Runs as |
|--------|---------|---------|
| [`gdrive-sync.gs`](gdrive-sync.gs) | Mirrors the school's shared weekly-reports folder to a folder you own | Hourly trigger |
| [`gmail-sync.gs`](gmail-sync.gs) | Exports school-related Gmail messages as Markdown files to Drive | Every 15 min |

### Data flow

```
School's shared folder ──► gdrive-sync.gs ──► Your reports folder ──┐
                                                                     ├──► Service account ──► Backend
Gmail inbox ──► gmail-sync.gs ──► Your mail folder ──────────────────┘
```

The backend reads both folders via a Google Cloud **service account**.
Because the school's shared folder is typically read-only (Viewer access),
`gdrive-sync.gs` copies files to a folder you own so the service account
can access them.

---

## 1. Google Cloud Service Account

The service account lets the backend read from Google Drive without
interactive login.

### Create the service account

1. Go to the [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or reuse an existing one)
3. Enable the **Google Drive API**:
   - *APIs & Services → Library → search "Google Drive API" → Enable*
4. Create a service account:
   - *APIs & Services → Credentials → Create Credentials → Service Account*
   - Name: e.g. `school-summary-reader`
   - No roles needed (it only accesses shared folders)
5. Create a JSON key:
   - Click the service account → *Keys → Add Key → Create new key → JSON*
   - Save the downloaded `.json` file
6. Place it where the backend can reach it:
   - **Docker**: inside the mounted `app_data/` directory,
     e.g. `/app/app_data/service_account.json`
   - **Local dev**: `backend/app_data/service_account.json`

### Note the service account email

Open the JSON file and find the `client_email` field:

```
school-summary-reader@my-project.iam.gserviceaccount.com
```

You will share Drive folders with this address in the next steps.

---

## 2. Google Drive Folders

Create **two folders** in your own Google Drive (the parent account):

### A) Reports folder (weekly reports)

This is the destination for `gdrive-sync.gs`. The service account reads
weekly reports from here.

1. Create a folder, e.g. `Školní reporty – kopie`
2. **Share it** with the service account email (Viewer access is enough)
3. Copy the **folder ID** from the URL:
   `https://drive.google.com/drive/folders/`**`<FOLDER_ID>`**
4. This will be the `reports_folder_id` (or per-student `gdrive_folder_id`)
   in `config.yaml`

#### Expected contents

After `gdrive-sync.gs` runs, the folder mirrors the school's shared folder:

```
Školní reporty – kopie/
├── Týden 1.docx              ← files directly in root
├── Týden 2.docx
├── Září/                      ← or inside month subfolders
│   ├── Týden 3.docx
│   └── Týden 4.docx
└── 5/                         ← or week-number folders
    └── report.docx
```

The backend extracts the week number from filenames. Supported patterns:

| Pattern | Example |
|---------|---------|
| `Týden N` | `Týden 14.docx` |
| `Week N` | `Week 14.docx` |
| `W N` / `W_N` | `W 14.docx` |
| Number only | `14.docx` |
| With date range | `Týden 16 (15.12-19.12).docx` |

Supported formats: **Google Docs**, **DOCX**, **plain text**.

### B) Mail folder (exported Gmail)

This is the destination for `gmail-sync.gs`.

1. Create a folder, e.g. `Školní maily`
2. **Share it** with the service account email (Viewer access is enough)
3. Copy the **folder ID**
4. This will be the `mail_folder_id` in `config.yaml`

If you have multiple students, create a separate mail folder per student.

---

## 3. Deploy `gdrive-sync.gs` — Weekly Reports Mirror

This script copies the school's shared folder (where you're only a Viewer)
to a folder you own.

### Setup

1. Open [Google Apps Script](https://script.google.com/) and create a
   **new project** (name it e.g. "GDrive Report Sync")
2. Replace the default `Code.gs` with the contents of
   [`gdrive-sync.gs`](gdrive-sync.gs)
3. Set the two folder IDs at the top of the file:

   ```javascript
   /** Shared folder you have Viewer access to (source of truth). */
   const SOURCE_FOLDER_ID = "1uITr259T...";   // ← school's folder

   /** Your own folder where copies are stored. */
   const DEST_FOLDER_ID = "1Z5oSruO5...";     // ← your reports folder from step 2A
   ```

4. **Save** (Ctrl+S)

### First run

1. Select `syncFolder` from the function dropdown → click **Run**
2. Authorise Drive access when prompted
3. Check the execution log — you should see "Copied: ..." lines
4. Verify the files appeared in your destination folder

### Set up automatic sync

1. Select `createTrigger` from the dropdown → click **Run**
2. The script will now run every hour
3. You can verify under *Triggers* (clock icon in sidebar)

### How it works

- Recursively walks the source folder (including month subfolders)
- Copies new files that don't exist in the destination
- Replaces files in the destination if the source version is newer
  (trashes the old copy, creates a fresh one)
- Creates matching subfolders automatically

---

## 4. Deploy `gmail-sync.gs` — Email Export

This script exports school-related Gmail messages as Markdown files into
a Drive folder, which the backend then syncs.

### Setup

1. Open [Google Apps Script](https://script.google.com/) and create a
   **new project** (name it e.g. "Gmail School Sync")
2. Replace the default `Code.gs` with the contents of
   [`gmail-sync.gs`](gmail-sync.gs)
3. Update the `CONFIG` object:

   ```javascript
   const CONFIG = {
     MAIL_FOLDER_ID: 'paste_your_mail_folder_id',   // ← from step 2B
     GMAIL_QUERY: 'label:school',                    // ← adjust to your needs
     MAX_MESSAGES: 50,
     TRIGGER_INTERVAL_MINUTES: 15,
   };
   ```

4. **Save** (Ctrl+S)

### Configure the Gmail query

The `GMAIL_QUERY` determines which emails are exported. Use standard
[Gmail search operators](https://support.google.com/mail/answer/7190):

| Use case | Query |
|----------|-------|
| All from school domain | `from:@skola.cz` |
| Specific senders | `from:ucitel@skola.cz OR from:reditel@skola.cz` |
| By Gmail label | `label:school` |
| From Bakaláři system | `from:@bakalari.cz` |
| Combined (OR) | `{from:@skola.cz from:@bakalari.cz}` |

**Tip**: Create a Gmail filter that auto-labels school messages with a
`school` label, then use `label:school`.

### First run

1. Select `initialSync` from the dropdown → click **Run**
2. Authorise Gmail + Drive access when prompted
3. Check the execution log for output
4. Verify `.md` files appeared in your mail Drive folder

### Set up automatic sync

1. Select `createTrigger` from the dropdown → click **Run**
2. The script will now run every 15 minutes

### Output format

Each email becomes `YYYY-MM-DD_HHMMSS_subject.md`:

```markdown
---
subject: "Informace k výletu"
from: "Mgr. Nováková <novakova@skola.cz>"
date: "2026-03-10T08:15:00.000Z"
---

Vážení rodiče,

informujeme Vás o plánovaném výletu...
```

### Deduplication

The script tracks processed Gmail message IDs in Script Properties.
Re-running won't create duplicates. The backend also deduplicates by
Google Drive file ID — each file is downloaded only once.

To re-export everything (e.g. after clearing the Drive folder), run
`resetProcessedIds()`.

---

## 5. Application Configuration

Once both scripts are deployed and folders are set up, update
`app_data/config.yaml`:

```yaml
gdrive:
  # Path to the service account JSON key file
  service_account_path: "/app/app_data/service_account.json"

  # Folder ID of your reports copy (destination of gdrive-sync.gs)
  reports_folder_id: "1Z5oSruO5yO9HUdD7zK5NDHkMvlVdkuME"

  # Optional: override school year start (default: auto-detected from Sept 1)
  # school_year_start: "2025-09-01"

students:
  - name: "Jan"
    username: "jan.novak"
    password: "***"

    # Optional: per-student override for reports folder
    # gdrive_folder_id: "different_folder_id"

    # Folder ID where gmail-sync.gs saves markdown files
    mail_folder_id: "9z8Y7x6W5v4U3t2S1r"

update_intervals:
  gdrive: 3600    # check for new reports every hour
  mail: 900       # check for new mail files every 15 minutes
```

### Docker volumes

The service account JSON must be accessible inside the container:

```yaml
services:
  backend:
    volumes:
      - ${PATH_TO_APPDATA}/school-summary:/app/app_data
      # Place service_account.json inside this directory
```

---

## 6. Verification

After everything is configured:

1. **Check the Admin panel** → Scheduler section
   - `gdrive:{student}` and `mail:{student}` tasks should show `success`
2. **Check the Dashboard** → AI summaries should reference report and
   mail content
3. **Check Zprávy (Resources)** → exported mail messages should appear
   alongside Komens messages

### Troubleshooting

| Problem | Solution |
|---------|----------|
| `gdrive` task shows error | Check service account JSON path; verify the reports folder is shared with the service account email |
| `mail` task shows error | Same as above; also verify `mail_folder_id` is correct |
| No files in reports folder | Run `syncFolder()` manually in the GDrive Sync script; check the execution log |
| No `.md` files in mail folder | Run `initialSync()` manually in the Gmail Sync script; check execution log; verify the Gmail query matches messages |
| Reports not detected | The app needs week numbers in filenames — see naming patterns above |
| Permission denied (403) | Make sure the folder is shared with the service account's `client_email` |

---

## 7. Multiple Students

For multiple students in one household:

- **Reports**: If the school uses one shared folder per student, create
  separate destination folders and set `gdrive_folder_id` per student.
  If reports are shared, one folder is enough.
- **Mail**: Create a separate mail folder per student. If all school emails
  arrive at one Gmail account, use different Gmail labels/queries and
  deploy separate Apps Script projects, each writing to a different folder.

```yaml
students:
  - name: "Jan"
    gdrive_folder_id: "reports_for_jan"
    mail_folder_id: "mail_for_jan"

  - name: "Marie"
    gdrive_folder_id: "reports_for_marie"
    mail_folder_id: "mail_for_marie"
```
