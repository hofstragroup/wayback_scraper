#!/usr/bin/env python

from collections import defaultdict
from urllib.parse import urlparse
from operator import itemgetter
from bs4 import BeautifulSoup
from datetime import datetime
import argparse
import requests
import json
import sys
import os
import re



def _extract_domain(url, netloc=False):
    d = re.search(r'/web/\b(.*)', url).group(0)
    d = '/'.join(d.split('/')[3:])
    d = urlparse(d)
    domain = '%s://%s' % (d.scheme, d.netloc)
    if netloc:
        domain = d.netloc
    return domain


class WaybackScraper(object):

    SEARCH_URL = 'http://web.archive.org/cdx/search/cdx'
    BASE_URL = 'https://web.archive.org/web/'
    

    def __init__(self, domains, dates=None, blacklist=None, status=None, verbose=True):
        """ Initializes the object with the user inputs """
        self.domains = domains
        self.new_domains = []
        if blacklist:
            self.blacklist = blacklist
        else:
            self.blacklist = []
        self.status = status
        self.verbose = verbose
        self.url_records = {}
        if dates:
            self.dates = [datetime.strptime(x, '%m-%d-%Y') for x in dates]
            self.sorted_urls = {k:[] for k in self.dates}
            
    
    def _extract_date(self, url):
        """ Extracts the date from a snapshot URL """
        raw_date = re.sub(".*web\/|/http.*", "", url)
        try:
            raw_date = datetime.strptime(raw_date, '%Y%m%d%H%M%S')
            return raw_date  
        except Exception as err:
            print('Invalid date found in this URL: %s' % url)
    
    
    def fetch_snapshot_urls(self):
        """ Searches and builds all the snapshot URLs of a given domain """
        for i, domain in enumerate(self.domains):
            #if self.verbose: print('%s: Fetching snapshot URLs...' % domain)
            params = {'url': domain,
                      'collapse': 'timestamp:6',
                      'output': 'json'}            
            if type(self.status) == int:
                params['filter'] = 'statuscode:%s' % self.status
            response = requests.get(self.SEARCH_URL, params=params)
            if response.ok:
                results = response.json()
                status = response.status_code
                snaps = {}
                count = 0
                for result in results[1:]:
                    snap_url = self.BASE_URL + result[1] + '/' + domain
                    #if not snap_url.endswith('/'):
                    #    snap_url = snap_url + '/'
                    snap_date = self._extract_date(snap_url)
                    if snap_date:
                        count += 1
                        data = {}
                        data['url'] = snap_url
                        data['snapshot_date'] = snap_date
                        data['statuscode'] = result[4]
                        data['recursive'] = False
                        snaps[count] = data
                self.url_records[domain] = snaps
                if self.verbose: print('%s: A total of %s URLs were obtained!' % (domain, len(snaps)))
            else:
                print('\n%s: The error below was encountered for this domain!' % domain)
                print(response.text)
         

    def _check_redirection(self, url, depth=1):
        """ Checks and follows redirections of a snapshot URL """
        resp = requests.get(url, allow_redirects=False)
        soup = BeautifulSoup(resp.content)
        redirect_link = soup.find('p', {'class': 'impatient'})
        recursive = False
        if redirect_link != None:
            if self.verbose:
                print('--> Following the redirection for:')
                print('    %s' % url)
            redirect_url = redirect_link.find('a')['href'].replace('/web/', '')
            redirect_url = self.BASE_URL + redirect_url
            if redirect_url == url or depth >= 3:
                # The url redirects to itself or recursion
                # depth limit of 3 is reached
                recursive = True
            else:
                print('    %s - Redirects to:' % depth)
                print('    %s' % redirect_url)
                return self._check_redirection(redirect_url, depth+1)
        return (recursive, url)
        
        
    def check_url_redirection(self, url_record):
        """ Checks redirection in URL and saves new domains, if any """
        current_url = url_record['url']
        recursive, url = self._check_redirection(current_url)
        url_record['final_url'] = url
        if recursive:
            print('    This is a recursive redirect. Action: Skipped!')
            url_record['redirected'] = True
            url_record['recursive'] = True
        else: 
            url_record['recursive'] = False
            if url == current_url:
                url_record['redirected'] = False
            else:
                url_record['redirected'] = True
                domain1 = _extract_domain(current_url)
                domain2 = _extract_domain(url)
                if urlparse(domain1).netloc == urlparse(domain2).netloc:
                    url_record['same_domain'] = True
                else:
                    url_record['same_domain'] = False
                    if domain2 not in self.new_domains:
                        # Make sure the domain is not in the blacklist
                        if urlparse(domain2).netloc not in self.blacklist:
                            # Make sure that the URL is that of a web archive snapshot
                            if '://web.archive.org/web/' in url:
                                print('    New domain found: %s' % domain2)
                                self.new_domains.append(domain2)
                    
        return url_record
            

    def sort_snapshots_to_dates(self):  
        """ Sorts snapshot URLs to the user-given input dates """  
        if self.url_records:
            print('\n:: Sorting URLs to the given dates...')  
            # First step
            print('Step 1: Sorting per domain')
            sorted_urls = defaultdict(list)
            for domain in self.url_records:
                print(domain)
                for n in self.url_records[domain]:
                    # Determine the time difference in seconds between
                    # each snapshot URL and each input date
                    data = []
                    for date in self.dates:
                        url = self.url_records[domain][n].copy()
                        url['date'] = date
                        diff = url['snapshot_date'] - date
                        url['diff'] = abs(diff.total_seconds())
                        url['domain'] = domain
                        url['statuscode'] = url['statuscode']
                        data.append(url)
                    # Sort the data according to time difference
                    data.sort(key=itemgetter('diff'))
                    # Get the one with the smallest difference and put
                    # into the sorted URLs dictionary
                    sorted_urls[url['url']] = data[0]
            # Second step
            print('Step 2: Sorting per input date and checking for redirections')
            for date in self.dates:
                print(datetime.strftime(date, '%m-%d-%Y'))
                domains = defaultdict(list)
                for url in sorted_urls:
                    url = sorted_urls[url]
                    if url['date'] == date:
                        domains[url['domain']].append(url)
                if domains:
                    for domain in domains:
                        urls = domains[domain]
                        urls.sort(key=itemgetter('diff'))
                        url = urls[0]
                        statsr = ['301', '302']
                        if url['statuscode'] in statsr and url['recursive'] == False:
                            url = self.check_url_redirection(urls[0])
                        else:
                            url['redirected'] = False
                            url['final_url'] = url['url']
                        self.sorted_urls[date].append(url)

            

