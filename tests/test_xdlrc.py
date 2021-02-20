"""
Functions for comparing two XDLRC files.

Used to test DeviceResources.generate_xdlrc().  Generates and checks for
correctness an XDLRC file for xc7a100tcsg-1 part. Only declarations
contained in XDLRC_KEY_WORD are currently supported (case-insensitive).
If an unknown declaration is encountered, the line is skipped and a
warning is printed.

Note: CFG is recognized as a declaration, but not supported in XDLRC
generation so these lines are skipped without warning or error.

To be ran in the tests directory of the python-fpga-interchange project
with the command:
    $python test_xdlrc.py -m interchange
"""

import enum
import os
import sys
import debugpy
import time
from collections import namedtuple

KeyWords = namedtuple(
    'KeyWords', 'comment tiles tile wire conn summary pip site pinwire prim_defs prim_def element cfg pin')  # noqa

# Dictionary contains XDLRC declarations as keys and expected token length
# as values
XDLRC_KEY_WORD = {'#': 0, 'TILES': 3, 'TILE': 6, 'WIRE': 3, 'CONN': 6,
                  'TILE_SUMMARY': 6, 'PIP': 4, 'PRIMITIVE_SITE': 5,
                  'PINWIRE': 4, 'PRIMITIVE_DEFS': 2, 'PRIMITIVE_DEF': 3,
                  'ELEMENT': 3, 'CFG': 0, 'PIN': 4}

XDLRC_KEY_WORD_KEYS = KeyWords(comment='#', tiles='TILES', tile='TILE',
                               wire='WIRE', conn='CONN',
                               summary='TILE_SUMMARY', pip='PIP',
                               site='PRIMITIVE_SITE', pinwire='PINWIRE',
                               prim_defs='PRIMITIVE_DEFS',
                               prim_def='PRIMITIVE_DEF', element='ELEMENT',
                               cfg='CFG', pin='PIN')

# TODO change these paths so they are not hard coded
TEST_XDLRC = 'xc7a100t.xdlrc'
CORRECT_XDLRC = '/home/reilly/xc7a100t.xdlrc'
# CORRECT_XDLRC = '/home/reilly/partial.xdlrc'
SCHEMA_DIR = "/home/reilly/RapidWright/interchange"
DEVICE_FILE = "/home/reilly/xc7a100t.device"

_errors = 0
unknowns = []


def get_line(*argv):
    """
    Get the next eligible line in one or both XDLRC files.

    Strips beginning and end of line of '()\n\t ' characters.  Also
    checks the first word of each line to see if it is a supported XDLRC
    keyword. Uses two global variables - unknowns and lines. Lines is a
    dict that keeps track of line numbers for each file. Unknowns is a
    list of unrecognized XDLRC key words.

    Parameters:
        Any number of (XDLRC) file objects.

    Return Values:
        [] (list) - A list of words in the next valid line.  If multiple
        files are provided as input, returns a list of lists.  If EOF is
        reached then an empty list is returned.
    """

    ret = []
    for f in argv:
        line = []
        while True:
            line = f.readline()
            if not line:
                # EOF is reached in this file. end of parse
                print(f"file reached EOF\n\n")
                print(unknowns)
                break

            # keep track of line numbers
            if "line" not in dir(f):
                f.line = 0
            f.line += 1

            line = line.strip("()\n\t ")
            if not line:
                continue
            line = line.upper().split()
            key_word = line[0]
            if key_word not in XDLRC_KEY_WORD_KEYS:
                if line[0] not in unknowns:
                    print(f"Warning: Unknown Key word {line[0]}. Ignoring line"
                          + f" {f.line}")
                    print(line)
                    unknowns.append(line[0])
                continue
            elif (key_word[0] != XDLRC_KEY_WORD_KEYS.comment and
                  key_word != XDLRC_KEY_WORD_KEYS.cfg):  # CFG not supported
                # Make sure token is appropriate length
                if len(line) < XDLRC_KEY_WORD[line[0]]:
                    line += ['BLANK'] * XDLRC_KEY_WORD[line[0]]
                break

        ret.append(line)
    if len(ret) == 1:
        return ret[0]
    else:
        return ret


def assert_equal(obj1, obj2):
    """
    Run assert for equality on two objects.
    Catches AssertionError and prints it. Returns a bool of (obj1 == obj2)
    """

    try:
        assert obj1 == obj2
    except AssertionError as e:
        global _errors
        _errors += 1
        print(f"AssertionError caught.\nObj1:\n{obj1}\n\nObj2:\n{obj2}\n\n")
        return False
    return True


