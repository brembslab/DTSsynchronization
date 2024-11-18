import argparse
import sys
import os
import subprocess
import getpass
import mimetypes
import zipfile
import re
import time
from datetime import datetime, date
from zipfile import ZIP_DEFLATED
import netrc
from dotenv import load_dotenv
from pathlib import Path
import urllib3

# Disable warnings about insecure HTTPS requests (self-signed certificates)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Compatibility for Python 2 and Python 3 for in-memory byte streams
try:
    from StringIO import StringIO as BytesIO
except:
    from io import BytesIO

# Check if required packages are installed
try:
    import yaml
except ImportError:
    print("The 'pyyaml' package is not installed. Please install it by running:\npip install pyyaml")
    sys.exit(1)  # Exit with a non-zero status code to indicate an error

try:
    import requests
except ImportError:
    print("The 'requests' package is not installed. Please install it by running:\npip install requests")
    sys.exit(1)  # Exit with a non-zero status code to indicate an error

# Load environment variables
current_file_path = Path(__file__).resolve()
dotenv_path = Path(f'{current_file_path.parent}/.env')
load_dotenv(dotenv_path=dotenv_path)

# Constants
BASE_URL = 'https://epub-test.uni-regensburg.de'
USE_LIVE_SERVER = os.getenv("USE_LIVE_SERVER", "False").lower() in ("true", "1", "t")
VERIFY = USE_LIVE_SERVER
BASE_URL = 'https://epub.uni-regensburg.de' if USE_LIVE_SERVER else BASE_URL

# Notify if using the live server
if USE_LIVE_SERVER:
    print("Using live server")

# Handle compatibility between Python 2 and Python 3 for user input functions
try:
    input = raw_input
except NameError:
    pass


def get_content_type(file_path):
    """Guess the MIME type of a file based on its extension."""
    _, file_extension = os.path.splitext(file_path)
    # mime_type.guess sometimes returns incorrect types in windows
    if file_extension == ".zip":
        return "application/zip"

    mime_type = mimetypes.guess_type(file_path)[0] or 'text/plain'

    return mime_type


def pretty_print_POST(req):
    """Helper function to print HTTP POST requests in a human-readable format (for debugging)
def pretty_print_POST(req):"""
    print('{}\n{}\n{}\n\n{}'.format(
        '-----------START-----------',
        req.method + ' ' + req.url,
        '\n'.join('{}: {}'.format(k, v) for k, v in req.headers.items()),
        req.body,
    ))


def curl_send_file(file, url, action='POST'):
    """Send a file using the curl command."""
    _, filename = os.path.split(file)

    # Remark: '--next' needed to be removed
    if user:
        args = ['curl', '-X ' + action, '-ik', '-u ' + user + ':' + password, '--data-binary "@' + file + '"',
                '-H "Content-Type: text/html"', '-H "Content-Disposition: attachment; filename=' + filename + '"', url]
    else:
        # user + password can be substituted
        args = ['curl', '-X ' + action, '-ik', '--netrc', '--data-binary "@' + file + '"',
                '-H "Content-Type: text/html"',
                '-H "Content-Disposition: attachment; filename=' + filename + '"', url]

    print(' '.join(args))
    subprocess.call(' '.join(args), shell=True, stdout=subprocess.PIPE)


def send_sword_request(data, content_type, send_file=False, headers=None, url=BASE_URL + '/id/contents', action='POST'):
    """Send a single SWORD request for file upload."""
    if headers is None:
        headers = {}
    s = requests.Session()

    h = {'Content-Type': content_type, 'Accept-Charset': 'UTF-8'}
    headers.update(h)
    headers.update({'Connection': 'close'})

    if send_file:
        f = data
        _, filename = os.path.split(f)

        zip = open(f, 'rb')
        files = {'file': (filename, zip, content_type)}
        fc = {'Content-Disposition': 'attachment; filename=' + filename}
        headers.update(fc)
        if user:
            r = requests.Request(action, url, files=files, headers=headers, auth=(user, password))
        else:
            r = requests.Request(action, url, files=files, headers=headers)
    else:
        if user:
            r = requests.Request(action, url, data=data, headers=headers, auth=(user, password))
        else:
            r = requests.Request(action, url, data=data, headers=headers)

    prepared = r.prepare()

    # if verbose:
    #    pretty_print_POST(prepared)

    # Verify ssl certificate
    resp = s.send(prepared, verify=VERIFY)
    if verbose:
        print(resp.status_code)
        print(resp.raise_for_status())
        print(resp.headers)

    try:
        zip.close()
    except:
        pass

    if resp.status_code == 200 or resp.status_code == 201:
        if 'Location' in resp.headers:
            return resp.headers['Location']
        else:
            return 0
    else:
        return -1


