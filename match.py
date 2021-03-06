#!/usr/bin/env python3

import argparse
import itertools
import os
import stat
import filecmp
import sys
import logging
import collections
import pprint
import multiprocessing
import signal

import xxhash

logging.basicConfig(level=logging.INFO)

LOGGER = logging.getLogger(os.path.basename(__file__))

ARGP = argparse.ArgumentParser()
ARGP.add_argument('files', nargs='*', help='list of files to match')
ARGP.add_argument('--delimiter', dest='delimiter', default='\t', help='Use specified delimiter (default Tab)')
ARGP.add_argument('-z', '-N', '-0', action='store_const', const=b'\0', dest='delimiter', help='Use Null Delimiter')
ARGP.add_argument('--delete-prefix', help='Allow delting files under this prefix')
ARGP.add_argument('--delete', action='store_true', help='Unlink files as printed by --delete-prefix')
ARGP.add_argument('--name-match', '-n', action='store_true', help='Require file name to match')
ARGP.add_argument('--multiprocessing', '-j', type=int, help='Multiprocessing pool size')
ARGP_OUTPUT = ARGP.add_mutually_exclusive_group()
ARGP_OUTPUT.add_argument('--l0r0n', dest='output_mode', action='store_const', const='l0r0n')
ARGP_OUTPUT.add_argument('--pprint', dest='output_mode', action='store_const', const='pprint')

_Step = collections.namedtuple('_Step', ['iteration', 'digest', 'stepfunc', 'final'])

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

    @property
    def name(self):
        return os.path.basename(self.file)

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

def _filter(pairs, name_match=None):
    for pair in pairs:
        if name_match and pair[0].name != pair[1].name: continue
        yield pair

def _eq(pair):
    equal = None
    try:
        equal = pair[0] == pair[1]
    except FileNotFoundError:
        pass
    return (pair, equal,)

def _init_worker():
    signal.signal(signal.SIGINT, signal.SIG_IGN)

def _matches(pairs, pool=None):
    if pool is None:
        for pair in pairs:
            if not _eq(pair):
                continue
            yield pair

        return

    try:
        with pool as pool:
            for result in pool.imap_unordered(_eq, pairs):
                if not result[1]:
                    continue
                yield result[0]

            return
        pass
    except KeyboardInterrupt as err:
        pool.terminate()
        pool.close()
        raise SystemExit(err)

def _unlink_if_prefix_partial(delete_prefix, delete, left, right):
    if left.startswith(delete_prefix) and not right.startswith(delete_prefix):
        sys.stdout.buffer.write(left + b'\0')
        if delete:
            try:
                os.unlink(left)
            except FileNotFoundError as err:
                LOGGER.info(err)

        return True

def _unlink_if_prefix(delete_prefix, delete, match):
    flush = False
    flush = flush or _unlink_if_prefix_partial(delete_prefix, delete, match[0].file, match[1].file)
    flush = flush or _unlink_if_prefix_partial(delete_prefix, delete, match[1].file, match[0].file)
    if flush:
        sys.stdout.buffer.flush()


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
    matches = _matches(
        _filter(
            _pairs(files),
            name_match=argp.name_match
        ),
        pool=(multiprocessing.Pool(argp.multiprocessing, _init_worker) if argp.multiprocessing else None),
    )
    if argp.delete_prefix:
        argp.delete_prefix = argp.delete_prefix.encode('utf-8')

    for match in matches:
        if argp.delete_prefix:
            _unlink_if_prefix(argp.delete_prefix, argp.delete, match)
            continue

        if not argp.output_mode or argp.output_mode == 'pprint':
            pprint.pprint((match[0].file, match[1].file, ), width=len(pprint.pformat(match[0].file)))
        if argp.output_mode == 'l0r0n':
            sys.stdout.buffer.write(
                match[0].file
                + b'\0'
                + match[1].file
                + b'\0\n'
            )

if __name__ == '__main__':
    main()
