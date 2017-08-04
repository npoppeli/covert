# -*- coding: utf-8 -*-
"""Objects and functions related to the HashFS storage engine.

The HashFS storage engine implements a content-addressable storage, a storage facility mostly
suited for storing binary large objects (blobs). This is a simplified version of the HashFS
module developed by Derrick Gilland, and is only targeted at Python 3.x.

This module defines the HashFS class and related utilities.
"""

import hashlib, io, os, shutil
from distutils.dir_util import mkpath
from tempfile import NamedTemporaryFile

def to_bytes(s):
    return s if isinstance(s, bytes) else bytes(s, 'utf8')

class HashFS:
    """Class that implements a content-addressable file store.

    Attributes:
        root (str)     : root of storage space (directory).
        depth (int)    : depth of sub-folders to create when saving a file.
        width (int)    : width of each sub-folder to create when saving a file.
        algorithm (str): hash algorithm to use when computing file hash.
        fmode (int)    : file mode permission to set when adding files to directory.
        dmode (int)    : directory mode permission to set for sub-folders.
    """
    def __init__(self, root, depth=1, width=2, algorithm='sha256', fmode=0o664, dmode=0o755):
        self.root      = os.path.realpath(root)
        self.depth     = depth
        self.width     = width
        self.algorithm = algorithm
        self.fmode     = fmode
        self.dmode     = dmode

    def put(self, file):
        """Store contents of `file` on disk using its  digest (secure hash) for the address.

        Arguments:
            file: readable object or path to file.

        Returns:
            HashAddress: hash address of file.
        """
        stream = Stream(file)
        digest = self.compute_digest(stream)
        path = self._copy(stream, digest)
        stream.close()
        return HashAddress(digest, self.relpath(path), path)

    def _copy(self, stream, digest):
        """Copy the contents of `stream` to disk.

        The copy process uses a temporary file to store the initial contents and then moves that
        file to its final location.
        """
        path = self.idpath(digest)
        if not os.path.isfile(path):
            file_name = self._temp_file(stream)
            self.makepath(os.path.dirname(path))
            shutil.move(file_name, path)
        return path

    def _temp_file(self, stream):
        """Create a named temporary file from a :class:`Stream` object and
        return its filename.
        """
        temp_file = NamedTemporaryFile(delete=False)
        if self.fmode is not None:
            mask = os.umask(0)
            try:
                os.chmod(temp_file.name, self.fmode)
            finally:
                os.umask(mask)
        for data in stream:
            temp_file.write(to_bytes(data))
        temp_file.close()
        return temp_file.name

    def get(self, file):
        """Return `HashAddress` for given digest or path.
        
        If `file` does not refer to a valid file, return ``None``.

        Arguments:
            file (str): address ID or path of file.

        Returns:
            hash address of file (HashAddress)
        """
        realpath = self.realpath(file)
        if realpath is None:
            return None
        else:
            return HashAddress(self.unshard(realpath), self.relpath(realpath), realpath)

    def open(self, file, mode='rb'):
        """Return open buffer object from given id or path.

        Arguments:
            file (str): address ID or path of file.
            mode (str): mode for opening file.

        Returns:
            Buffer: an ``io`` buffer dependent on the `mode`.

        Raises:
            IOError: if file doesn't exist.
        """
        realpath = self.realpath(file)
        if realpath is None:
            raise IOError('Could not locate file: {0}'.format(file))
        return io.open(realpath, mode)

    def delete(self, file):
        """Delete file using id or path. Remove any empty directories after deleting.
        No exception is raised if file does not exist.

        Arguments:
            file (str): address ID or path of file.
        """
        real_path = self.realpath(file)
        if real_path is None:
            return
        try:
            os.remove(real_path)
        except OSError:
            pass
        else:
            self.remove_empty(os.path.dirname(real_path))

    def remove_empty(self, path):
        """Remove empty folders.

        Successively remove all empty folders starting with `path` and proceeding 'up' through
        directory tree until reaching the `root` folder.
        """
        if not self.haspath(path):
            return
        while path != self.root:
            if len(os.listdir(path)) > 0 or os.path.islink(path):
                break
            os.rmdir(path)
            path = os.path.dirname(path)

    def exists(self, file):
        """Check whether a given file id or path exists on disk."""
        return bool(self.realpath(file))

    def haspath(self, path):
        """Return whether `path` is a subdirectory of the `root` directory."""
        root = os.path.realpath(self.root) + os.sep
        path = os.path.realpath(path)
        return path.startswith(root)

    def makepath(self, path):
        """Physically create the folder path on disk."""
        mkpath(path, mode=self.dmode)

    def relpath(self, path):
        """Return `path` relative to the `root` directory."""
        return os.path.relpath(path, self.root)

    def realpath(self, file):
        """Determine real path of file.

        Attempt to determine the real path of a file id or path through successive checking of
        candidate paths.
        """
        # check for absolute path
        if os.path.isfile(file):
            return file
        # check for relative path
        relpath = os.path.join(self.root, file)
        if os.path.isfile(relpath):
            return relpath
        # check for sharded path
        filepath = self.idpath(file)
        if os.path.isfile(filepath):
            return filepath
        # no match
        return None

    def idpath(self, digest):
        """Build the file path for a given secure hash."""
        path_list = self.shard(digest)
        return os.path.join(self.root, *path_list)

    def compute_digest(self, stream):
        """Compute digest of file."""
        hashobj = hashlib.new(self.algorithm)
        for data in stream:
            hashobj.update(to_bytes(data))
        return hashobj.hexdigest()

    def shard(self, digest):
        """Divide `digest` into folder path and file name. Procedure: create a list of `depth` of
        tokens with width `width` from the first part of the digest plus the remainder.
        """
        d, w = self.depth, self.width
        items = [digest[w*k:w*(k+1)] for k in range(d)] + [digest[d*w:]]
        return [item for item in items if item]

    def unshard(self, path):
        """Unshard path to determine hash value."""
        if not self.haspath(path):
            raise ValueError("unshard: path '{}' is not subdirectory of root '{}'".\
                             format(path, self.root))
        return os.path.splitext(self.relpath(path))[0].replace(os.sep, '')

    def __contains__(self, file):
        """Return whether a given file id or path is contained in the
        :attr:`root` directory.
        """
        return self.exists(file)