def get_document_ids(epid, yaml_timestamp=False, type='fileid'):
    """
    Gets ids for the pdf and xml zip in eprints
    Parameters
    ----------
    epid : int
        Eprint entry for the current measurements
    yaml_timestamp : date
        changedate of the yamlfile
	type : string
		If type is fileid return the ids of the file regardless of
    Returns
    -------
    docid : mixed
        False on error
        -1 if zips are up to date
        int[] with xml.zip and pdf.zip at [0] and [1] respectively
    """
    s = requests.Session()

    headers = {'Accept': 'application/atom+xml', 'Accept-Charset': 'UTF-8'}

    url = BASE_URL + "/id/eprint/" + str(epid) + "/contents"

    if user:
        r = requests.Request('GET', url, headers=headers, auth=(user, password))
    else:
        r = requests.Request('GET', url, headers=headers)

    if verbose:
        print(headers)
    prepared = r.prepare()

    # Verify ssl certificate
    resp = s.send(prepared, verify=VERIFY)
    if verbose:
        print(resp.status_code)
        print(resp.raise_for_status())
        print(resp.headers)
        print(resp.text)

    if resp.status_code == 200 or resp.status_code == 201:
        regex = "text\/html.*\/document\/\d+"
        response = resp.text

        docid = []
        for match in re.findall(regex, response):
            m = re.search('(?<=\/document\/)\d+', match)

            if type != 'fileid':
                docid.append(m.group(0))
                continue

            # Read fileids; Eprints stores the files with ids, independent from the eprint id
            url = BASE_URL + "/id/document/" + str(m.group(0)) + "/contents"

            if user:
                r = requests.Request('GET', url, headers=headers, auth=(user, password))
            else:
                r = requests.Request('GET', url, headers=headers)

            prepared = r.prepare()
            if verbose:
                print(resp.status_code)
                print(resp.raise_for_status())
                print(resp.headers)
                print(resp.text)
            resp = s.send(prepared, verify=VERIFY)
            if resp.status_code == 200 or resp.status_code == 201:
                ep_timestamp = re.search('(?<=\<updated\>).*(?=T)', resp.text)
                ep_timestamp = datetime.strptime(ep_timestamp.group(0), "%Y-%m-%d").date()
                if verbose:
                    if yaml_timestamp:
                        print("Yamlfile last changed: " + date.strftime(yaml_timestamp, "%Y-%m-%d"))
                    print("Eprints file last modified: " + date.strftime(ep_timestamp, "%Y-%m-%d"))

                # Compare timestamps of file with Eprints
                # If equal or yaml is newer, no update is needed
                if yaml_timestamp and yaml_timestamp <= ep_timestamp:
                    return -1

                m = re.search('(?<=file\/)\d+', resp.text)
                docid.append(m.group(0))

        return docid  # Return the list of document IDs

    else:
        return False  # Return False if request failed


def create_zips(path):
    """Create zip files for XML and PDF content."""
    xmlzip = zipfile.ZipFile(path + 'xml.zip', 'w', ZIP_DEFLATED)
    pdfzip = zipfile.ZipFile(path + 'pdf.zip', 'w', ZIP_DEFLATED)
    yamlfile = None
    for root, dirs, files in os.walk(path):
        for file in files:
            filename, extension = os.path.splitext(file)
            basename = filename + extension

            if extension in '.xml':
                xmlzip.write(os.path.join(root, file), file)
            elif extension in '.pdf':
                pdfzip.write(os.path.join(root, file), file)
            elif extension in '.yml':
                # TODO: throw error when more than one yaml file present
                yamlfile = os.path.join(root, file)
                xmlzip.write(os.path.join(root, file), file)
                pdfzip.write(os.path.join(root, file), file)

    xmlzip.close()
    pdfzip.close()

    return [yamlfile, xmlzip.filename, pdfzip.filename]


def create_ep_xml(xmlcontent):
    """Create XML file for the EPrint metadata."""
    filename = 'ep_metadata.xml'
    stream = open(filename, 'w')

    # Python 3 needs byte streams whereas python 3 needs a str
    # For this to work in python 2 encode it as utf8
    stream.write(xmlcontent)
    stream.close()

    return filename


def load_netrc():
    """Load .netrc or _netrc credentials."""
    try:
        return netrc.netrc()
    except (FileNotFoundError, OSError):
        # Windows workaround because developer of netrc couldn't be bothered to take it into account
        try:
            return netrc.netrc(os.path.join(home, "_netrc"))
        except Exception as err:
            print(f"Netrc error: {err}")
            return None


