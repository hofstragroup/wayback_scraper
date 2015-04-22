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


class WaybackScraper(object):

    SEARCH_URL = 'http://web.archive.org/cdx/search/cdx'
    BASE_URL = 'https://web.archive.org/web/'
    

    def __init__(self, domains, dates=None, status=None, verbose=True):
        """ Initializes the object with the user inputs """
        self.domains = domains
        self.new_domains = []
        self.status = status
        self.verbose = verbose
        if dates:
            self.dates = [datetime.strptime(x, '%m-%d-%Y') for x in dates]
            self.sorted_urls = {k:[] for k in self.dates}
            
    
    def _extract_date(self, url):
        """ Extracts the date from a snapshot URL """
        raw_date = re.sub(".*web\/|/http.*", "", url)
        raw_date = datetime.strptime(raw_date, '%Y%m%d%H%M%S')
        return raw_date    


    def _extract_domain(self, url):
         d = re.search(r'/web/\b(.*)', url).group(0)
         d = '/'.join(d.split('/')[3:])
         d = urlparse(d)
         domain = '%s://%s' % (d.scheme, d.netloc)
         return domain
         

    def _check_redirection(self, url):
        """ Checks and follows redirections of a snapshot URL """
        resp = requests.get(url)
        soup = BeautifulSoup(resp.content)
        redirect_link = soup.find('p', {'class': 'impatient'})
        if redirect_link != None:
            url = redirect_link.find('a')['href'].strip('/web/')
            url = self.BASE_URL + url
            if self.verbose:
                print('   --> Following a redirection link')
            return self._check_redirection(url)
        return url  
    
    
    def _fetch_snapshot_urls(self, domain):
        """ Searches and builds all the snapshot URLs of a given domain """
        if self.verbose: print('   %s: Fetching snapshot URLs...' % domain)
        params = {'url': domain,
                  'collapse': 'timestamp:6',
                  'output': 'json'}            
        if type(self.status) == int:
            params['filter'] = 'statuscode:%s' % self.status
        response = requests.get(self.SEARCH_URL, params=params)
        results = response.json()
        status = response.status_code
        snaps = []
        for result in results[1:]:
            snap_url = self.BASE_URL + result[1] + '/' + domain
            if not snap_url.endswith('/'):
                snap_url = snap_url + '/'
            snaps.append(snap_url)
        if self.verbose: print('   %s: A total of %s URLs were obtained!' % (domain, len(snaps)))
        return snaps
         
        
    def _fetch_and_annotate_urls(self, domain):
        """ Fetches and annotates snapshot URLs """
        urls = self._fetch_snapshot_urls(domain) 
        annotated_urls = []
        for i, url in enumerate(urls):
            current_url = url
            url = self._check_redirection(url)
            data = {'final_url': url}
            if url == current_url:
                data['redirected'] = False
            else:
                data['redirected'] = True
                domain1 = self._extract_domain(current_url)
                domain2 = self._extract_domain(url)
                if domain1 == domain2:
                    data['same_domain'] = True
                else:
                    data['same_domain'] = False
                    if domain2 not in self.new_domains:
                        self.new_domains.append(domain2)
            date = self._extract_date(url)
            data['snapshot_date'] = date
            annotated_urls.append(data)
            if self.verbose: print('   %s: Annotated %s out of %s URLs' % (domain, i+1, len(urls)))
        return annotated_urls 

        
    def get_domain_snapshots(self):
        """ Executes the fetching and annotation of snapshot URLs """
        if self.verbose: print('\nFetching snapshot URLs from Wayback Machine...')
        self.urls = {}
        for domain in self.domains:
            if self.verbose:
                print(':: Dealing with domain: %s' % domain)
            self.urls[domain] = self._fetch_and_annotate_urls(domain)      
        
        
    def sort_snapshots_to_dates(self):  
        """ Sorts snapshot URLs to the user-given input dates """  
        if self.verbose: print('\nSorting the snapshot URLs to the given dates...')    
        sorted_urls = []
        for domain in self.urls:
            for url in self.urls[domain]:
                data = []
                for date in self.dates:
                    diff = url['snapshot_date'] - date
                    data.append({'date': date, 'diff': abs(diff.total_seconds())})
                data.sort(key=itemgetter('diff'))
                closest_date = data[0]['date']
                self.sorted_urls[closest_date].append(url['final_url'])
            

if __name__ == '__main__':
    
    parser = argparse.ArgumentParser(description='A script that scrapes the Wayback Machine')
    parser.add_argument('--dates', type=str, help='comma-separated dates with MM-DD-YYYY format')
    parser.add_argument('--domains', type=str, help='path to a file that contains a list of domains')
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
        
        def recursively_scrape(domains, dates, scraped_domains):
            w = WaybackScraper(domains, dates=args.dates.split(','))
            w.get_domain_snapshots()
            w.sort_snapshots_to_dates()
            for date in w.sorted_urls:
                urls[date] = urls[date] + w.sorted_urls[date]
            scraped_domains += domains
            if w.new_domains:
                nd = set(scraped_domains) - set(w.new_domains)
                nd = list(nd)
                if nd:
                    print('\nScraping for new domains found: %s' % str(nd))
                    return recursively_scrape(w.new_domains, date, scraped_domains)
            return 'Done!'
        
        recursively_scrape(domains, dates, scraped_domains)
        
        for date in urls:
            outfile = os.path.join(args.outdir, 'output_%s.txt' % datetime.strftime(date, '%m-%d-%Y'))
            with open(outfile, 'w') as outf:
                for url in set(urls[date]):
                    outf.write(url + '\n')
                    
        print('\n:: Finished! ::\n')
