import argparse
import sys
import os
import subprocess
import getpass
import mimetypes
import zipfile
import re
import time
from datetime import datetime, date, timezone, timedelta
from zipfile import ZIP_DEFLATED
import netrc
from dotenv import load_dotenv
from pathlib import Path
import urllib3
import xml.etree.ElementTree as ET
import logging

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
    logging.warning("The 'pyyaml' package is not installed. Please install it by running:\npip install pyyaml")
    sys.exit(1)  # Exit with a non-zero status code to indicate an error

try:
    import requests
except ImportError:
    logging.warning("The 'requests' package is not installed. Please install it by running:\npip install requests")
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
    logging.debug("Using live server")

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
    logging.debug('{}\n{}\n{}\n\n{}'.format(
        '-----------START-----------',
        req.method + ' ' + req.url,
        '\n'.join('{}: {}'.format(k, v) for k, v in req.headers.items()),
        req.body,
    ))


def curl_send_file(file, url, action='POST'):
    """Send a file using the curl command with shell=True and capture output."""
    _, filename = os.path.split(file)

    if user:
        cmd = (
            'curl -X {action} -ik -u "{user}:{password}" --data-binary "@{file}" '
            '-H "Content-Type: text/html" -H "Content-Disposition: attachment; filename={filename}" {url}'
        ).format(action=action, user=user, password=password, file=file, filename=filename, url=url)
    else:
        cmd = (
            'curl -X {action} -ik --netrc --data-binary "@{file}" '
            '-H "Content-Type: text/html" -H "Content-Disposition: attachment; filename={filename}" {url}'
        ).format(action=action, file=file, filename=filename, url=url)

    logging.debug(f"Running command: {cmd}")

    # Using shell=True, pass the command as a string.
    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    logging.debug("Return code:%s", result.returncode)
    logging.debug("Standard Output:\n%s", result.stdout)
    logging.debug("Standard Error:\n%s", result.stderr)

    return result


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
        logging.debug(resp.status_code)
        logging.debug(resp.raise_for_status())
        # logging.debug(resp.headers)

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