# remove files after upload
def cleanup():
    try:
        # TODO: Do get files removed if one file couldn't be found?
        os.remove(ep_xml_file)
    except IOError:
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Eprits SWORD client')
    parser.add_argument('--path', '-p', type=str, help='Directory for uploading')
    parser.add_argument('--epid', '-i', type=int,
                        help='Eprints Id to append or false to create new entry')
    parser.add_argument('--user', '-u', type=str, help='Eprints username')
    parser.add_argument('--verbose', '-v', action='store_true', help='Show additional information')

    args = parser.parse_args()

    path = args.path
    epid = args.epid
    user = args.user
    verbose = args.verbose

    # If no path set, read from cmd
    if path is None:
        path = input("File/Directory: ")

    # File or folder exist?
    assert os.path.exists(path), "Path not found: " + str(path)
    assert os.path.isdir(path), "No valid directory path " + str(path)

    from os.path import expanduser

    # Get the user's home directory
    home = expanduser("~")

    # Load netrc for authentication
    net = load_netrc()

    if user is None and net:
        try:
            (user, account, password) = net.authenticators(BASE_URL[8:])
            print(f"User for {BASE_URL[8:]}: {user}")
        except:
            print(f"Error with {BASE_URL[8:]}: {sys.exc_info()[0]}")
            user = False
    else:
        user = False

    if epid == None:
        epid = False

    # User password
    # only prompt for password if a user is provided
    # curl and python.requests should attempt to use netrc instead
    # they will try to use .netrc (linux) or _netrc from the users home directory
    # The file should look like this machine <example.com> login <username> password <password>

    if user and password == None:
        password = getpass.getpass('Password:')

    yamlfile = ""
    # Look for the YAML file in the directory
    for root, dirs, files in os.walk(path):
        for file in files:
            filename, extension = os.path.splitext(file)
            basename = filename + extension
            if file.endswith(".yml"):
                yamlfile = os.path.join(root, file)

    if verbose:
        print(yamlfile)

    changeddate = date.fromtimestamp(os.path.getmtime(yamlfile))

    # Open yaml file
    stream = open(yamlfile, "r")
    doc = yaml.safe_load(stream)

    # Extract metadata from the YAML file
    # Get title and author
    experiment = doc['experiment']
    title = experiment['title']
    experiment_name = experiment['name']
    description = experiment['description']
    # can there be multiple authors?
    # author_list = doc['author']
    # print(author_list)
    # print("title: " + str(title) + " author: " + str(doc['author']))
    # author={}
    # if not this should be fine:
    author = doc['author']

    additional_metadata = doc['meta-data']

    # Read and write finished flag
    if 'finished' in doc.keys():
        print("Messung abgeschlossen!")
        cleanup()
        exit()

    if 'epid' in doc.keys():
        epid = doc['epid']
    stream.close()

    # Prepare the XML content for EPrint metadata
    # Send metadata as xml request
    first_name = author['firstName']
    last_name = author['lastName']
    orcid = author['id']
    nds = user
    publication_date = time.strftime("%Y-%m-%d")
    date_type = "published"

    oa_type = None
    created_here = None
    data_type = None
    subject = None
    institution = None
    note = ''
    no_funding = 'TRUE'
    acknowledged_funders = 'no_funders'

    for metadata_entry in additional_metadata:
        if 'oa.type' in metadata_entry:
            oa_type = metadata_entry['oa.type']['name']
        if 'institution' in metadata_entry:
            created_here = "yes" if metadata_entry['institution']['id'] == '01eezs655' else "no"
        if 'data.type' in metadata_entry:
            data_type = metadata_entry['data.type']['name']
        if 'subject' in metadata_entry:
            subject = metadata_entry['subject']['id']
        if 'department' in metadata_entry:
            institution = metadata_entry['department']['id']
        if 'licenses' in metadata_entry:
            note = metadata_entry['licenses']['name']
        if 'funding' in metadata_entry:
            acknowledged_funders = str(metadata_entry['funding']['acknowledged.funders'])
            if acknowledged_funders == 'no' or acknowledged_funders == 'False':
                acknowledged_funders = 'no'
            elif acknowledged_funders == 'no_funders':
                acknowledged_funders = 'no_funders'
            else:
                acknowledged_funders = 'yes'

            no_funding = 'FALSE' if metadata_entry['funding']['received.funding'] is True else 'TRUE'

    # Check if all required metadata is present
    if oa_type is None or created_here is None or data_type is None or subject is None or institution is None:
        print("Please provide all necessary fields: oa.type, institution, data.type, subject, department")
        exit()

    # Create strings for subjects and institutions in the XML
    subjects_string = '<subjects>'
    subjects_string += '<item>%s</item>' % subject
    subjects_string += '</subjects>'

    institutions_string = '<institutions>'
    institutions_string += '<item>%s</item>' % institution
    institutions_string += '</institutions>'

    nofunding_string = '<nofunding>%s</nofunding>' % no_funding
    acknowledged_funders_string = '<acknowledged_funders>%s</acknowledged_funders>' % acknowledged_funders

    # Build the XML metadata for the EPrint
    ep_xml = """<?xml version='1.0' encoding='utf-8'?>
    <eprints xmlns='http://eprints.org/ep2/data/2.0'>
        <eprint>
            <eprint_status>archive</eprint_status>
            <title>%s</title>
            <abstract>%s</abstract>
            <note>%s</note>
            <creators>
                <item>
                <name>
                    <given>%s</given>
                    <family>%s</family>
                </name>
                <orcid>%s</orcid>
                <id>%s</id>
                </item>
            </creators>
            <type>%s</type>
            <oa_type>%s</oa_type>
            <created_here>%s</created_here>
            %s
            %s
            <date>%s</date>
            <date_type>%s</date_type>
            <ispublished>pub</ispublished>
            %s
            %s
        </eprint>
    </eprints>
    """ % (
    title, description, note, first_name, last_name, orcid, nds, data_type, oa_type, created_here, subjects_string,
    institutions_string,
    publication_date, date_type, nofunding_string, acknowledged_funders_string)

    print(ep_xml)

    ep_xml_file = create_ep_xml(ep_xml)

    headers = {}

    headers.update({'Content-Type': 'application/vnd.eprints.data+xml'})

    if not epid:
        # If no EPrint ID, create a new EPrint entry
        data = open(ep_xml_file, 'rb').read()
        epid = send_sword_request(data, content_type='application/vnd.eprints.data+xml', send_file=False,
                                  headers=headers)

        if verbose:
            print("EPID: " + str(epid))

        m = re.search('[0-9]+$', str(epid))
        epid = m.group(0)

        print("Eprint with id " + epid + " was created")
    else:
        # Eprint entry already exists
        print("Eprint with id " + str(epid) + " was updated")

    # Update yamlfile stream
    stream = open(yamlfile, "r")
    doc = yaml.safe_load(stream)
    stream.close()

    # If new eprint was generated, update the yamlfile with its id
    if not ('epid' in doc.keys()):
        yaml_file = open(yamlfile, 'a')  # append to file
        yaml_file.write("\n" + "epid: " + epid)
        yaml_file.close()
        # Read as yamlfile and write as plain text because pyyaml messes up the structure

    url = ''

    # Fetch document IDs to verify whether updates are needed
    docids = get_document_ids(epid, changeddate)

    if docids:
        if docids == -1:
            print("Files already up to date")
            cleanup()
            exit()
        else:
            # Check if files present and delete/update them
            for document in docids:
                print(document)

    thisurl = BASE_URL + "/id/eprint/" + str(epid) + "/contents"

    # Upload all htmlfiles
    htmlpath = path  # + "/evaluations/" oder '/opt/DTSevaluations/example data/colorlearning/evaluations/'
    print(htmlpath)

    # indexfile currently has the same name as the measurement
    # Upload the index file (usually the main file) first and add the others to its epid
    indexfile = os.path.join(htmlpath, experiment_name + ".html")

    if os.path.isfile(indexfile):
        print("Uploading: " + indexfile)
        if docids and len(docids) >= 1:
            print("Add files to an existing entry")
            curl_send_file(indexfile, BASE_URL + "/id/file/" + str(docids[0]), action='PUT')
        else:
            curl_target = BASE_URL + "/id/eprint/" + str(epid) + "/contents"
            print(f"Adding files to a new entry {epid}")
            print(f"File tu upload: {indexfile}")
            print(f"Target url: {curl_target}")
            curl_send_file(indexfile, curl_target, action='POST')

        # Fetch the main document ID after the first upload
        response = get_document_ids(epid, False, 'document')

        print("Response of first upload")
        print(response)

        docid = False
        if response and len(response) > 0:
            docid = response[0]
        else:
            print("No docid could be requested")

        if docid:
            for root, dirs, files in os.walk(path):
                for htmlfile in files:
                    headers = {}
                    filename, extension = os.path.splitext(htmlfile)

                    if extension in [".html", ".xml", ".yml"]:
                        if verbose:
                            print("Uploading: " + filename + extension)

                        htmlfile = os.path.join(root, htmlfile)
                        up_file = htmlfile

                        if up_file != indexfile:
                            curl_send_file(up_file, url=BASE_URL + "/id/document/" + docid + "/contents", action='POST')
        # TODO: Upload YAML file

    else:
        print("HTML file doesn't exist")

    # Delete files after upload
    cleanup()
