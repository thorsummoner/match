#!/usr/bin/env python3

import argparse
import itertools
import os
import stat
import filecmp

import xxhash

ARGP = argparse.ArgumentParser()
ARGP.add_argument('files', nargs='+', help='list of files to match')


def _hash(_file, _hash):
    with open(_file, 'rb') as fileh:
        for chunk in iter(lambda: fileh.read(4096), b''):
            _hash.update(chunk)
    return _hash.hexdigest()


class _File(object):
    def __init__(self, _file):
        self.file = _file

    _stat = None
    @property
    def stat(self):
        if self._stat is None:
            self._stat = os.stat(self.file)
        return self._stat

    @property
    def size(self):
        return self.stat.st_size

    _xxhashhex = None
    @property
    def _xxhash(self):
        if self._xxhashhex is None:
            self._xxhashhex = _hash(self.file, xxhash.xxh64())
        return self._xxhashhex

    def __eq__(self, other):
        if self.size != other.size:
            return False

        if self._xxhash != other._xxhash:
            return False

        return filecmp.cmp(self.file, other.file, shallow=False)

def _pairs(files):
    files = (_File(i) for i in files)
    for filea, fileb in itertools.combinations(files, 2):
        yield (filea, fileb,)

def main(argp=None):
    if argp is None:
        argp = ARGP.parse_args()


    pairs = _pairs(argp.files)
    for pair in pairs:
        if pair[0] != pair[1]:
            continue
        print('{}\t{}'.format(pair[0].file, pair[1].file))

if __name__ == '__main__':
    main()
