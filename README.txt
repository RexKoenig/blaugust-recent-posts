BLAUGUST BLOGROLL - MAINTENANCE AND DATA NOTES
=============================================
Last revised: 10 October 2026

PURPOSE
-------
The Blaugust blogroll is a living directory, not a fixed historical list.
Its single authoritative source is:

    data/blogs.csv

The alphabetical directory and the "twenty latest posts" feature are both
built from this CSV. Routine additions, removals and corrections should be
made in this file, rather than in the generated website data or Squarespace
code.

DIRECTORY STATUS AND CURRENCY
-----------------------------
The directory is continually reviewed and updated as blogs are suggested,
addresses change, feeds move, sites close or information is corrected.
Consequently:

- Entries, names, web addresses, feed URLs and classifications may be revised.
- Earlier entries or feed addresses may be superseded by newer, more accurate
  details. A record's presence in an old copy does not make it current.
- An obsolete or duplicate entry may be retained for reference but hidden
  from the public directory and excluded from the latest-posts feature.
- Inclusion does not guarantee that a site is still active, that its RSS/Atom
  feed is working or that it will appear in the latest-posts panel.
- The directory is a best-efforts community resource, not an exhaustive or
  permanent register of Blaugust participants.
- Counts quoted in documentation or older exports are snapshots only. The
  current directory display and master CSV take precedence.

Please consult the latest committed version of data/blogs.csv before
relying on an older copy, quoting a total or reviving a superseded address.

CURRENT CSV SNAPSHOT - 10 OCTOBER 2026
--------------------------------------
The accompanying updated blogs.csv contains:

- 355 records in total
- 354 entries enabled for public display
- 344 visible entries in the alphabetical section
- 10 visible entries in Other Languages
- 1 hidden, disabled legacy duplicate (OrbitalMartian)

These figures will change as the list is maintained. They should not be
used as fixed totals in website copy.

The original master CSV was assembled from a Feedly Blogroll OPML export
supplied on 6 August 2026. Many subsequent changes and additions have
superseded that initial import. Archived OPML files, where retained under
data/archive, are historical references and are not live data sources.

MASTER CSV COLUMNS
------------------
name
    The blog name displayed to visitors.

site_url
    The address opened when a visitor selects the blog.

feed_url
    The RSS or Atom feed used by the latest-posts process.

language
    Administrative language label. Many entries remain "Unspecified"
    where reliable language information was not supplied.

directory_group
    Use alphabetical or other-languages.

status
    Administrative description such as included, inactive or duplicate.
    This field does not, by itself, hide a record.

show_in_directory
    yes = publish the blog in the directory
    no  = retain the record without displaying it

include_in_latest
    yes = make the feed eligible for the latest-posts check
    no  = exclude it from that check
    A value of yes does not guarantee a recent post will be found or shown.

notes
    Optional internal maintenance notes, not published on the website.
    Use them to document redirects, feed restrictions, superseded records
    and other details needed for future updates.

FEEDS AND SITE-OWNER PREFERENCES
--------------------------------
Use the feed selected or approved by the site owner when one has been
specified. Do not automatically substitute a full-text feed for a requested
excerpt-only feed, even if another feed is easier to discover.

For example, the site 情報の灯台 (Joho Todai) specifically requested:

    https://joho-todai.com/pinterest-rss/

This is its requested excerpt-only feed. Preserve that address unless the
site owner asks for a change. The choice is also recorded in the CSV notes.

When a feed moves or redirects, verify its replacement before updating the
CSV. Record unresolved issues in notes rather than assuming that a feed
is valid. Some blogs may remain listed even if their feeds are unavailable.

ADDING, CORRECTING OR RETIRING ENTRIES
-------------------------------------
1. Open data/blogs.csv in the blaugust-recent-posts GitHub repository.
2. Edit the existing entry or add the new row, keeping the column order.
3. Check that the blog name, site URL and feed URL are appropriate and
   that the feed respects any preference expressed by the owner.
4. For a superseded or duplicate record, normally set
   show_in_directory=no and include_in_latest=no. Explain the replacement
   or reason in notes. Remove a record completely only when appropriate.
5. Commit the change to the main branch.
6. Check the "Update Blaugust directory and recent posts" GitHub Actions
   workflow for successful validation and regeneration.
7. Check the published directory and, where relevant, the latest-posts
   display. Feed eligibility is not proof of successful retrieval.

Routine changes should not require a fresh OPML export or edits to the
Squarespace directory HTML. Its data is loaded from the published output.

IMPORTANT CSV RULES
-------------------
- Keep all nine column names and their existing order.
- Every feed_url must be unique across the CSV, including disabled rows.
- site_url and feed_url must start with http:// or https://.
- show_in_directory and include_in_latest accept yes or no.
- directory_group accepts alphabetical or other-languages.
- Preserve valid CSV quotation marks around fields containing commas,
  quotation marks or line breaks.
- Save the file as UTF-8 so international blog names remain intact.
- Record any relevant replacement, redirect or exception in notes.

SYSTEM FILES
------------
Source of truth:

    data/blogs.csv

Build script and automation named in the original setup:

    scripts/build_site_data.py
    .github/workflows/update-recent-posts.yml

Published page and generated output:

    docs/directory.html
    docs/blog-directory.json
    docs/blog-directory-data.js
    docs/latest-posts.json
    docs/latest-posts-data.js
    data/feed-cache.json

The generated JSON and JavaScript files should not be edited as an
alternative to changing the master CSV. The GitHub workflow regenerates them.
The existing Squarespace widgets consume the published data.

CHECKS AND TROUBLESHOOTING
--------------------------
To validate the CSV and directory without checking external feeds, run from
the repository root:

    python scripts/build_site_data.py --directory-only

The normal GitHub workflow runs without that option and checks feeds that
have include_in_latest=yes. A successful build does not necessarily mean
every external feed returned usable content; investigate individual feed
issues separately.

For major changes, retain a copy of the previous working file or rely on
GitHub commit history for rollback. If publication fails, inspect the
GitHub Actions log before changing Squarespace embed code.

DOCUMENTATION NOTE
------------------
This README describes the directory's current maintenance approach as of
10 October 2026. It is also subject to revision. Earlier setup instructions,
old OPML imports, older CSV exports and previous README versions may be
outdated or superseded. The latest repository configuration and committed
master CSV are authoritative for the running directory.