class Direction(enum.Enum):
    """ Enumeration for direction values. """
    Input = 0
    Output = 1
    Inout = 2

    def convert(input_str):
        input_str = input_str.upper()
        if input_str == 'INPUT':
            return Direction.Input
        elif input_str == 'OUTPUT':
            return Direction.Output
        elif input_str == 'INOUT':
            return Direction.Inout
        else:
            return None


class PinWire(namedtuple('PinWire', 'name direction wire')):
    """
    Lightweight class for holding XDLRC pinwire information.

    __eq__() has been overridden for accurate comparisons.
    __hash__() is overridden so PinWire can be in a set.

    Members:
        name  (str)       - Name of the pin.
        direction (Direction) - Direction of the pin.
        wire      (str)       - Name of the connecting wire.
    """

    def __hash__(self):
        return hash(tuple([self.name, self.direction, self.wire]))

    def __eq__(self, other):
        if type(other) != type(self):
            return False
        return ((self.name == other.name)
                and (self.direction == other.direction)
                and (self.wire == other.wire))


class TileStruct(namedtuple('TileStruct', 'name wires pips sites')):
    """
    Lightweight class for holding XDLRC tile information.

    __eq__() is overridden for accurate comparison

    Members:
        name  (str)  - Tile name
        wires (dict) - Key: Wire Name (str)
                       Value: Associated conns (list of tuples)
        pips  (dict) - Key: Input Wire Name (str)
                       Value: Output Wire names (list of str)
        sites (dict) - Key: Site Name + ' ' + Site Type (str)
                       Value: PinWires (list of PinWire)
    """

    def __eq__(self, other):
        """
        Check two objects for equality.

        Fails immediately upon type mismatch.
        Fails immediately if tile names differ, otherwise does NOT fail
        immediately upon equality violation.  Will check all elements
        and print out all errors found.  Increments global _error count.
        """

        global _errors
        tmp_err = _errors

        if type(other) != type(self):
            return False

        if self.name != other.name:
            print("Fatal Error: Tile names do not match. Abort compare.")
            print(f"Name1: {self.name} Name2: {other.name}\n\n")
            return False

        # compare wires
        keys = [set(self.wires.keys()), set(other.wires.keys())]
        common_wires = keys[0].intersection(keys[1])
        uncommon_wires = keys[0].symmetric_difference(keys[1])

        for wire in uncommon_wires:
            _errors += 1
            print(f"Tile: {self.name} Wire {wire} missing.")

        for wire in common_wires:
            conns = self.wires[wire]
            other_conns = other.wires[wire]

            conns.sort()
            other_conns.sort()

            if conns != other_conns:
                _errors += 1
                print(f"Tile: {self.name} Wire conns mismatch for {wire}")

        # compare pips
        keys = [set(self.pips.keys()), set(other.pips.keys())]
        common_pips = keys[0].intersection(keys[1])
        uncommon_pips = keys[0].symmetric_difference(keys[1])

        for wire_in in uncommon_pips:
            _errors += 1
            print(f"Tile: {self.name} Pip {wire_in} missing.")

        for wire_in in common_pips:
            wire_outs = self.pips[wire_in]
            other_wire_outs = other.pips[wire_in]

            wire_outs.sort()
            other_wire_outs.sort()

            if wire_outs != other_wire_outs:
                _errors += 1
                print(f"Tile: {self.name} "
                      + f"Pip connection mismatch for {wire_in}")

        # compare primitive sites
        keys = [set(self.sites.keys()), set(other.sites.keys())]
        common_sites = keys[0].intersection(keys[1])
        uncommon_sites = keys[0].symmetric_difference(keys[1])

        for site in uncommon_sites:
            _errors += 1
            print(f"Tile: {self.name} Site missing {site}")

        for site in common_sites:
            pinwires = set(self.sites[site])
            other_pinwires = set(other.sites[site])

            for pw in pinwires.symmetric_difference(other_pinwires):
                _errors += 1
                print(f"Tile: {self.name} PinWire mismatch for {pw}")

        return tmp_err == _errors


