"""
Contains classes and utilities that help publishing a hyde website to
a filesystem using PyFilesystem FS objects.

This publisher provides an easy way to publish to FTP, SFTP, WebDAV or other
servers by specifying a PyFS filesystem URL.  For example, the following
are valid URLs that can be used with this publisher:

    ftp://my.server.com/~username/my_blog/
    dav:https://username:password@my.server.com/path/to/my/site

"""

import getpass
import hashlib


from hyde._compat import basestring, input
from hyde.publisher import Publisher

from commando.util import getLoggerWithNullHandler

logger = getLoggerWithNullHandler('hyde.ext.publishers.pyfs')


try:
    from fs.osfs import OSFS
    from fs.path import join as pathjoin
    from fs import open_fs
except ImportError:
    logger.error("The PyFS publisher requires PyFilesystem v0.4 or later.")
    logger.error("`pip install -U fs` to get it.")
    raise


class PyFS(Publisher):

    def initialize(self, settings):
        self.settings = settings
        self.url = settings.url
        self.check_mtime = getattr(settings, "check_mtime", False)
        self.check_etag = getattr(settings, "check_etag", False)
        if self.check_etag and not isinstance(self.check_etag, basestring):
            raise ValueError("check_etag must name the etag algorithm")
        self.prompt_for_credentials()
        self.fs = open_fs(self.url)

    def prompt_for_credentials(self):
        credentials = {}
        if "%(username)s" in self.url:
            print("Username: ",)
            credentials["username"] = input().strip()
        if "%(password)s" in self.url:
            credentials["password"] = getpass.getpass("Password: ")
        if credentials:
            self.url = self.url % credentials

    def publish(self):
        super(PyFS, self).publish()
        deploy_fs = OSFS(self.site.config.deploy_root_path.path)
        for step in deploy_fs.walk():
            dirnm = step.path
            local_filenms = [f.name for f in step.files]
            logger.info("Making directory: %s", dirnm)
            self.fs.makedir(dirnm, recreate=True)
            remote_fileinfos = list(self.fs.filterdir(dirnm, exclude_dirs=['*'], namespaces=['basic', 'details']))
            #  Process each local file, to see if it needs updating.
            for filenm in local_filenms:
                filepath = pathjoin(dirnm, filenm)
                #  Try to find an existing remote file, to compare metadata.
                for info in remote_fileinfos:
                    if info.name == filenm:
                        break
                else:
                    info = None
                #  Skip it if the etags match
                # if self.check_etag and "etag" in info:
                #    with deploy_fs.open(filepath, "rb") as f:
                #        local_etag = self._calculate_etag(f)
                #    if info["etag"] == local_etag:
                #        logger.info("Skipping file [etag]: %s", filepath)
                #        continue
                #  Skip it if the mtime is more recent remotely.
                if info and self.check_mtime:
                    linfo = deploy_fs.getinfo(filepath, namespaces=['basic', 'details'])
                    local_mtime = linfo.modified
                    if info.modified > local_mtime:
                        logger.info("Skipping file [mtime]: %s", filepath)
                        continue
                #  Upload it to the remote filesystem.
                logger.info("Uploading file: %s", filepath)
                with deploy_fs.open(filepath, "rb") as f:
                    self.fs.writefile(filepath, f)
            #  Process each remote file, to see if it needs deleting.
            for info in remote_fileinfos:
                filepath = pathjoin(dirnm, info.name)
                if filepath not in local_filenms:
                    logger.info("Removing file: %s", filepath)
                    self.fs.remove(filepath)

    def _calculate_etag(self, f):
        hasher = getattr(hashlib, self.check_etag.lower())()
        data = f.read(1024 * 64)
        while data:
            hasher.update(data)
            data = f.read(1024 * 64)
        return hasher.hexdigest()
