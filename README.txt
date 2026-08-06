BLAUGUST BLOGROLL — SINGLE-SOURCE SETUP
=======================================

PURPOSE
-------
This version uses one authoritative file:

    data/blogs.csv

Both the alphabetical blog directory and the twenty latest posts are generated
from that CSV. Once installed, routine changes should normally require editing
only this one file in GitHub.

CURRENT IMPORT
--------------
The master CSV was created from Feedly Blogroll.opml supplied on 6 August 2026.
It contains 272 rows:

- 271 visible directory entries
- 8 entries in the Other Languages section
- 1 disabled legacy duplicate for Orbital Martian

The original and previous OPML files are retained under data/archive for
reference only. They are not used by the live system.

MASTER CSV COLUMNS
------------------
name
    The blog name shown to visitors.

site_url
    The address opened when a visitor selects the blog.

feed_url
    The RSS or Atom feed checked for the latest-post panel.

language
    Administrative label. The eight obvious non-English-script blogs have
    initially been marked Japanese, Chinese or Arabic. Other rows are marked
    Unspecified because OPML does not contain dependable language metadata.

directory_group
    Use alphabetical or other-languages.

status
    Administrative note such as included, inactive or duplicate. This field
    does not itself hide a row.

show_in_directory
    yes = display the blog in the directory
    no  = keep the row in the master file but hide it from the directory

include_in_latest
    yes = check the feed for the twenty latest posts
    no  = do not check the feed

notes
    Optional maintenance notes. These are never published on the website.

HOW TO EDIT THE LIST LATER
--------------------------
1. Open data/blogs.csv in the GitHub repository.
2. Select the pencil icon to edit it.
3. Change, add or remove rows.
4. Commit the change to the main branch.
5. GitHub Actions validates the CSV, rebuilds the directory, checks eligible
   feeds and republishes GitHub Pages.

The Squarespace page then loads the revised data automatically. No fresh OPML
export or replacement of the directory HTML should be necessary.

IMPORTANT CSV RULES
-------------------
- Do not rename or remove the header row.
- Each feed_url must be unique.
- site_url and feed_url must begin with http:// or https://.
- show_in_directory and include_in_latest should contain yes or no.
- directory_group must be alphabetical or other-languages.
- If a field contains a comma, GitHub's CSV editor must retain quotation marks
  around that field.

FILES TO UPLOAD TO GITHUB
--------------------------
Upload the complete contents of this folder to the existing
blaugust-recent-posts repository, preserving the folder structure.

The active new files are:

- data/blogs.csv
- scripts/build_site_data.py
- .github/workflows/update-recent-posts.yml
- squarespace-blog-directory-widget.txt
- squarespace-directory-iframe-fallback.txt
- docs/directory.html

The workflow will generate and maintain:

- docs/blog-directory.json
- docs/blog-directory-data.js
- docs/latest-posts.json
- docs/latest-posts-data.js
- data/feed-cache.json

OLD FILES TO REMOVE FROM GITHUB
-------------------------------
After the new files are uploaded, delete these old active files from the root
repository if they remain there:

- data/feedly.opml
- data/overrides.json
- scripts/build_recent_posts.py
- layout-preview.html

Copies of the old OPML and overrides are included in data/archive.

FIRST GITHUB TEST
-----------------
1. Open the repository's Actions tab.
2. Select "Update Blaugust directory and recent posts".
3. Select Run workflow.
4. Wait for the run to show a green tick.
5. Check these GitHub Pages addresses, replacing YOUR-GITHUB-USERNAME:

   https://YOUR-GITHUB-USERNAME.github.io/blaugust-recent-posts/
   https://YOUR-GITHUB-USERNAME.github.io/blaugust-recent-posts/directory.html

SQUARESPACE CHANGE
------------------
The existing recent-post widget can remain in place because it continues to use
latest-posts-data.js at the same address.

Replace the old static alphabetical directory code with the contents of:

    squarespace-blog-directory-widget.txt

Before pasting, replace YOUR-GITHUB-USERNAME with the same GitHub username used
in the existing recent-post widget.

The new directory provides:

- All, 0-9 and A-Z filtering buttons
- an Other Languages button
- a blog-name search box
- automatic totals
- two-column desktop and one-column mobile layouts

ROLLBACK
--------
Do not remove the existing Squarespace directory until the GitHub Pages preview
works. Keep a copy of the old Squarespace code temporarily. If a problem occurs,
restore that old code while the repository is corrected.

LOCAL VALIDATION
----------------
The CSV and directory can be validated without checking external feeds:

    python scripts/build_site_data.py --directory-only

The normal GitHub workflow runs without that option and therefore also checks
all feeds enabled by include_in_latest.
