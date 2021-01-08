import requests
import os
import sys
import string
import re
import pickle
import logging
import time
import random
from bs4 import BeautifulSoup as bs
from urllib.parse import unquote
from requests.exceptions import ChunkedEncodingError, ConnectionError
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry


NTUBB_URL = 'https://ntulearn.ntu.edu.sg'
NTUBB_LOGINURL = 'https://ntulearn.ntu.edu.sg/webapps/login/'


logging.basicConfig(
    filename='Logger.log',
    filemode='w',
    format='%(asctime)s %(message)s',
    datefmt='%I:%M:%S %p',
    level=logging.DEBUG
)

logger = logging.getLogger(__name__)

BB_adapter = HTTPAdapter(
    max_retries=Retry(
        total=5,
        read=3,
        connect=3,
        backoff_factor=1
    )
)


def formatName(name):
    '''
    Function that formats folder names to
    contain only allowed characters in Windows

    '''
    allowed_chars = string.ascii_letters + string.digits + " ()[]-_&,'"
    temp = []

    for char in name:
        if char in allowed_chars:
            temp.append(char)

    return ''.join(temp)


def dlProgress(bufferSize, fileSize):
    '''
    Displays a simple progress indicator for 
    active downloads

    '''
    percent = int(bufferSize * 100 / fileSize)
    sys.stdout.write("%2d%%" % percent)
    sys.stdout.write("\b\b\b")


class BlackboardSession:

    def __init__(self, username, password, dldir, opt):
        '''
        Manages a blackboard session, sets download directory
        and retrieves courses enrolled

        '''
        self.session = requests.session()
        self.username = username
        self.password = password
        self.courseList = []
        self.downloadDir = dldir
        self.opt = opt

        # Automate GET retries
        self.session.mount(NTUBB_URL, BB_adapter)

    def request(self, method, *args, **kwargs):
        '''
        Retries a HTTP request multiple times while handling errors

        '''
        for retry in range(4):
            exception = None
            if retry > 0:
                sleep = (2**retry) - 1
                logger.info(
                    'Retrying due to connection reset, sleeping for {}s'.format(sleep)
                    )
                time.sleep(sleep)

            try:
                resp = method(*args, **kwargs)
            except ChunkedEncodingError:
                exception = ChunkedEncodingError
            except ConnectionError:
                exception = ConnectionError

            if exception:
                if retry == 3:
                    logger.exception('Unrecoverable error from request')
                    raise exception
                else:
                    continue
            else:
                break

        return resp

    def login(self):
        '''
        Performs the login

        '''
        payload = {
            'user_id': self.username,
            'password': self.password,
            'login': 'Login',
            'action': 'login',
            'new_loc': ''
        }

        # Authenticate the session
        with self.session.post(NTUBB_LOGINURL, data=payload) as r:
            # Check if login is successful
            if 'You are being redirected to another page' in r.text:
                print('Login successful!')

            else:
                print('Login failed!')
                sys.exit(0)

    def get_courses(self):
        '''
        Gets list of available courses for logged in user

        '''
        url = 'https://ntulearn.ntu.edu.sg/webapps/portal/execute/tabs/tabAction'

        data = {
            'action': 'refreshAjaxModule',
            'modId': '_22_1',
            'tabId': '_96724_1',
            'tab_tab_group_id': '_65_1'
        }

        with self.request(self.session.post, url, data=data) as r:
            # Parse returned XML response with BeautifulSoup
            soup = bs(r.text, "lxml")

        for link in soup.find_all('a'):
            title = formatName(link.text)

            # Strip whitespace at start of url
            href = (link.get('href')).strip()

            # Append course object to list of enrolled courses
            logger.info('Course found: {0}, link: {1}'.format(title, href))

            self.courseList.append(
                BlackboardCourse(
                    NTUBB_URL + href,
                    title,
                    self.opt,
                    self.downloadDir,
                    self.session)
            )

            time.sleep(6)

        # Save course list object as file
        with open('courseList.obj', 'wb') as courseListfile:
            pickle.dump(self.courseList, courseListfile)


