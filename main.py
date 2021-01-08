import argparse
from client import *


def main():
    '''
    Main function call that executes the program

    '''
    # Initialize parser object
    parser = argparse.ArgumentParser(
        description='Download all your NTULearn course materials')

    # Positional arguments
    parser.add_argument('username',
                        help='Your NTULearn username'
                        )

    parser.add_argument('password',
                        help='Your NTULearn password'
                        )

    # Optional arguments
    parser.add_argument('-c',
                        nargs='*',
                        dest='course',
                        action='store',  # returns a list
                        metavar='',
                        help='Download from specified course(s) \
                        i.e -c mh1300 cz1003'
                        )

    parser.add_argument('-w',
                        dest='opt',
                        action='store_true',
                        help='Download webcasts'
                        )

    parser.add_argument('-d',
                        dest='destination',
                        metavar='',
                        help='Set download directory, i.e \
                        -d "C:\\Users\\<Username>\\<Folder>"'
                        )

    args = parser.parse_args(args=None if sys.argv[1:] else ['-h'])

    if args.opt:
        opt = True
    else:
        opt = False

    username = args.username
    password = args.password

    if args.destination:
        download_dir = os.path.abspath(args.destination)
    else:
        download_dir = os.path.abspath(os.path.expanduser('~/Downloads/'))

    print('Downloading files to {}'.format(os.path.abspath(download_dir)))

    crawler = BlackboardSession(username, password, download_dir, opt)

    crawler.login()

    try:
        with open('courseList.obj', 'rb') as courseListfile:
            crawler.courseList = pickle.load(courseListfile)
            # Renew session object when restoring cached requests
            for course in crawler.courseList:
                course.session = crawler.session
    except FileNotFoundError:
        crawler.get_courses()

    if not crawler.courseList:
        print('No registered courses found!')
        sys.exit(0)

    if args.course:
        courseLst = []
        for arg in args.course:
            for course in crawler.courseList:
                if arg in course.name.lower():
                    courseLst.append(course)

        crawler.courseList = courseLst

    for course in crawler.courseList:
        print('Scraping contents for {}'.format(course.name))
        done = course.scrape_contents()
        if done:
            print('Scraping completed for {}'.format(course.name))

        time.sleep(6)


if __name__ == '__main__':
    main()
