import datetime
import json
import os
import sys
import time
from sys import exit
from typing import Callable, Optional, Union
import ansiescapes

if os.name == "nt":
    # Windows
    import msvcrt
else:
    # Not Windows \o/
    import select


class Utils:
    def __init__(self, name="Python Script"):
        self.name = name
        # Init our colors before we need to print anything
        cwd = os.getcwd()
        os.chdir(os.path.dirname(os.path.realpath(__file__)))
        if os.path.exists("colors.json"):
            self.colors_dict = json.load(open("colors.json"))
        else:
            self.colors_dict = {}
        os.chdir(cwd)

    def grab(self, prompt, **kwargs):
        # Takes a prompt, a default, and a timeout and shows it with that timeout
        # returning the result
        timeout = kwargs.get("timeout", 0)
        default = kwargs.get("default", None)
        # If we don't have a timeout - then skip the timed sections
        if timeout <= 0:
            return input(prompt)
        # Write our prompt
        sys.stdout.write(prompt)
        sys.stdout.flush()
        if os.name == "nt":
            start_time = time.time()
            i = ""
            while True:
                if msvcrt.kbhit():
                    c = msvcrt.getche()
                    if ord(c) == 13:  # enter_key
                        break
                    elif ord(c) >= 32:  # space_char
                        i += c.decode("utf-8")
                if len(i) == 0 and (time.time() - start_time) > timeout:
                    break
        else:
            i, o, e = select.select([sys.stdin], [], [], timeout)
            if i:
                i = sys.stdin.readline().strip()
        print("")  # needed to move to next line
        if len(i) > 0:
            return i
        else:
            return default

    def cls(self):
        os.system("cls" if os.name == "nt" else "clear")

    # Header drawing method
    def head(self, text=None, width=55):
        if text == None:
            text = self.name
        self.cls()
        print("  {}".format("#" * width))
        mid_len = int(round(width / 2 - len(text) / 2) - 2)
        middle = " #{}{}{}#".format(" " * mid_len, text, " " * ((width - mid_len - len(text)) - 2))
        if len(middle) > width + 1:
            # Get the difference
            di = len(middle) - width
            # Add the padding for the ...#
            di += 3
            # Trim the string
            middle = middle[:-di] + "...#"
        print(middle)
        print("#" * width)

    def custom_quit(self):
        self.head()
        print("by DhinakG")
        print("with code from CorpNewt's USBMap\n")
        print("Thanks for testing it out!\n")
        # Get the time and wish them a good morning, afternoon, evening, and night
        hr = datetime.datetime.now().time().hour
        if hr > 3 and hr < 12:
            print("Have a nice morning!\n\n")
        elif hr >= 12 and hr < 17:
            print("Have a nice afternoon!\n\n")
        elif hr >= 17 and hr < 21:
            print("Have a nice evening!\n\n")
        else:
            print("Have a nice night!\n\n")
        exit(0)


def cls():
    os.system("cls" if os.name == "nt" else "clear")


def header(text, width=55):
    cls()
    print("  {}".format("#" * width))
    mid_len = int(round(width / 2 - len(text) / 2) - 2)
    middle = " #{}{}{}#".format(" " * mid_len, text, " " * ((width - mid_len - len(text)) - 2))
    if len(middle) > width + 1:
        # Get the difference
        di = len(middle) - width
        # Add the padding for the ...#
        di += 3
        # Trim the string
        middle = middle[:-di] + "...#"
    print(middle)
    print("#" * width)


class TUIMenu:
    EXIT_MENU = object()

    def __init__(
        self,
        title: str,
        prompt: str,
        return_number: bool = False,
        add_quit: bool = True,
        auto_number: bool = False,
        in_between: Optional[Union[list, Callable]] = None,
        top_level: bool = False,
        loop: bool = False,
    ):
        self.title = title
        self.prompt = prompt
        self.in_between = in_between or []
        self.options = []
        self.return_number = return_number
        self.auto_number = auto_number
        self.add_quit = add_quit
        self.top_level = top_level
        self.loop = loop
        self.add_quit = add_quit

        self.return_option = (["Q", "Quit"] if self.top_level else ["B", "Back"]) if self.add_quit else None

    def add_menu_option(self, name: Union[str, Callable], description: Optional[list[str]] = None, function: Optional[Callable] = None, key: Optional[str] = None):
        if not key and not self.auto_number:
            raise TypeError("Key must be specified if auto_number is false")
        self.options.append([key, name, description or [], function])

    def head(self):
        cls()
        header(self.title)
        print()

    def print_options(self):
        for index, option in enumerate(self.options):
            if self.auto_number:
                option[0] = str((index + 1))
            print(option[0] + ".  " + (option[1]() if callable(option[1]) else option[1]))
            for i in option[2]:
                print("    " + i)
        if self.add_quit:
            print(f"{self.return_option[0]}.  {self.return_option[1]}")
        print()

    def select(self):
        print(ansiescapes.cursorSavePosition, end="")
        print(ansiescapes.eraseDown, end="")
        selected = input(self.prompt)

        keys = [option[0].upper() for option in self.options]
        if self.add_quit:
            keys += [self.return_option[0]]

        while not selected or selected.upper() not in keys:
            nl_count = self.prompt.count("\n") + selected.count("\n") + 1
            selected = input(f"{nl_count * ansiescapes.cursorPrevLine}{ansiescapes.eraseDown}{self.prompt}")

        if self.add_quit and selected.upper() == self.return_option[0]:
            return self.EXIT_MENU
        elif self.return_number:
            return self.options[keys.index(selected.upper())][0]
        else:
            return self.options[keys.index(selected.upper())][3]() if self.options[keys.index(selected.upper())][3] else None

    def start(self):
        while True:
            self.head()

            if callable(self.in_between):
                self.in_between()
                print()
            elif self.in_between:
                for i in self.in_between:
                    print(i)
                print()

            self.print_options()

            result = self.select()

            if result is self.EXIT_MENU:
                return self.EXIT_MENU
            elif not self.loop:
                return result


class TUIOnlyPrint:
    def __init__(self, title, prompt, in_between=None):
        self.title = title
        self.prompt = prompt
        self.in_between = in_between or []

    def start(self):
        cls()
        header(self.title)
        print()

        if callable(self.in_between):
            self.in_between()
        else:
            for i in self.in_between:
                print(i)
            if self.in_between:
                print()

        return input(self.prompt)