class BlackboardCourse:

    def __init__(self, link, name, opt, cwd, session):
        '''
        Course object that manages scraping process

        '''
        self.link = link
        self.name = name
        self.session = session
        self.sidebarFolders = []
        self.webcasts = opt   # Download webcasts or not
        self.cwd = os.path.abspath(os.path.join(cwd, self.name))
        self._getsbfolders()

    def request(self, method, *args, **kwargs):
        '''
        Retries a HTTP request multiple times while handling errors

        '''
        for retry in range(4):
            exception = None
            if retry > 0:
                sleep = (2**retry) - 1
                logger.info(
                    'Retrying due to connection reset, sleeping for {}s'.format(sleep)
                    )
                time.sleep(sleep)

            try:
                resp = method(*args, **kwargs)
            except ChunkedEncodingError:
                exception = ChunkedEncodingError
            except ConnectionError:
                exception = ConnectionError

            if exception:
                if retry == 3:
                    logger.exception('Unrecoverable error from request')
                    raise exception
                else:
                    continue
            else:
                break

        return resp

    def scrape_contents(self):

        if not self.sidebarFolders:
            return True

        for folder in self.sidebarFolders:
            logger.info('Scraping all attachments for {}'.format(folder[1]))

            # Handle downloading of recorded lectures here
            if 'recorded lectures' in folder[1].lower():
                self._scrapewebcast(
                    folder[0], os.path.join(self.cwd, folder[1])
                )

            else:
                self._scrapefolder(
                    folder[0], os.path.join(self.cwd, folder[1])
                )

            time.sleep(6)

        return True

    def _getsbfolders(self):
        '''
        Scrapes the course sidebar links (except those from skip_folders)

        '''
        skip_folders = ['Announcements', 'Discussion Board',
                        'Groups', 'Video Portal', 'Tools']

        with self.request(self.session.get, self.link) as r:
            soup = bs(r.text, "lxml")

        sidebar = soup.find(id='courseMenuPalette_contents')
        links = sidebar.find_all('a')

        for link in links:
            title = link.find('span')
            href = link.get('href')

            if title.text in skip_folders:
                continue
            # Option to skip webcasts
            if not self.webcasts and 'recorded lectures' in title.text.lower():
                continue

            logger.info(
                'Adding sidebar folder: {0}, link: {1}'.format(
                    title.text, href)
            )

            self.sidebarFolders.append(
                (NTUBB_URL + href, formatName(title.text))
            )

    def _scrapefolder(self, url, path):
        '''
        Scrapes for attached docs in sidebar/nested folder

        '''
        with self.request(self.session.get, url) as r:
            soup = bs(r.text, "lxml")

        try:
            sections = soup.find(id='content_listContainer').find_all(
                'li', {'class': 'clearfix read'})

        except AttributeError:
            # Empty folder
            logger.info('No attached docs under path: {}'.format(path))
            return

        for section in sections:
            section_header = section.find(
                'div', attrs={'class': 'item clearfix'})

            section_title = formatName(section_header.text.strip())

            logger.info('Found section {0} in path: {1}'.format(
                section_title, path)
            )

            attachment_list = section.find(class_='attachments clearfix')

            # Check for a nested folder
            if attachment_list is None:
                link = section_header.find('a')

                if link is None:  # Not a nested folder
                    # Allow download of attachments in tables
                    attachment_list = section.find(
                        'div', attrs={'class': 'details'})

                elif '/webapps/blackboard/content/listContent.jsp?' in link.get('href'):
                    logger.info(
                        'Nested folder {} discovered. Scraping folder...'.format(
                            link.text)
                    )
                    self._scrapefolder(NTUBB_URL + link.get('href'),
                                       os.path.join(
                                           path, formatName(link.text))
                                       )
                    continue

                else:
                    # Ignore section if no attachments can be found
                    continue

            params = attachment_list.find_all(
                'span', attrs={'class': 'contextMenuContainer'})
            filenames = []

            for param in params:  # Fetch underlying filenames and extension
                paramObj = str(param)
                param_exp = re.compile(r'bb:menugeneratorurl="(.*)\?')
                paramStr = param_exp.search(paramObj).group(1)
                filenames.append(paramStr.rsplit('/', 1)[-1])

            # Only consider <a> tags without a class
            attachments = attachment_list.find_all('a', attrs={'class': None})

            # Skip section without attachments
            if not filenames:
                continue

            # Create attachments' parent directories
            parent_dir = os.path.join(path, section_title)

            if not os.path.exists(parent_dir):
                os.makedirs(parent_dir)

            for idx, attachment in enumerate(attachments):
                if NTUBB_URL in attachment['href']:
                    url = attachment['href']
                else:
                    url = NTUBB_URL + attachment['href']

                # Removes unicode encoding of filename in url
                name = unquote(filenames[idx])

                logger.info('{0} discovered under section {1}'.format(
                    name, section_title))

                save_location = os.path.join(parent_dir, name)
                self._download(url, save_location)

    def _download(self, fileUrl, path):
        '''
        Downloads a single document

        '''
        if os.path.isfile(path):
            logger.info(
                'Skipping file: {}'.format(os.path.basename(path))
            )
            return

        resp = self.request(self.session.get, fileUrl, stream=True)

        if not resp.ok:
            logger.error(
                'Request failed with status code {}'.format(resp.status_code)
            )

            logger.error('URL: {}'.format(fileUrl))

            print(
                'Downloading of {} failed. Skipping...'.os.path.basename(path)
            )
            return

        try:
            fileSize = int(resp.headers['Content-Length'])  # file size in bytes
        except KeyError:
            fileSize = None

        logger.info('Downloading file as {}'.format(path))

        with open(path + '.temp', 'wb+') as f:
            progress = 0
            for chunk in resp.iter_content(chunk_size=1048576):  # 1 mb chunk
                if chunk:  # filter out keep-alive new chunks
                    f.write(chunk)
                    progress += len(chunk)
                    sys.stdout.write('\rDownloading ' +
                                     os.path.basename(path) + '...')
                    if fileSize:
                        dlProgress(progress, fileSize)
                    sys.stdout.flush()
            sys.stdout.write('\n')

        os.rename(path + '.temp', path)
        logger.info('Saved file as {}'.format(path))
        time.sleep(random.randrange(2, 6))

    def _scrapewebcast(self, link, path):
        with self.request(self.session.get, link) as r:
            soup = bs(r.text, "lxml")

        try:
            sections = soup.find(id='content_listContainer').find_all(
                'li', {'class': 'clearfix read'})

        except AttributeError:
            # Empty folder
            logger.info('No webcasts found under path: {}'.format(path))
            return

        if not os.path.exists(path):
            os.makedirs(path)

        for section in sections:
            section_header = section.find(
                'div', attrs={'class': 'item clearfix'})

            name = formatName(section_header.text)
            link = NTUBB_URL + section_header.find('a').get('href')

            with self.session.get(link) as resp:
                respObj = bs(resp.text, "lxml")
                scripts = respObj.find_all('script')

            UserId_exp = re.compile(r'var\sgsUserId\s*=\s"(.*)"')
            ModuleId_exp = re.compile(r'var\sgsModuleId\s*=\s"(.*)"')
            userid = UserId_exp.search(scripts[3].text).group(1)
            moduleid = ModuleId_exp.search(scripts[3].text).group(1)
            media_link = 'https://ntume23.ntu.edu.sg/content/' + \
                userid + '/' + moduleid + '/' + 'media/1.mp4'

            save_location = os.path.join(path, name + '.mp4')
            self._download(media_link, save_location)