def build_tile_db(myFile, tileName):
    """
    Build a TileStruct of a tile by scanning XDLRC myFile.

    Breaks on tile_summary or on EOF.
    Parameters:
        myFile (file object) - file to scan for tile information

    Returns:
        (tile, last_line) - Tuple of TileStruct representing the tile
                            and a list containing the contents of the
                            last line parsed (empty for EOF or with
                            tile_summary)
    """

    tile = TileStruct(tileName, {}, {}, {})
    line = get_line(myFile)
    while line and line[0] != XDLRC_KEY_WORD_KEYS.summary:
        if line[0] == XDLRC_KEY_WORD_KEYS.wire:
            wire = line[1]
            tile.wires[wire] = []
            conns = tile.wires[wire]

            line = get_line(myFile)
            while line and (line[0] == XDLRC_KEY_WORD_KEYS.conn):
                conns.append(tuple([line[1], line[2]]))
                line = get_line(myFile)

        elif line[0] == XDLRC_KEY_WORD_KEYS.pip:
            if line[1] not in tile.pips.keys():
                tile.pips[line[1]] = []
            tile.pips[line[1]].append(line[3])
            line = get_line(myFile)

        elif line[0] == XDLRC_KEY_WORD_KEYS.site:
            sites_key = line[1] + ' ' + line[2]
            tile.sites[sites_key] = []
            pin_wires = tile.sites[sites_key]

            line = get_line(myFile)
            while line and (line[0] == XDLRC_KEY_WORD_KEYS.pinwire):
                direction = Direction.convert(line[2])
                pin_wires.append(PinWire(line[1], direction, line[3]))
                line = get_line(myFile)
        else:
            print("Error: build_tile_db() hit default branch")
            print("This should not happen if XDLRC files are equal")
            print(f"Line {myFile.line}:")
            print(line)
            sys.exit()

    return (tile, line)


class Conn(namedtuple('Conn', 'bel1 belpin1 bel2 belpin2')):
    """
    Lightweight class for holding XDLRC conn information.

    __eq__() is overridden for accruate comparison

    Members:
        bel1    (str) - Name of the INPUT Bel
        belpin1 (str) - Name of the INPUT Bel pin
        bel2    (str) - Name of the OUTPUT Bel
        belpin2 (str) - Name of the OUTPUT Bel pin
    """

    def __eq__(self, other):
        if type(self) != type(other):
            return False

        return ((self.bel1 == other.bel1)
                and (self.bel2 == other.bel2)
                and (self.belpin1 == other.belpin1)
                and (self.belpin2 == other.belpin2))


class Element(namedtuple('Element', 'name pins conns')):
    """
    Lightweight class for holding XDLRC element information.

    __eq__() is overridden for accruate comparison

    Members:
        name  (str)  - Element name
        pins  (list) - List of Element pins (PinWire)
        conns (list) - List of Element conns (Conn)
    """

    def __eq__(self, other):
        if type(self) != type(other):
            return False
        if self.name != other.name:
            return False

        if len(self.pins) != len(other.pins):
            return False
        if len(self.conns) != len(other.conns):
            return False

        for pin in self.pins:
            if pin not in other.pins:
                return False
        for conn in self.conns:
            if conn not in other.conns:
                return False

        return True


class PrimDef(namedtuple('PrimDef', 'name pins elements')):
    """
    Lightweight class for holding XDLRC primitive def information.

    __eq__() is overridden for accurate comparison.

    Members:
        name     (str)  - Name of Primitive Def
        pins     (list) - List of PinWires
        elements (dict) - Key: Element name (str)
                          Value: Element details (Element)
    """

    def __eq__(self, other):
        """
        Check two objects for equality.

        Fails immediately upon type mismatch.
        Fails immediately if PrimDef names differ, otherwise does NOT
        fail immediately upon equality violation.  Will check all
        elements and print out all errors found.  Increments global
        _error count.
        """
        if type(self) != type(other):
            return False

        if self.name != other.name:
            print("Fatal Error: Primitive Def name mismatch")
            print(f"Name1: {self.name} Name2: {other.name}")
            return False

        global _errors
        tmp_err = _errors

        # Check pins
        pins = set(self.pins)
        other_pins = set(other.pins)

        for pin in pins.symmetric_difference(other_pins):
            _errors += 1
            print(f"Prim_Def: {self.name} Pin Mismatch {pin}")

        # Check elements
        keys = set(self.elements.keys())
        other_keys = set(other.elements.keys())

        for key in keys.symmetric_difference(other_keys):
            _errors += 1
            print(f"Prim_Def {self.name} Element Missing {key}")

        for key in keys.intersection(other_keys):
            if self.elements[key] != other.elements[key]:
                _errors += 1
                print(f"Prim_Def {self.name} Element Mismatch "
                      + f"{self.elements[key]} {other.elements[key]}")

        return tmp_err == _errors


