# -*- coding: utf-8 -*-
"""Objects and functions related to the HashFS storage engine.

The HashFS storage engine implements a content-addressable storage, a storage facility mostly
suited for storing binary large objects (blobs). This is a simplified version of the HashFS
module developed by Derrick Gilland, and is only targeted at Python 3.x.

This module defines the HashFS class and related utilities.
"""

import glob
import hashlib
import io
import os
import shutil
from distutils.dir_util import mkpath
from tempfile import NamedTemporaryFile
from contextlib import closing

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
        with closing(stream):
            shash = self.compute_hash(stream)
            path = self._copy(stream, shash)
        return HashAddress(id, self.relpath(path), path)

    def _copy(self, stream, shash):
        """Copy the contents of `stream` to disk.

        The copy process uses a temporary file to store the initial contents and then moves that
        file to its final location.
        """
        path = self.idpath(shash)
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
        """Delete file using id or path.

        Remove any empty directories after deleting. No exception is raised if file doesn't exist.

        Arguments:
            file (str): address ID or path of file.
        """
        realpath = self.realpath(file)
        if realpath is None:
            return
        try:
            os.remove(realpath)
        except OSError:
            pass
        else:
            self.remove_empty(os.path.dirname(realpath))

    def remove_empty(self, subpath):
        """Remove empty folders.

        Successively remove all empty folders starting with `subpath` and proceeding 'up' through
        directory tree until reaching the `root` folder.
        """
        if not self.haspath(subpath):
            return
        while subpath != self.root:
            if len(os.listdir(subpath)) > 0 or os.path.islink(subpath):
                break
            os.rmdir(subpath)
            subpath = os.path.dirname(subpath)

    def exists(self, file):
        """Check whether a given file id or path exists on disk."""
        return bool(self.realpath(file))

    def haspath(self, path):
        """Return whether `path` is a subdirectory of the `root` directory."""
        return issubdir(path, self.root)

    def makepath(self, path):
        """Physically create the folder path on disk."""
        mkpath(path, mode=self.dmode)

    def relpath(self, path):
        """Return `path` relative to the `root` directory."""
        return os.path.relpath(path, self.root)

    def realpath(self, file):
        """Determine rea lpath of file.

        Attempt to determine the real path of a file id or path through successive checking of
        candidate paths. If the real path is stored with an extension, the path is considered a
        match if the basename matches the expected file path of the id.
        """
        # Check for absoluate path.
        if os.path.isfile(file):
            return file
        # Check for relative path.
        relpath = os.path.join(self.root, file)
        if os.path.isfile(relpath):
            return relpath
        # Check for sharded path.
        filepath = self.idpath(file)
        if os.path.isfile(filepath):
            return filepath
        # Check for sharded path with any extension.
        paths = glob.glob('{0}.*'.format(filepath))
        if paths:
            return paths[0]
        # Could not determine a match.
        return None

    def idpath(self, shash):
        """Build the file path for a given secure hash."""
        paths = self.shard(shash)
        return os.path.join(self.root, *paths)

    def compute_hash(self, stream):
        """Compute hash of file using `algorithm`."""
        hashobj = hashlib.new(self.algorithm)
        for data in stream:
            hashobj.update(to_bytes(data))
        return hashobj.hexdigest()

    def shard(self, shash):
        """Shard content ID into subfolders."""
        return shard(shash, self.depth, self.width)

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
        shash (str)  : secure hash (digest) of file contents.
        relpath (str): relative path location to `HashFS.root`.
        abspath (str): absolute path location of file on disk.
    """
    __slots__ = ('shash', 'relpath', 'abspath')
    def __init__(self, shash, relpath, abspath):
        self.shash        = shash
        self.relpath      = relpath
        self.abspath      = abspath

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
            raise ValueError('Stream.init: argument is not a valid file path or readable object')
        self._obj = obj
        self._pos = pos

    def __iter__(self):
        """Read underlying IO object and yield results. Return object to
        original position if we didn't open it originally.
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
        """Close underlying IO object if we opened it, else return it to original position.
        """
        if self._pos is None:
            self._obj.close()
        else:
            self._obj.seek(self._pos)

def issubdir(subpath, path):
    """Return whether `subpath` is a sub-directory of `path`."""
    # Append os.sep so that paths like /usr/var2/log doesn't match /usr/var.
    path = os.path.realpath(path) + os.sep
    subpath = os.path.realpath(subpath)
    return subpath.startswith(path)

def shard(digest, depth, width):
    """Create a list of `depth` of tokens with width `width` from the first part of the digest
    (secure hash) id plus the remainder.
    """
    items = [digest[k * width:width * (k + 1)] for k in range(depth)] + [digest[depth * width:]]
    return [item for item in items if item]

def to_bytes(text):
    if not isinstance(text, bytes):
        text = bytes(text, 'utf8')
    return text