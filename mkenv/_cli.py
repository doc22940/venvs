from collections import defaultdict
from functools import wraps
import os
import pydoc
import sys

from characteristic import Attribute, attributes

from mkenv import __version__


class UsageError(Exception):
    pass


@attributes(
    [
        Attribute(name="kind"),
        Attribute(name="help", default_value="", exclude_from_repr=True),
        Attribute(name="type", default_value=lambda value : value),
        Attribute(name="repeat", default_value=1, exclude_from_repr=True),
        Attribute(name="_default", default_value=None, exclude_from_repr=True),
    ],
)
class Argument(object):
    def __init__(self, dest=None, nargs=None):
        if dest is None:
            dest = max(self.names, key=len).lstrip("-")
        self.dest = dest

        if nargs is None:
            nargs = getattr(self.kind, "nargs", 1)
        self.nargs = nargs

    @property
    def names(self):
        names = getattr(self.kind, "names", None)
        if names is None:
            return self.kind.name,
        return names

    def consume(self, command_line):
        dest, nargs = self.dest, self.nargs

        if nargs == 1:
            raw_value = self.type(next(command_line))
        elif nargs == "?":
            argument = next(command_line, None)
            if argument is None:
                raw_value = self.default()
            else:
                raw_value = self.type(argument)
        else:
            raw_value = [self.type(next(command_line)) for _ in xrange(nargs)]

        value = self.prepare(raw_value)
        seen = command_line.see(argument=self, value=value)

        repeat = self.repeat
        infinite_repeat = repeat is True
        if not infinite_repeat and len(seen) > repeat:
            name = " / ".join(self.names)
            raise UsageError("{0!r} specified multiple times".format(name))
        if infinite_repeat or repeat > 1:
            value = seen
        return [(dest, value)]

    def default(self):
        default = self._default
        if default is not None:
            return default()

        default = getattr(self.kind, "default", None)
        if default is not None:
            return default()

        if self.repeat is True or self.repeat > 1:
            return []
        return None

    def prepare(self, argument_value):
        return getattr(self.kind, "prepare", lambda arg : arg)(argument_value)

    def register(self):
        if self.kind.is_positional:
            return (self,), ()
        else:
            return (), [(name, self) for name in self.names]

    def emit_default(self):
        return [(self.dest, self.default())]

    def format_help(self):
        return "  {names:<20}        {self.help:<57}\n".format(
            names=", ".join(self.names),
            self=self,
        )


@attributes(
    [
        Attribute(name="names"),
        Attribute(name="store", default_value=True),
    ],
)
class Flag(object):
    is_positional = False
    nargs = 0

    def default(self):
        return not self.store

    def prepare(self, argument_value):
        return self.store


@attributes([Attribute(name="names")])
class Option(object):
    is_positional = False


@attributes([Attribute(name="name")])
class Positional(object):
    is_positional = True


@attributes([Attribute(name="members")], apply_with_cmp=False)
class Group(object):
    def register(self):
        positionals, nonpositionals = [], []
        for new_argument in self.members:
            new_positionals, new_nonpositionals = new_argument.register()
            positionals.extend(
                _Exclusivity.wrap(group=self, argument=argument)
                for argument in new_positionals
            )
            nonpositionals.extend(
                (name, _Exclusivity.wrap(group=self, argument=argument))
                for name, argument in new_nonpositionals
            )
        return positionals, nonpositionals

    def format_help(self):
        body = "".join(member.format_help() for member in self.members)
        return "\n" + body + "\n"

    def emit_default(self):
        # TODO: probably something different for required groups
        return []


@attributes([Attribute(name="argument"), Attribute(name="group")])
class _Exclusivity(object):
    def __init__(self):
        self.names = self.argument.names
        self.dest = self.argument.dest

    @classmethod
    def wrap(cls, argument, group):
        return cls(argument=argument, group=group)

    def consume(self, command_line):
        seen = command_line.see(self.group, value=self.argument)
        if set(seen) != set([self.argument]):
            raise UsageError(
                "specify only one of " + " or ".join(
                    repr(" / ".join(argument.names)) for argument in seen
                ),
            )
        else:
            return self.argument.consume(command_line=command_line)


