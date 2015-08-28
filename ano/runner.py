#!/usr/bin/env python2
# -*- coding: utf-8; -*-

"""\
Arturo is a command-line toolkit for working with Arduino hardware.

It is intended to replace Arduino IDE UI for those who prefer to work in
terminal or want to integrate Arduino development in a 3rd party IDE.

Arturo can build sketches, libraries, upload firmwares, establish
serial-communication. For this it is split in a bunch of subcommands, like git
or mercurial do. The full list is provided below. You may run any of them with
--help to get further help. E.g.:

    ano build --help
"""

import sys
import os.path
import argparse
import inspect

import ano.commands

from ano.commands.base import Command
from ano.conf import configure
from ano.exc import Abort
from ano.filters import colorize
from ano.environment import Environment
from ano.argparsing import FlexiFormatter


def main():
    e = Environment()
    e.load()

    conf = configure()

    try:
        current_command = sys.argv[1]
    except IndexError:
        current_command = None

    parser = argparse.ArgumentParser(prog='ano', formatter_class=FlexiFormatter, description=__doc__)
    subparsers = parser.add_subparsers()
    is_command = lambda x: inspect.isclass(x) and issubclass(x, Command) and x != Command
    commands = [cls(e) for _, cls in inspect.getmembers(ano.commands, is_command)]
    for cmd in commands:
        p = subparsers.add_parser(cmd.name, formatter_class=FlexiFormatter, help=cmd.help_line)
        if current_command != cmd.name:
            continue
        cmd.setup_arg_parser(p)
        p.set_defaults(func=cmd.run, **conf.as_dict(cmd.name))

    args = parser.parse_args()

    try:
        run_anywhere = "init clean list-models serial version"

        e.process_args(args)

        if current_command not in run_anywhere:
            if os.path.isdir(e.output_dir):
                # we have an output dir so we'll pretend this is a project folder
                None
            elif e.src_dir is None or not os.path.isdir(e.src_dir):
                raise Abort("No project found in this directory.")

        if current_command not in run_anywhere:
            # For valid projects create .build & lib
            if not os.path.isdir(e.build_dir):
                os.makedirs(e.build_dir)

            if not os.path.isdir(e.lib_dir):
                os.makedirs(e.lib_dir)
                with open('lib/.holder', 'w') as f:
                    f.write("")

        args.func(args)
    except Abort as exc:
        print colorize(str(exc), 'red')
        sys.exit(1)
    except KeyboardInterrupt:
        print 'Terminated by user'
    finally:
        e.dump()
