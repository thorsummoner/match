#!/usr/bin/env python3

import argparse
import itertools
import os
import stat
import filecmp
import sys
import logging
import collections

import xxhash

logging.basicConfig(level=logging.INFO)

LOGGER = logging.getLogger(os.path.basename(__file__))

ARGP = argparse.ArgumentParser()
ARGP.add_argument('files', nargs='*', help='list of files to match')
ARGP.add_argument('--delimiter', dest='delimiter', default='\t', help='Use specified delimiter (default Tab)')
ARGP.add_argument('-z', '-N', '-0', action='store_const', const=b'\0', dest='delimiter', help='Use Null Delimiter')
ARGP.add_argument('--delete-prefix', help='Allow delting files under this prefix')

_Step = collections.namedtuple('Step', ['iteration', 'digest', 'stepfunc', 'final'])

def exponential(initial=1):
    yield initial
    while True:
        initial*=initial
        yield initial


def _hash(_file, _hash):
   """ Hash whole file up front
   """
   with open(_file, 'rb') as fileh:
       for chunk in iter(lambda: fileh.read(4096), b''):
           _hash.update(chunk)
   return _hash.hexdigest()


def _stephash(_file, _hash, stepfunc=None):
    """ Hash file in 4096 blocks according to the stepping function
        (default exponentional stops, file hex at [1, 2, 4, 8 ...] * 4096 bytes)
    """
    if stepfunc is None:
        stepfunc = exponential

    stepping = stepfunc()

    step = next(stepping)
    with open(_file, 'rb') as fileh:
        iteration = 0
        for chunk in iter(lambda: fileh.read(4096), b''):
            _hash.update(chunk)
            iteration += 1
            if iteration >= step:
                yield _Step(step, _hash.digest(), stepfunc, 0)
                try:
                    step = next(stepping)
                except StopIteration as err:
                    raise SystemError(err)

    yield _Step(step, _hash.hexdigest(), stepfunc, 1)


class _File(object):
    def __init__(self, _file):
        self.file = _file
        if b'\0' in self.file:
            import pprint; pprint.pprint(self.file)
        self.stat = self._stat = os.stat(self.file)


    def __hash__(self):
        return self.file.__hash__()

    @property
    def size(self):
        return self.stat.st_size


    _stepxxhash_map = None
    @property
    def _stepxxhash(self):
        if self._stepxxhash_map is None:
            _map = list()
            for step in _stephash(self.file, xxhash.xxh64()):
                _map.append(step)
                yield step

            self._stepxxhash_map = _map
            self._xxhashhex = step.digest
            return
        yield from self._stepxxhash_map


    _xxhashhex = None
    @property
    def _xxhash(self):
        if self._xxhashhex is None:
            LOGGER.warning('File was hashed all at once!, file size of %s', self.size)
            self._xxhashhex = _hash(self.file, xxhash.xxh64())
        return self._xxhashhex

    def __eq__(self, other):
        if self.size != other.size:
            return False

        local_stop, other_stop = False, False
        local_hashsteps = self._stepxxhash
        other_hashsteps = other._stepxxhash
        try:
            while True:
                try:
                    local_step = next(local_hashsteps)
                except StopIteration:
                    local_stop = True
                try:
                    other_step = next(other_hashsteps)
                except StopIteration:
                    other_stop = True

                assert local_stop == other_stop, "File sizes differ"
                assert local_step.stepfunc == other_step.stepfunc, "step function differ"
                assert local_step.iteration == other_step.iteration, "iteration count differ"

                if local_stop:
                    break
        except AssertionError as err:
            LOGGER.error('Files failed assertion, %s and %s', self.file, other.file)
            raise err

        if local_step.digest != other_step.digest:
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
            if argp.delimiter:
                argp.files = sys.stdin.buffer.read().split(argp.delimiter)
            else:
                argp.files = [line.strip() for line in sys.stdin.buffer]

    LOGGER.info('files specified: %s', len(argp.files))
    # collect all files that exist
    files_all = list()
    for file_ in argp.files:
        try:
            file_ = _File(file_)
        except OSError as err:
            LOGGER.error(err)
            continue
        files_all.append(file_)

    LOGGER.info('files exist: %s', len(files_all))

    files = set(files_all)
    if len(files) < len(files_all):
        LOGGER.warning('Not all files names are unique')

    LOGGER.info('files unique: %s', len(files))

    # pair them together
    for pair in _pairs(files):
        if pair[0] != pair[1]:
            continue
        sys.stdout.buffer.write(
            pair[0].file
            + b'\0'
            + pair[1].file
            + b'\0\n'
        )

if __name__ == '__main__':
    main()