class CLI(object):

    HELP = Argument(
        kind=Option(names=("-h", "--help")),
        help="Show usage information.",
    )
    VERSION = Argument(
        kind=Option(names=("-V", "--version")),
        help="Show version information."
    )

    def __init__(self, *argspec):
        self._nonpositionals = nonpositionals = {}
        self._positionals = positionals = []

        for argument in (self.HELP, self.VERSION) + argspec:
            for_positionals, for_nonpositionals = argument.register()
            positionals.extend(for_positionals)
            nonpositionals.update(for_nonpositionals)

        self.argspec = argspec

    def __call__(self, fn):
        @wraps(fn)
        def main(command_line=None, exit=sys.exit, arguments=None):
            if command_line is None:
                command_line = CommandLine()
            if arguments is None:
                arguments = {}

            help, _ = pydoc.splitdoc(pydoc.getdoc(fn))
            try:
                parsed = self.parse(command_line=command_line, help=help)
            except UsageError as error:
                command_line.stderr.write("error: ")
                command_line.stderr.write(str(error))
                command_line.stderr.write("\n\n")
                self.show_help(stdout=command_line.stdout, help=help)
                exit_status = os.EX_USAGE
            else:
                if parsed is None:
                    exit_status = os.EX_OK
                else:
                    parsed.update(arguments)
                    exit_status = main.with_arguments(
                        arguments=parsed,
                        stdin=command_line.stdin,
                        stdout=command_line.stdout,
                        stderr=command_line.stderr,
                    )
            exit(exit_status or os.EX_OK)
        main.with_arguments = fn
        return main

    def parse(self, command_line, help=""):  # XXX: help
        parsed = {}
        positionals = iter(self._positionals)
        nonpositionals = self._nonpositionals

        while command_line:
            argument = command_line.peek()
            if not argument.startswith("-"):
                found = next(positionals, None)
                if found is None:
                    raise UsageError("no such argument " + repr(argument))
                parsed.update(found.consume(command_line=command_line))
                continue

            found = nonpositionals.get(next(command_line))

            if found is None:
                raise UsageError("no such argument " + repr(argument))

            if found == CLI.HELP:
                self.show_help(help=help, stdout=command_line.stdout)
                return
            elif found == CLI.VERSION:
                command_line.stdout.write(__version__)
                command_line.stdout.write("\n")
                return
            else:
                try:
                    parsed.update(found.consume(command_line=command_line))
                except StopIteration:
                    message = "{0} takes {1} argument(s)"
                    raise UsageError(message.format(argument, found.nargs))

        for unseen in positionals:
            raise UsageError(
                "{0!r} is required".format(" / ".join(unseen.names)),
            )
        for argument in command_line.unseen(argspec=self.argspec):
            parsed.update(argument.emit_default())
        return parsed

    def show_help(self, help, stdout):
        if help:
            stdout.write(help)
            stdout.write("\n\n")
        stdout.write(self.concise_usage())
        stdout.write("\n\nUsage:\n")

        for argument in self.argspec:
            stdout.write(argument.format_help())

    def concise_usage(self):
        # XXX
        return "findenv"


@attributes(
    [
        Attribute(name="argv", default_factory=lambda : sys.argv[1:]),
        Attribute(
            name="stdin", default_value=sys.stdin, exclude_from_repr=True,
        ),
        Attribute(
            name="stdout", default_value=sys.stdout, exclude_from_repr=True,
        ),
        Attribute(
            name="stderr", default_value=sys.stderr, exclude_from_repr=True,
        ),
    ]
)
class CommandLine(object):
    def __init__(self):
        self._remaining = self.argv[::-1]
        self._seen = defaultdict(list)

    def __iter__(self):
        return self

    def __len__(self):
        return len(self._remaining)

    def next(self):
        try:
            return self._remaining.pop()
        except IndexError:
            raise StopIteration()

    def peek(self):
        return self._remaining[-1]

    def see(self, argument, value):
        """
        See a new value for the given argument.

        """

        seen = self._seen[argument]
        seen.append(value)
        return seen

    def unseen(self, argspec):
        """
        Filter out any unseen arguments during parsing.

        """

        return (argument for argument in argspec if argument not in self._seen)