class HashAddress:
    """File address containing file's path on disk and it's content hash ID.

    Attributes:
        digest (str)  : secure hash (digest) of file contents.
        relpath (str): relative path location to `HashFS.root`.
        abspath (str): absolute path location of file on disk.
    """
    __slots__ = ('digest', 'relpath', 'abspath')
    def __init__(self, digest, relpath, abspath):
        self.digest  = digest
        self.relpath = relpath
        self.abspath = abspath

class Stream:
    """Common interface for file-like objects.

    The input `obj` can be a file-like object or a path to a file. If `obj` is a path to a file,
    then it will be opened until `close` is called. If `obj` is a file-like object, then it's
    original position will be restored when `close` is called instead of closing the object
    automatically. Closing of the stream is deferred to whatever process passed the stream in.

    Successive readings of the stream is supported without having to manually set it's position
    back to ``0``.
    """
    def __init__(self, obj):
        if hasattr(obj, 'read'):
            pos = obj.tell()
        elif os.path.isfile(obj):
            obj = io.open(obj, 'rb')
            pos = None
        else:
            raise ValueError('Stream: {} is not a valid file path or readable object'.format(obj))
        self._obj = obj
        self._pos = pos

    def __iter__(self):
        """Read underlying IO object and yield results. Return object to
        original position if this application did not open it originally.
        """
        self._obj.seek(0)
        while True:
            data = self._obj.read()
            if not data:
                break
            yield data
        if self._pos is not None:
            self._obj.seek(self._pos)

    def close(self):
        """Close underlying IO object if this application opened it, else return it to original position.
        """
        if self._pos is None:
            self._obj.close()
        else:
            self._obj.seek(self._pos)
