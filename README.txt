BLAUGUST RECENT POSTS — SETUP GUIDE
===================================

WHAT THIS DOES
--------------
This package checks the 259 RSS/Atom feeds in your Feedly OPML file twice each
day. It keeps one newest dated post per blog, sorts those posts newest-first and
publishes the newest 20 as one small data file. Your Squarespace page makes one
request for that file rather than contacting 259 blogs.

Temporary feed failures do not normally make an entry disappear: the script
keeps the last successful result in data/feed-cache.json.

The updater is scheduled for 07:17 and 19:17 Europe/London time. The odd minute
is intentional, because scheduled services are commonly busiest on the hour.

GITHUB SETUP
------------
1. Sign in to GitHub and create a new PUBLIC repository named exactly:

       blaugust-recent-posts

2. Unzip this package. On the new repository page choose Add file > Upload files,
   then upload everything INSIDE the blaugust-recent-posts folder. This includes
   the normally hidden .github folder. Commit the upload to the main branch.

3. Open the repository's Settings tab. Choose Pages in the left-hand column.
   Under Build and deployment, set Source to GitHub Actions.

4. Open the Actions tab. Select "Update recent posts" and use Run workflow.
   The first run checks all feeds and normally takes a few minutes. A green tick
   means the files have been published successfully.

5. Your public data address will be:

       https://YOUR-GITHUB-USERNAME.github.io/blaugust-recent-posts/latest-posts-data.js

   Replace YOUR-GITHUB-USERNAME with your actual GitHub username.

SQUARESPACE SETUP
-----------------
1. Open squarespace-recent-posts-widget.txt.
2. Replace YOUR-GITHUB-USERNAME in its data-source address.
3. Paste the entire contents into a new Squarespace Code Block immediately above
   the existing alphabetical blogroll.
4. Make sure Display Source is switched off, then save the page.

The widget shows 20 posts in two columns on larger screens and one column on
phones. Each item contains the post title, blog name and publication date.

If your Squarespace plan prevents JavaScript in Code Blocks, use the contents of
squarespace-iframe-fallback.txt instead. It embeds the GitHub-hosted panel in an
iframe, although the integrated JavaScript version will generally look better.

UPDATING THE BLOG LIST LATER
----------------------------
Export a fresh OPML file from Feedly and replace data/feedly.opml in the GitHub
repository. Commit the replacement. The workflow will run automatically because
that source file changed.

The data/overrides.json file contains the nine corrections applied to the
original export. They are keyed by RSS address, so they continue to be used when
those same subscriptions appear in a later export.

CHANGING THE NUMBER OF POSTS
----------------------------
The default is 20. In .github/workflows/update-recent-posts.yml, add an env value
to the "Check feeds and build files" step, for example:

       env:
         MAX_POSTS: "30"

Twenty is recommended initially so the panel remains compact.

FILES OF INTEREST
-----------------
- squarespace-recent-posts-widget.txt : preferred Squarespace block
- squarespace-iframe-fallback.txt     : fallback without inline JavaScript
- data/feedly.opml                    : current Feedly export
- data/overrides.json                 : corrected names and homepages
- scripts/build_recent_posts.py       : feed checker and data builder
- .github/workflows/...               : twice-daily automatic updater
- docs/index.html                     : standalone iframe version

NOTES
-----
- The GitHub repository must be public to use GitHub Pages on a free account.
- The list contains public blog names, URLs and post titles; no private Feedly
  credentials are stored.
- A feed without a usable publication date is not eligible for the newest-posts
  panel, although it remains in the existing alphabetical blogroll.
- Individual feeds may occasionally reject automated checks. Cached results are
  retained and the other feeds continue to update.

GITHUB SCHEDULE NOTE
--------------------
GitHub may disable scheduled workflows in a public repository after a long
period without repository activity. The updater normally commits refreshed data
regularly, but if updates ever stop, open Actions and run the workflow manually
to re-enable and test it.
