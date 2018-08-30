#!/usr/bin/env python3

import argparse
import itertools
import os
import stat
import filecmp
import sys
import logging

import xxhash

logging.basicConfig(level=logging.INFO)

LOGGER = logging.getLogger(os.path.basename(__file__))

ARGP = argparse.ArgumentParser()
ARGP.add_argument('files', nargs='*', help='list of files to match')
ARGP.add_argument('--delimiter', dest='delimiter', default='\t', help='Use specified delimiter (default Tab)')
ARGP.add_argument('-z', '-N', '-0', action='store_const', const='\0', dest='delimiter', help='Use Null Delimiter')


def _hash(_file, _hash):
    with open(_file, 'rb') as fileh:
        for chunk in iter(lambda: fileh.read(4096), b''):
            _hash.update(chunk)
    return _hash.hexdigest()


class _File(object):
    def __init__(self, _file):
        self.file = _file
        self.stat = self._stat = os.stat(self.file)


    def __hash__(self):
        return self.file.__hash__()

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
    for filea, fileb in itertools.combinations(files, 2):
        yield (filea, fileb,)

def main(argp=None):
    if argp is None:
        argp = ARGP.parse_args()
        if not argp.files:
            argp.files = [line.strip() for line in sys.stdin]

    # collect all files that exist
    files_all = list()
    for file_ in argp.files:
        try:
            file_ = _File(file_)
        except OSError as err:
            LOGGER.error(err)
            continue
        files_all.append(file_)

    files = set(files_all)
    if len(files) < len(files_all):
        LOGGER.warning('Not all files names are unique')

    # pair them together
    pairs = _pairs(files)
    for pair in pairs:
        if pair[0] != pair[1]:
            continue
        print('{}{}{}'.format(pair[0].file, argp.delimiter, pair[1].file))

if __name__ == '__main__':
    main()