def get_document_ids(epid, experiment_name, yaml_timestamp=None, type='fileid'):
    """
    Gets ids for the files in eprints
    Parameters
    ----------
    epid : int
        Eprint entry for the current measurements
    yaml_timestamp : date or None
        changedate of the yamlfile
	type : string
		If type is fileid return the ids of the files
    Returns
    -------
    docid : mixed
        False on error
        -1 if zips are up to date
        int[] with xml.zip and pdf.zip at [0] and [1] respectively
    """

    ns_atom = {'atom': 'http://www.w3.org/2005/Atom'}
    ns_eprint = {'ep2': 'http://eprints.org/ep2/data/2.0'}

    s = requests.Session()

    headers_atom_xml = {'Accept': 'application/atom+xml', 'Accept-Charset': 'UTF-8'}
    url_atom_xml = BASE_URL + "/id/eprint/" + str(epid) + "/contents"
    headers_eprint_xml = {'Accept': 'application/xml', 'Accept-Charset': 'UTF-8'}
    url_eprint_xml = f"{BASE_URL}/cgi/export/eprint/{epid}/XMLCit/epub-eprint-{epid}.xml"

    if user:
        r_atom_xml = requests.Request('GET', url_atom_xml, headers=headers_atom_xml, auth=(user, password))
    else:
        r_atom_xml = requests.Request('GET', url_atom_xml, headers=headers_atom_xml)

    prepared_atom_xml = r_atom_xml.prepare()

    response_atom_xml = s.send(prepared_atom_xml, verify=VERIFY)

    logging.debug(response_atom_xml)
    logging.debug(response_atom_xml.status_code)
    logging.debug(response_atom_xml.raise_for_status())
    logging.debug(response_atom_xml.headers)
    logging.debug(response_atom_xml.text)

    if user:
        r_eprint_xml = requests.Request('GET', url_eprint_xml, headers=headers_eprint_xml, auth=(user, password))
    else:
        r_eprint_xml = requests.Request('GET', url_eprint_xml, headers=headers_eprint_xml)

    prepared_eprint_xml = r_eprint_xml.prepare()

    response_eprint_xml = s.send(prepared_eprint_xml, verify=VERIFY)

    logging.debug(response_eprint_xml)
    logging.debug(response_eprint_xml.status_code)
    logging.debug(response_eprint_xml.raise_for_status())
    logging.debug(response_eprint_xml.headers)
    logging.debug(response_eprint_xml.text)

    # The main HTML file is returned that looks like this:
    """
    <?xml version="1.0" encoding="utf-8" ?>
    <feed
        xmlns="http://www.w3.org/2005/Atom"
        xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
        xmlns:xhtml="http://www.w3.org/1999/xhtml"
        xmlns:sword="http://purl.org/net/sword/"
    >
    <title>Publikationsserver der Universität Regensburg: </title>
    <link rel="alternate" href="https://epub-test.uni-regensburg.de/"/>
    <updated>2025-03-14T09:37:16Z</updated>
    <generator uri="http://www.eprints.org/" version="3.3.15">EPrints</generator>
    <logo>https://epub-test.uni-regensburg.de/images/sitelogo.gif</logo>
    <id>https://epub-test.uni-regensburg.de/</id>
    <entry>
      <id>https://epub-test.uni-regensburg.de/id/document/4853</id>
      <title>  HTML </title>
      <link rel="contents" href="https://epub-test.uni-regensburg.de/id/document/4853/contents"/>
      <link rel="edit-media" href="https://epub-test.uni-regensburg.de/id/document/4853/contents"/>
      <summary>  HTML   </summary>
      <content type="text/html" src="https://epub-test.uni-regensburg.de/id/document/4853/contents"/>
    </entry>
    </feed>
    """

    if (response_eprint_xml.status_code == 200 or response_eprint_xml.status_code == 201) and (
            response_atom_xml.status_code == 200 or response_atom_xml.status_code == 201):
        # Parse the eprint XML
        root_eprint_xml = ET.fromstring(response_eprint_xml.text)

        # Find the <lastmod> element using the namespace
        adjusted_adjusted_ep_timestamp_utc = None
        lastmod_elem = root_eprint_xml.find('ep2:lastmod', ns_eprint)
        if lastmod_elem is not None and lastmod_elem.text:
            lastmod_str = lastmod_elem.text.strip()  # "2025-03-19 09:34:42"

            # Convert the timestamp string into a datetime object.
            ep_timestamp = datetime.strptime(lastmod_str, "%Y-%m-%d %H:%M:%S")
            adjusted_ep_timestamp = ep_timestamp
            # TODO: adjusted_ep_timestamp = ep_timestamp + timedelta(hours=1)
            adjusted_adjusted_ep_timestamp_utc = adjusted_ep_timestamp.replace(tzinfo=timezone.utc)

        # Compare timestamps of file with Eprints
        # If equal or yaml is older (lesser than), then no update is needed
        if yaml_timestamp and adjusted_adjusted_ep_timestamp_utc:
            logging.debug("Yamlfile last changed: " + yaml_timestamp.isoformat())
            logging.debug("Eprints file last modified: " + adjusted_adjusted_ep_timestamp_utc.isoformat())
            if adjusted_adjusted_ep_timestamp_utc >= yaml_timestamp:
                return -1
        else:
            logging.debug(f"No timestamp was passed as it was probably newly created.")

        regex = "text\/html.*\/document\/\d+"
        response_text = response_atom_xml.text

        doc_ids = []
        # Iterate every "contents" of each uploaded file "package"
        # <content type="text/html" src="https://epub-test.uni-regensburg.de/id/document/4867/contents"/>
        for match in re.findall(regex, response_text):
            m = re.search('(?<=\/document\/)\d+', match)

            # Get the id of the document
            if type == 'fileid':
                # Read file ids; Eprints stores the files with ids, independent of the eprint id
                url_contents = BASE_URL + "/id/document/" + str(m.group(0)) + "/contents"

                if user:
                    r_contents = requests.Request('GET', url_contents, headers=headers_atom_xml, auth=(user, password))
                else:
                    r_contents = requests.Request('GET', url_contents, headers=headers_atom_xml)

                prepared_contents = r_contents.prepare()

                # This is the list of all appended files
                """
                <feed
                        xmlns="http://www.w3.org/2005/Atom"
                        xmlns:opensearch="http://a9.com/-/spec/opensearch/1.1/"
                        xmlns:xhtml="http://www.w3.org/1999/xhtml"
                        xmlns:sword="http://purl.org/net/sword/">
                <title>Publikationsserver der Universität Regensburg: </title>
                <link rel="alternate" href="https://epub-test.uni-regensburg.de/"/>
                <updated>2025-03-18T07:19:36Z</updated>
                <generator uri="http://www.eprints.org/" version="3.3.15">EPrints</generator>
                <logo>https://epub-test.uni-regensburg.de/images/sitelogo.gif</logo>
                <id>https://epub-test.uni-regensburg.de/</id>
                <entry>
                  <id>https://epub-test.uni-regensburg.de/id/file/30264</id>
                  <title>apkc_CRISPR_torquelearning_MNs.html</title>
                  <link rel="alternate" href="http://epub-test.uni-regensburg.de/553/1/apkc_CRISPR_torquelearning_MNs.html"/>
                </entry>
                ...
                """

                single_response = s.send(prepared_contents, verify=VERIFY)
                if single_response.status_code == 200 or single_response.status_code == 201:
                    if verbose:
                        logging.debug("/documents overview")
                        logging.debug("-------------")
                        logging.debug(single_response.status_code)
                        # logging.debug(single_response.raise_for_status())
                        # logging.debug(single_response.headers)
                        # logging.debug(single_response.text)

                    # Parse the XML content
                    root_xml = ET.fromstring(single_response.text)
                    # Iterate over all <entry> elements in the feed
                    for entry in root_xml.findall('atom:entry', ns_atom):
                        title_elem = entry.find('atom:title', ns_atom)
                        if title_elem is not None and title_elem.text is not None:
                            # Get the title and remove its file extension, if any
                            entry_title = title_elem.text.strip()
                            entry_title_base = os.path.splitext(entry_title)[0]
                            # Compare the title text (after stripping whitespace) to the experiment name
                            if entry_title_base == experiment_name.strip():
                                id_elem = entry.find('atom:id', ns_atom)
                                if id_elem is not None and id_elem.text is not None:
                                    # Extract the file id from the URL (the last segment after '/')
                                    file_id = id_elem.text.strip().split('/')[-1]

                                    logging.debug(f"Found file id of main HTML file {experiment_name}: {file_id}")
                                    doc_ids.append(file_id)

                    logging.debug("-------------")
            else:
                doc_ids.append(m.group(0))
                continue

        logging.debug("--------------------------------------------------------------------")
        logging.debug(doc_ids)
        return doc_ids

    else:
        logging.debug("--------------------------------------------------------------------")
        return False  # Return False if request failed


