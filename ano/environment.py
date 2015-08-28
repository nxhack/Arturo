# -*- coding: utf-8; -*-

import sys
import os.path
import itertools
import pickle
import platform
import hashlib
import re

try:
    from collections import OrderedDict
except ImportError:
    # Python < 2.7
    from ordereddict import OrderedDict

from collections import namedtuple
from glob2 import glob

from ano.filters import colorize
from ano.utils import format_available_options
from ano.exc import Abort


class Version(namedtuple('Version', 'major minor build')):

    regex = re.compile(ur'^([^:]+:)?(\d+(\.\d+(\.\d+)?)?)')

    @classmethod
    def parse(cls, s):
        # Version could have various forms
        #   0022
        #   0022ubuntu0.1
        #   0022-macosx-20110822
        #   1.0
        #   1:1.0.5+dfsg2-1
        # We have to extract a 3-int-tuple (major, minor, build)
        match = cls.regex.match(s)
        if not match:
            raise Abort("Could not parse Arduino library version: %s" % s)

        # v is numbers possibly split by dots without a trash
        v = match.group(2)

        if v.startswith('0'):
            # looks like old 0022 or something like that
            return cls(0, int(v), 0)

        parts = map(int, v.split('.'))

        # append nulls if they were not explicit
        while len(parts) < 3:
            parts.append(0)

        return cls(*parts)

    def as_int(self):
        if not self.major:
            return self.minor
        return self.major * 100 + self.minor * 10 + self.build

    def __str__(self):
        return '%s.%s.%s' % self