def build_prim_def_db(myFile, name):
    """
    Build a PrimDef by scanning myFile.

    Breaks on EOF or new Primitive_Def declaration.

    Parameters:
        myFile (file object) - file to scan for tile information

    Returns:
        (prim_def, last_line) - Tuple of PrimDef representing the
                                primitive_def and a list containing the
                                contents of the last line parsed (empty
                                for EOF or next primitive_def)
    """
    prim_def = PrimDef(name, [], {})
    line = get_line(myFile)

    while line and (line[0] != XDLRC_KEY_WORD_KEYS.prim_def):
        if line[0] == XDLRC_KEY_WORD_KEYS.pin:
            prim_def.pins.append(PinWire(line[1], Direction.convert(line[2]),
                                         line[3]))
            line = get_line(myFile)
        elif line[0] == XDLRC_KEY_WORD_KEYS.element:
            if line[2] != '0':  # make sure there is more than just cfg
                prim_def.elements[line[1]] = Element(line[1], [], [])
                element = prim_def.elements[line[1]]
                line = get_line(myFile)

                while line:
                    if line[0] == XDLRC_KEY_WORD_KEYS.pin:
                        element.pins.append(
                            PinWire(line[1], Direction.convert(line[2]), ''))
                        line = get_line(myFile)
                    elif line[0] == XDLRC_KEY_WORD_KEYS.conn:
                        if line[3] == '==>':
                            element.conns.append(
                                Conn(line[1], line[2], line[4], line[5]))
                        else:
                            element.conns.append(
                                Conn(line[4], line[5], line[1], line[2]))
                        line = get_line(myFile)
                    else:
                        break
            else:
                line = get_line(myFile)
        else:
            print("Error: build_prim_def_db hit default branch")
            line = get_line(myFile)

    return (prim_def, line)


def compare_xdlrc(file1, file2):
    """
    Compare two xdlrc files for equality.

    Tiles must be listed in the same order. Primitive Def headers must
    be in the same order.  Everything else can be out of order.
    Assumes that file2 has been generated correctly and file1 is being
    checked against it for correctness.
    """
    with open(file1, "r") as f1, open(file2, "r") as f2:
        line1 = [None]
        line2 = [None]
        global _errors
        _errors = 0

        line1, line2 = get_line(f1, f2)
        # # check Tiles row_num col_num declaration
        assert_equal(line1, line2)

        # Tile chekcs
        line1, line2 = get_line(f1, f2)
        while line1 and line2 and (line1[0] != XDLRC_KEY_WORD_KEYS.prim_defs):
            # Check Tile Header
            assert_equal(line1, line2)

            tile1, line1 = build_tile_db(f1, line1[3])
            tile2, line2 = build_tile_db(f2, line2[3])

            # Check Tile contents
            # __eq__ is overridden so this line actually does stuff
            tile1 == tile2

            # Check Tile summary
            assert_equal(line1, line2)
            line1, line2 = get_line(f1, f2)

        # Check primitive_defs declaration
        assert_equal(line1, line2)
        line1, line2 = get_line(f1, f2)

        # Primitive_def checks
        while line1 and line2:
            # Elements w/ only CFG bits are not supported, so comparing
            # element count will likely fail. So element cnt is dropped.
            line1 = line1[:3]
            while line2[1] != line1[1]:  # skip PrimDefs that are not supported
                line2 = get_line(f2)
            line2 = line2[:3]

            assert_equal(line1, line2)

            prim_def1, line1 = build_prim_def_db(f1, line1[1])
            prim_def2, line2 = build_prim_def_db(f2, line2[1])

            # __eq__ is overridden so this actually does stuff
            prim_def1 == prim_def2

    print(f"Done comparing XDLRC files. Errors: {_errors}")


def init():
    """
    Set up the environment for __main__.
    Also useful to run after an import for debugging/testing
    """
    import os

    PACKAGE_PARENT = '..'
    SCRIPT_DIR = os.path.dirname(os.path.realpath(
        os.path.join(os.getcwd(), os.path.expanduser(__file__))))
    sys.path.append(os.path.normpath(os.path.join(SCRIPT_DIR, PACKAGE_PARENT)))

    from fpga_interchange.XDLRC import XDLRC
    from fpga_interchange.interchange_capnp import Interchange, read_capnp_file

    device_schema = Interchange(SCHEMA_DIR).device_resources_schema.Device
    return XDLRC(read_capnp_file(device_schema, DEVICE_FILE),
                 TEST_XDLRC.replace(".xdlrc", ''))


if __name__ == "__main__":

    start = time.time()
    myDevice = init()
    finish = time.time() - start
    print(f"XDLRC generated in {finish} seconds")

    start = time.time()
    compare_xdlrc(TEST_XDLRC, CORRECT_XDLRC)
    finish = time.time() - start
    print(f"XDLRC compared in {finish} seconds")