def delete_existing_file(file_id):
    """Delete an existing file from EPrints before re-uploading."""
    url = BASE_URL + "/id/file/" + str(file_id)
    headers = {'Authorization': f'Basic {user}:{password}'}

    response = requests.delete(url, headers=headers, verify=VERIFY)
    if response.status_code == 200 or response.status_code == 204:
        logging.debug(f"Deleted existing file ID {file_id} successfully.")
    else:
        logging.debug(f"Failed to delete file ID {file_id}: {response.status_code} - {response.text}")


def get_existing_file_id(epid, filename):
    """
    Check if a file with the same name already exists on the EPrints server.

    Parameters:
    - epid (int): The EPrints entry ID.
    - filename (str): The name of the file to check.

    Returns:
    - str: The file ID if found, else None.
    """
    s = requests.Session()
    headers = {'Accept': 'application/atom+xml', 'Accept-Charset': 'UTF-8'}
    url = f"{BASE_URL}/id/eprint/{epid}/contents"

    if user:
        r = requests.Request('GET', url, headers=headers, auth=(user, password))
    else:
        r = requests.Request('GET', url, headers=headers)

    prepared = r.prepare()
    resp = s.send(prepared, verify=VERIFY)

    logging.debug(f"GET {url}")
    # logging.debug(resp.text)

    if resp.status_code == 200 or resp.status_code == 201:
        # Extract all file entries from the response
        regex = "text\/html.*\/document\/\d+"
        match = re.search(regex, resp.text)

        document_id = None

        if match:
            # Extract matched text from `MatchObject`
            matched_text = match.group()

            # Now apply the second regex to extract only the document ID
            matched_doc_id = re.search(r"(?<=\/document\/)\d+", matched_text)

            if matched_doc_id:
                document_id = matched_doc_id.group()
                logging.debug(f"Document ID: {document_id}")
            else:
                logging.debug("Document ID not found.")
        else:
            logging.debug("No match found")
            # logging.debug(resp.text)

        if document_id is None:
            return None

        # Read file ids; Eprints stores the files with ids, independent of the eprint id
        url = BASE_URL + "/id/document/" + str(document_id) + "/contents"

        if user:
            r = requests.Request('GET', url, headers=headers, auth=(user, password))
        else:
            r = requests.Request('GET', url, headers=headers)

        prepared = r.prepare()

        single_response = s.send(prepared, verify=VERIFY)

        # logging.debug(single_response.text)

        title_regex = r"<title>(.*?)</title>"
        filenames = re.findall(title_regex, single_response.text)

        logging.debug("File names on server:")
        logging.debug(filenames)

        # Step 2: Check if the given filename exists
        if filename.strip() not in [name.strip() for name in filenames]:
            logging.debug(f"File '{filename}' does not exist on the server.")
            return None  # File not found

        # Step 3: If filename exists, find its corresponding file ID
        entry_regex = r"<entry>\s*<id>.*?/file/(\d+)</id>\s*<title>" + re.escape(filename) + r"</title>"
        match = re.search(entry_regex, single_response.text, re.DOTALL)

        if match:
            file_id = match.group(1)
            logging.debug(f"File '{filename}' exists on the server with file ID {file_id}.")
            return file_id  # Return the corresponding file ID

    logging.debug(f"No existing file '{filename}' found on the server.")
    return None  # Return None if no match is found


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