class Environment(dict):

    templates_dir = os.path.join(os.path.dirname(__file__), 'templates')
    output_dir = '.build_ano'
    lib_dir = 'lib'
    hex_filename = 'firmware.hex'

    arduino_user_dir = None
    arduino_user_dir_guesses = [
        'libraries',
        os.path.expanduser("~/Documents/Arduino"),
        os.path.expanduser("~/Arduino")
    ]

    platformSystem = platform.system()

    arduino_dist_dir = None
    arduino_dist_dir_guesses = [
        '/usr/local/share/arduino',
        '/usr/share/arduino',
    ]

    if platformSystem == 'Darwin':
        arduino_dist_dir_guesses.insert(0, '/Applications/Arduino.app/Contents/Resources/Java')
        arduino_dist_dir_guesses.insert(0, '/Applications/Arduino.app/Contents/Java')
    elif platformSystem == 'Windows':
        arduino_user_dir_guesses.insert(0, os.path.expanduser(os.path.join("~", "My Documents", "Arduino")))

    default_board_model = 'uno'
    ano = sys.argv[0]

    def __init__(self):
        super(Environment, self).__init__()
        self['__ano_objectVersion__'] = 3;

    def dump(self):
        if not os.path.isdir(self.output_dir):
            return
        with open(self.dump_filepath, 'wb') as f:
            pickle.dump(self.items(), f, pickle.HIGHEST_PROTOCOL)

    def load(self):
        if not os.path.exists(self.dump_filepath):
            return
        needToResetPickle = False
        with open(self.dump_filepath, 'rb') as f:
            try:
                unjarred = dict(pickle.load(f))
                if unjarred['__ano_objectVersion__'] != self['__ano_objectVersion__']:
                    needToResetPickle = True
                else:
                    self.update(unjarred)
            except:
                needToResetPickle = True

        if needToResetPickle:
            os.remove(self.dump_filepath)

    @property
    def dump_filepath(self):
        return os.path.join(self.output_dir, 'environment-ano.pickle')

    def __getitem__(self, key):
        try:
            return super(Environment, self).__getitem__(key)
        except KeyError as e:
            try:
                return getattr(self, key)
            except AttributeError:
                raise e

    def __getattr__(self, attr):
        try:
            return super(Environment, self).__getitem__(attr)
        except KeyError:
            raise AttributeError("Environment has no attribute %r" % attr)

    @property
    def hex_path(self):
        return os.path.join(self.build_dir, self.hex_filename)

    def _find(self, key, items, places, human_name, join, multi, optional):
        """
        Search for file-system entry with any name passed in `items` on
        all paths provided in `places`. Use `key` as a cache key.

        If `join` is True result will be a path join of place/item,
        otherwise only place is taken as result.

        Return first found match unless `multi` is True. In that case
        a list with all fount matches is returned.

        Raise `Abort` if no matches were found.
        """
        if key in self:
            return self[key]

        human_name = human_name or key

        # expand env variables in `places` and split on colons
        places = itertools.chain.from_iterable(os.path.expandvars(p).split(os.pathsep) for p in places)
        places = map(os.path.expanduser, places)

        glob_places = itertools.chain.from_iterable(glob(p) for p in places)

        print 'Searching for', human_name, '...',
        results = []
        for p in glob_places:
            for i in items:
                path = os.path.join(p, i)
                if os.path.exists(path):
                    result = path if join else p
                    if not multi:
                        print colorize(result, 'green')
                        self[key] = result
                        return result
                    results.append(result)

        if results:
            if len(results) > 1:
                formatted_results = ''.join(['\n  - ' + x for x in results])
                print colorize('found multiple: %s' % formatted_results, 'green')
            else:
                print colorize(results[0], 'green')

            self[key] = results
            return results

        print colorize('FAILED', 'red')
        if not optional:
            raise Abort("%s not found. Searched in following places: %s" %
                        (human_name, ''.join(['\n  - ' + p for p in places])))
        else:
            self[key] = None
            return results

    def find_dir(self, key, items, places, human_name=None, multi=False, optional=False):
        return self._find(key, items or ['.'], places, human_name, join=False, multi=multi, optional=optional)

    def find_file(self, key, items=None, places=None, human_name=None, multi=False):
        return self._find(key, items or [key], places, human_name, join=True, multi=multi, optional=False)

    def find_tool(self, key, items, places=None, human_name=None, multi=False):
        return self.find_file(key, items, places or ['$PATH'], human_name, multi=multi)

    def find_arduino_dir(self, key, dirname_parts, items=None, human_name=None, multi=False, optional=False):
        return self.find_dir(key, items, self.arduino_dist_places(dirname_parts), human_name, multi=multi, optional=optional)

    def find_arduino_user_dir(self, key, dirname_parts, items=None, human_name=None, multi=False, optional=False):
        return self.find_dir(key, items, self.arduino_user_places(dirname_parts), human_name, multi=multi, optional=optional)

    def find_arduino_file(self, key, dirname_parts, items=None, human_name=None, multi=False):
        return self.find_file(key, items, self.arduino_dist_places(dirname_parts), human_name, multi=multi)

    def find_arduino_tool(self, key, dirname_parts, items=None, human_name=None, multi=False):
        # if not bundled with Arduino Software the tool should be searched on PATH
        places = self.arduino_dist_places(dirname_parts) + ['$PATH']
        return self.find_file(key, items, places, human_name, multi=multi)

    def arduino_user_places(self, dirname_parts):
        return self.guess_at_places('arduino_user_dir', self.arduino_user_dir_guesses, dirname_parts)

    def arduino_dist_places(self, dirname_parts):
        """
        For `dirname_parts` like [a, b, c] return list of
        search paths within Arduino distribution directory like:
            /user/specified/path/a/b/c
            /usr/local/share/arduino/a/b/c
            /usr/share/arduino/a/b/c
        """
        return self.guess_at_places('arduino_dist_dir', self.arduino_dist_dir_guesses, dirname_parts)

    def guess_at_places(self, key, guesses, dirname_parts):
        if key in self:
            places = [self[key]]
        else:
            places = guesses
        return [os.path.join(p, *dirname_parts) for p in places]

    def board_models(self):
        if 'board_models' in self:
            return self['board_models']

        # boards.txt can be placed in following places
        # - hardware/arduino/boards.txt (Arduino IDE 0.xx, 1.0.x)
        # - hardware/arduino/{chipset}/boards.txt (Arduino 1.5.x, chipset like `avr`, `sam`)
        # - hardware/{platform}/boards.txt (MPIDE 0.xx, platform like `arduino`, `pic32`)
        # we should find and merge them all
        boards_txts = self.find_arduino_file('boards.txt', ['hardware', '**'],
                                             human_name='Board description file (boards.txt)',
                                             multi=True)

        self['board_models'] = BoardModels()
        self['board_models'].default = self.default_board_model
        for boards_txt in boards_txts:
            with open(boards_txt) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue

                    # Transform lines like:
                    #   yun.upload.maximum_data_size=2560
                    # into a nested dict `board_models` so that
                    #   self['board_models']['yun']['upload']['maximum_data_size'] == 2560
                    multikey, _, val = line.partition('=')
                    multikey = multikey.split('.')

                    # traverse into dictionary up to deepest level
                    # create nested dictionaries if they aren't exist yet
                    subdict = self['board_models']
                    for key in multikey[:-1]:
                        if key not in subdict:
                            subdict[key] = {}
                        elif not isinstance(subdict[key], dict):
                            # it happens that a particular key
                            # has a value and has sublevels at same time. E.g.:
                            #   diecimila.menu.cpu.atmega168=ATmega168
                            #   diecimila.menu.cpu.atmega168.upload.maximum_size=14336
                            #   diecimila.menu.cpu.atmega168.upload.maximum_data_size=1024
                            #   diecimila.menu.cpu.atmega168.upload.speed=19200
                            # place value `ATmega168` into a special key `_` in such case
                            subdict[key] = {'_': subdict[key]}
                        subdict = subdict[key]

                    subdict[multikey[-1]] = val

                    # store spectial `_coredir` value on top level so we later can build
                    # paths relative to a core directory of a specific board model
                    self['board_models'][multikey[0]]['_coredir'] = os.path.dirname(boards_txt)

        return self['board_models']

    def board_model(self, key):
        return self.board_models()[key]

    def add_board_model_arg(self, parser):
        helpText = '\n'.join([
            "Arduino board model (default: %(default)s)",
            "For a full list of supported models run:",
            "`ano list-models'"
        ])

        parser.add_argument('-m', '--board-model', metavar='MODEL',
                            default=self.default_board_model, help=helpText)

        parser.add_argument('-s', '--source-dir', metavar='SOURCE',
                    default='src',
                    help='The name of the directory which contains '
                    'the project source/sketches. By default this is '
                    'a folder named src.')

        parser.add_argument('--cpu', metavar='CPU',
                            default=self.default_board_model, help='''
Additional CPU argument required for board models available with different CPUs (e.g. Arduino Pro).''')

    def add_arduino_dist_arg(self, parser):
        parser.add_argument('-d', '--arduino-dist', metavar='PATH',
                            help='Path to Arduino distribution, e.g. ~/Downloads/arduino-0022.\nTry to guess if not specified')

    def serial_port_patterns(self):
        system = platform.system()
        if system == 'Linux':
            return ['/dev/ttyACM*', '/dev/ttyUSB*']
        if system == 'Darwin':
            return ['/dev/tty.usbmodem*', '/dev/tty.usbserial*']
        raise NotImplementedError("Not implemented for Windows")

    def list_serial_ports(self):
        ports = []
        for p in self.serial_port_patterns():
            matches = glob(p)
            ports.extend(matches)
        return ports

    def guess_serial_port(self):
        print 'Guessing serial port ...',

        ports = self.list_serial_ports()
        if ports:
            result = ports[0]
            print colorize(result, 'yellow')
            return result

        print colorize('FAILED', 'red')
        raise Abort("No device matching following was found: %s" %
                    (''.join(['\n  - ' + p for p in self.serial_port_patterns()])))

    def process_args(self, args):
        self.src_dir = getattr(args, 'source_dir', None)

        arduino_dist = getattr(args, 'arduino_dist', None)
        if arduino_dist:
            self['arduino_dist_dir'] = os.path.realpath(arduino_dist)

        board_model = getattr(args, 'board_model', None)
        if board_model:
            all_models = self.board_models()
            if board_model not in all_models:
                print "Supported Arduino board models are:"
                print all_models.format()
                raise Abort('%s is not a valid board model' % board_model)

        # Build artifacts for each Arduino distribution / Board model
        # pair should go to a separate subdirectory
        build_dirname = board_model or self.default_board_model
        if arduino_dist:
            distHash = hashlib.md5(arduino_dist).hexdigest()[:8]
            build_dirname = '%s-%s' % (build_dirname, distHash)

        self['build_dir'] = os.path.join(self.output_dir, build_dirname)

    @property
    def arduino_lib_version(self):
        self.find_arduino_file('version.txt', ['lib'],
                               human_name='Arduino lib version file (version.txt)')

        if 'arduino_lib_version' not in self:
            with open(self['version.txt']) as f:
                print 'Detecting Arduino software version ... ',
                v_string = f.read().strip()
                v = Version.parse(v_string)
                self['arduino_lib_version'] = v
                print colorize("%s (%s)" % (v, v_string), 'green')

        return self['arduino_lib_version']


class BoardModels(OrderedDict):

    @classmethod
    def getValueForVariant(cls, boardsDict, variant, keyType, key):
        if variant is not None:
            try:
                return boardsDict['menu']['cpu'][variant][keyType][key]
            except KeyError:
                None

        try:
            return boardsDict[keyType][key]
        except KeyError as e:
            if 'menu' in boardsDict and 'cpu' in boardsDict['menu']:
                raise KeyError("Are you missing --cpu %s" % (str(boardsDict['menu']['cpu'].keys())))
            else:
                raise e;

    def format(self):
        boardsMap = [(key, val['name']) for key, val in self.iteritems() if 'name' in val]
        return format_available_options(boardsMap, head_width=12, default=self.default)
