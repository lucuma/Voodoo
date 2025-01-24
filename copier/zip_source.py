import zipfile
import os
import requests
from tempfile import mkdtemp
from io import BytesIO
from zipfile import ZipFile
from urllib.request import urlopen

HTTP_PREFIX = ("https://", "http://")
ZIP_POSTFIX = ".zip"

def is_zip_url(url: str) -> bool:
    """Indicate if a url is a zip file."""
    return url.endswith(ZIP_POSTFIX)

def _location_after_extract(zf, location):
    """If all files of the zip are in a single directory, return the subdirectory."""
    files = zf.namelist()
    first_file = files[0]
    if all(ele.startswith(first_file) for ele in files):
        location = os.path.join(location + "/" + first_file)
    return location

def unzip(url: str) -> None:
    """
    Unzip a template zip file from local or http endpoint.
    return the location of the unzipped files.
    """
    location = mkdtemp(prefix=f"{__name__}.unzip.")
    if url.startswith(HTTP_PREFIX):
        resp = urlopen(url)
        input_zip = BytesIO(resp.read())
    else:
        input_zip = url
    
    with zipfile.ZipFile(input_zip, "r") as zf:
        zf.extractall(location)
        return _location_after_extract(zf, location)