if __name__ == '__main__':
    
    parser = argparse.ArgumentParser(description='A script that scrapes the Wayback Machine')
    parser.add_argument('--dates', type=str, help='comma-separated dates with MM-DD-YYYY format')
    parser.add_argument('--domains', type=str, help='path to a file that contains a list of domains')
    parser.add_argument('--blacklist', type=str, help='path to a file with a list of blacklisted sites')
    parser.add_argument('--outdir', type=str, default='.', help='path to output folder')
    args = parser.parse_args()

    if args.domains and args.dates:
    
        with open(args.domains.strip(), 'r') as infile:
            domains = infile.read().splitlines()
            domains = [x.strip() for x in domains if x]
        new_domains = []
        scraped_domains = []
        dates = args.dates
        urls = defaultdict(list) 
        
        # Prepare the blacklist
        if args.blacklist:
            with open(args.blacklist, 'r') as blacklist:
                blacklist = [urlparse(x.strip()).netloc for x in blacklist.read().splitlines() if x]
        else:
            blacklist = []
        global_blacklist = None
        
        def recursively_scrape(domains, dates, scraped_domains, blacklist):
            w = WaybackScraper(domains, dates=args.dates.split(','), blacklist=blacklist)
            global global_blacklist
            if global_blacklist == None:
                global_blacklist = w.blacklist
            print('\n:: Fetching snapshot URLs...')
            w.fetch_snapshot_urls()
            w.sort_snapshots_to_dates()
            for date in w.sorted_urls:
                for url in w.sorted_urls[date]:
                    if url['redirected']:
                        if url['recursive'] == False:
                            # Include only the redirects to the same domain
                            if url['same_domain']:
                                urls[date].append(url)
                    else:
                        urls[date].append(url)
            scraped_domains += domains
            if w.new_domains:
                nds = set(w.new_domains) - set(scraped_domains)
                nds = list(nds)
                global new_domains
                for nd in nds:
                    d = urlparse(nd).netloc
                    if d not in global_blacklist:
                        new_domains.append(nd)
                if nds:
                    return recursively_scrape(nds, date, scraped_domains, blacklist)
            return 'Done!'
        
        # Execute the recurive scraping function
        recursively_scrape(domains, dates, scraped_domains, blacklist)
        
        # Write the output files
        for date in urls:
            outfile = os.path.join(args.outdir, 'output_%s.txt' % datetime.strftime(date, '%m-%d-%Y'))
            with open(outfile, 'w') as outf:
                final_urls = []
                for url in urls[date]:
                    final_url = url['final_url']
                    if final_url not in final_urls:
                        d = _extract_domain(final_url, netloc=True)
                        if d not in global_blacklist:
                            final_urls.append(final_url)
                for url in set(final_urls):
                    outf.write(url + '\n')
        
        # Write the new domains into a file
        with open(os.path.join(args.outdir, 'new_domains.txt'), 'w') as outf:
            for domain in new_domains:
                outf.write(domain + '\n')
                    
        print('\n:: Finished! ::\n')
