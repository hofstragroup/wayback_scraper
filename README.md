## wayback_scraper

Scrapes snapshot URLs from the archive.org (WayBack Machine) given a list of dates and domains

### main methods

#### self.fetch_snapshot_urls()

This iterates over the list of domains and sends a request to archive.org for each. Each request recieves a response of JSON list of snapshot URLs for the given domain. The URLs are stored in `self.url_records`.

#### self.sort_snapshot_to_dates()

The ultimate goal of this method is to be able to find out which URLs from the given input domains are closest to the given input dates. The output should be snapshot URLs from the different input domains grouped according to the input dates. This desired output is achieved in two steps: 

First step is sorting of the snapshot URLs in each domain based on their time difference with each of the input dates. In this step, the URLs with the closest proximity to the input dates are selected, one such URL per input date per domain. These data are temporarily stored in `sorted_urls` dictionary.

Second step is to iterate over the input dates and extract from `sorted_urls` the snapshot URLs that have been found to be closest to each. This is the point when the snapshot URLs are checked for any redirections.

#### self.check_url_redirection(url)

This is the method invoked by `self.sort_snapshot_to_dates` to check for redirections. It implements the logic of following the snapshot URLs that are redirected plus more. This method also catches new domains, checks against a blacklist, and detects problematic "recursive" URLs.

### other features

#### new domains

New domains found upon following the redirections are stored `self.new_domains` list and written into a file named `new_domains.txt`.

#### recursive scraping of new domains

While new domains are found, the scraping executes recursively taking the new domains found in each round as inputs for the next round until no more new domains are found.

#### skipping of recursive redirects

If redirection URLs that are being followed redirect to itself or keeps redirecting to another URLs for at least 3 times, the URL is tagged as `recursive` and is skipped.

#### skipping of domains from a blacklist

The script accepts a list of domains that are checked against in every run. Any snapshot URL that redirects to a page within those domains are not followed further and are thus skipped.

### sample usage

Make sure to create the outputs directory before executing the script:

    mkdir outputs
    python scraper.py --dates=01-01-2011,01-01-2013,01-01-2015 --domains=domains.txt --outdir=outputs --blacklist=blacklist.txt