def create_ep_xml_file(xmlcontent):
    """Create XML file for the EPrint metadata."""
    filename = 'ep_metadata.xml'
    stream = open(filename, 'w')

    # Python 3 needs byte streams whereas python 3 needs a str
    # For this to work in python 2 encode it as utf8
    stream.write(xmlcontent)
    stream.close()

    return filename


def create_ep_xml_schema(doc):
    # Extract metadata from the YAML file
    experiment = doc['experiment']
    title = experiment['title']

    description = experiment['description']
    author = doc['author']

    additional_metadata = doc['meta-data']

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
    data_type_status = None
    subject = None
    institution = None
    note = ''
    no_funding = 'TRUE'
    acknowledged_funders = 'no_funders'
    is_published = None
    refereed = None

    for metadata_entry in additional_metadata:
        if 'oa.type' in metadata_entry:
            oa_type = metadata_entry['oa.type']['name']
        if 'institution' in metadata_entry:
            created_here = "yes" if metadata_entry['institution']['id'] == '01eezs655' else "no"
        if 'data.type' in metadata_entry:
            data_type = metadata_entry['data.type']['name']
            data_type_status = metadata_entry['data.type']['status']
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
        if 'ispublished' in metadata_entry:
            is_published = metadata_entry['ispublished']
        if 'refereed' in metadata_entry:
            refereed = metadata_entry['refereed']

    # Check if all required metadata is present
    if oa_type is None or created_here is None or data_type is None or subject is None or institution is None:
        logging.warning("Please provide all necessary fields: oa.type, institution, data.type, subject, department")
        exit()

    if data_type == "dataset" and data_type_status == "ongoing":
        data_type = "dataset_in_progress"

    # Create strings for subjects and institutions in the XML
    subjects_string = '<subjects>'
    subjects_string += '<item>%s</item>' % subject
    subjects_string += '</subjects>'

    institutions_string = '<institutions>'
    institutions_string += '<item>%s</item>' % institution
    institutions_string += '</institutions>'

    nofunding_string = '<nofunding>%s</nofunding>' % no_funding
    acknowledged_funders_string = '<acknowledged_funders>%s</acknowledged_funders>' % acknowledged_funders

    is_published_string = ""
    if is_published:
        is_published_string = '<ispublished>%s</ispublished>' % is_published

    refereed_string = ""
    if refereed:
        refereed_string = '<refereed>%s</refereed>' % refereed

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
                %s
                %s
                %s
                %s
            </eprint>
        </eprints>
        """ % (
        title, description, note, first_name, last_name, orcid, nds, data_type, oa_type, created_here, subjects_string,
        institutions_string,
        publication_date, date_type, is_published_string, nofunding_string, acknowledged_funders_string,
        refereed_string)

    logging.debug("XML request")
    logging.debug("--------------------------------------------------------------------")
    logging.debug(ep_xml)
    logging.debug("--------------------------------------------------------------------")

    return ep_xml


def load_netrc():
    """Load .netrc or _netrc credentials."""
    try:
        return netrc.netrc()
    except (FileNotFoundError, OSError):
        # Windows workaround because developer of netrc couldn't be bothered to take it into account
        try:
            return netrc.netrc(os.path.join(home, "_netrc"))
        except Exception as err:
            logging.warning(f"Netrc error: {err}")
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
    parser.add_argument('--force', action='store_true', help='Force update')
    parser.add_argument("--auto", action="store_true", help="Run without user interaction")

    args = parser.parse_args()

    path = args.path
    epid = args.epid
    user = args.user
    verbose = args.verbose
    force = args.force

    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format='%(asctime)s %(levelname)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        logging.getLogger().setLevel(logging.INFO)

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

    password = None

    if user is None and net:
        try:
            (user, account, password) = net.authenticators(BASE_URL[8:])
            logging.debug(f"User for {BASE_URL[8:]}: {user}")
        except:
            logging.debug(f"Error with {BASE_URL[8:]}: {sys.exc_info()[0]}")
            user = False
    else:
        user = False

    # No eprint id provided via args
    if epid is None:
        epid = False

    # User password
    # only prompt for password if a user is provided
    # curl and python.requests should attempt to use netrc instead
    # they will try to use .netrc (linux) or _netrc from the users home directory
    # The file should look like this machine <example.com> login <username> password <password>
    if user and password is None:
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
        logging.debug(f"YAML file located at {yamlfile}")

    yaml_mtime = os.path.getmtime(yamlfile)
    # First, get the file modification time as a naive datetime in local time:
    local_dt = datetime.fromtimestamp(yaml_mtime)
    # Then, convert it to a timezone-aware datetime in UTC:
    yaml_timestamp = local_dt.astimezone(timezone.utc)

    logging.debug(f"Local YAML file was last changed at {yaml_timestamp}")

    # Open yaml file
    stream = open(yamlfile, "r")
    doc = yaml.safe_load(stream)

    # TODO: What does this do?
    # Read and write finished flag
    if 'finished' in doc.keys():
        logging.info("Experiment completed!")
        cleanup()
        exit()

    docids = None
    if 'epid' in doc.keys():
        epid = doc['epid']

        if not args.auto:
            response = input("Please check if the eprint id is associated with the correct entry. Do you want to "
                             "proceed? (y/n): ").strip().lower()
            if response != "y":
                logging.info("Exiting ...")
                sys.exit(1)

    experiment_name = doc['experiment']['name']
    ep_xml = create_ep_xml_schema(doc)

    # YAML file was read
    stream.close()

    ep_xml_file = create_ep_xml_file(ep_xml)

    if not epid:
        headers = {}
        headers.update({'Content-Type': 'application/vnd.eprints.data+xml'})
        # If no EPrint ID, create a new EPrint entry
        data = open(ep_xml_file, 'rb').read()
        epid = send_sword_request(data, content_type='application/vnd.eprints.data+xml', send_file=False,
                                  headers=headers)

        m = re.search('[0-9]+$', str(epid))
        epid = m.group(0)

        logging.debug(f"Eprint with id {epid} was created")

        # Fetch document IDs of newly created entry
        # Pass no timestamp as it was newly created
        docids = get_document_ids(int(epid), experiment_name, yaml_timestamp=None)
    else:
        # Eprint entry already exists, so get the file ids of the main html files
        # The ids of the main html files (if more uploaded packages are available)
        docids = get_document_ids(int(epid), experiment_name, yaml_timestamp, type='fileid')

        logging.debug(f"Eprint with id {str(epid)} will be updated")

    logging.debug("The docids are the following:")
    logging.debug(docids)

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

    if docids and docids == -1:
        logging.info("Files already up to date")
        cleanup()
        exit()

    thisurl = BASE_URL + "/id/eprint/" + str(epid) + "/contents"

    # Upload all htmlfiles
    htmlpath = path  # + "/evaluations/" oder '/opt/DTSevaluations/example data/colorlearning/evaluations/'

    # indexfile currently has the same name as the measurement
    # Upload the index file (usually the main file) first and add the others to its epid
    indexfile = os.path.join(htmlpath, experiment_name + ".html")
    logging.debug(f"Index file is {indexfile}")

    if os.path.isfile(indexfile):
        if docids and len(docids) >= 1:
            # Main HTML file will be updated
            logging.debug("Add files to an existing entry")
            curl_target = BASE_URL + "/id/file/" + str(docids[0])
            logging.debug(f"Target url: {curl_target}")

            curl_send_file(indexfile, curl_target, action='PUT')
        else:
            curl_target = BASE_URL + "/id/eprint/" + str(epid) + "/contents"
            logging.debug(f"Adding files to a new entry {epid}")
            logging.debug(f"File tu upload: {indexfile}")
            logging.debug(f"Target url: {curl_target}")

            curl_send_file(indexfile, curl_target, action='POST')

        # Fetch the main document ID after the first upload
        response = get_document_ids(epid, experiment_name, yaml_timestamp=None, type='document')

        logging.debug("Response of first upload")
        logging.debug(response)

        docid = False
        if response and len(response) > 0:
            docid = response[0]
            logging.debug(f"Docid {docid} was request")
        else:
            logging.debug("No docid could be requested")

        if docid:
            # Collect all files that need to process
            files_to_upload = []
            for root, dirs, files in os.walk(path):
                for experiment_file in files:
                    filename, extension = os.path.splitext(experiment_file)
                    if extension in [".html", ".xml", ".yml"]:
                        files_to_upload.append(os.path.join(root, experiment_file))

            total_files = len(files_to_upload)
            logging.info(f"Total files to upload: {total_files}")

            bar_length = 40

            for i, experiment_file in enumerate(files_to_upload):
                headers = {}
                filename, extension = os.path.splitext(experiment_file)

                action = "POST"

                # Check if the file already exists on the server
                existing_file_id = get_existing_file_id(epid, os.path.basename(experiment_file))
                if existing_file_id:
                    # action = "PUT"
                    logging.debug(f"File with id {existing_file_id} already exists!")
                    # If file exists, delete it first before re-uploading
                    delete_existing_file(existing_file_id)

                # if experiment_file != indexfile:
                if verbose:
                    logging.debug(f"Attempt to upload {filename}.{extension}")

                curl_target = BASE_URL + "/id/document/" + docid + "/contents"

                logging.debug(f"Send to {curl_target} via {action}")

                curl_send_file(experiment_file, url=curl_target, action=action)

                # Update the progress bar
                progress = (i + 1) / total_files
                block = int(round(bar_length * progress))
                text = f"\rUploading: [{'#' * block + '-' * (bar_length - block)}] {progress * 100:.1f}% ({i + 1}/{total_files})"
                sys.stdout.write(text)
                sys.stdout.flush()
            print()
            logging.info("Upload finished")

    else:
        logging.info("HTML file doesn't exist")

    # Delete the ep_xml file
    cleanup()
