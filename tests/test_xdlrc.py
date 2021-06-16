"""
Functions for comparing two XDLRC files.
Used to test DeviceResources.generate_xdlrc().  Generates and checks for
correctness an XDLRC file for xc7a100tcsg-1 part. Only declarations
contained in XDLRC_KEY_WORD are currently supported (case-insensitive).
If an unknown declaration is encountered, the line is skipped and a
warning is printed.
Note: CFG is recognized as a declaration, but not supported in XDLRC
generation so these lines are skipped without warning or error.
Wires not found in both interchange and ISE are checked against a JSON
database of Vivado wires. The following encoding shows where a wire can
be found:
    100 ISE
    010 Interchange
    001 Vivado
Naturally, this leads to encodings like 101 indicating that the wire is
found in ISE and Vivado but not interchange.
To be ran in the tests directory of the python-fpga-interchange project
with the command:
    $python test_xdlrc.py -m interchange
Differences that are deemed "acceptable" (see XDLRC.py comments) are
tracked separately from errors and stored in the text file
XDLRC_Exceptions.txt.
"""

from collections import namedtuple
import debugpy
import enum
import sys
import time
import json
from fpga_interchange.XDLRC import XDLRC
from fpga_interchange.interchange_capnp import Interchange, read_capnp_file

KeyWords = namedtuple('KeyWords', 'comment tiles tile wire conn summary pip site pinwire prim_defs prim_def element cfg pin header tile_summary')  # noqa

# Dictionary contains XDLRC declarations as keys and expected token length
# as values
XDLRC_KEY_WORD = {'#': 0, 'TILES': 3, 'TILE': 6, 'WIRE': 3, 'CONN': 6,
                  'TILE_SUMMARY': 6, 'PIP': 4, 'PRIMITIVE_SITE': 5,
                  'PINWIRE': 4, 'PRIMITIVE_DEFS': 2, 'PRIMITIVE_DEF': 3,
                  'ELEMENT': 3, 'CFG': 0, 'PIN': 4, 'XDL_RESOURCE_REPORT': 0,
                  'SUMMARY': 6}

XDLRC_UNSUPPORTED_WORDS = ['UNBONDED']

XDLRC_KEY_WORD_KEYS = KeyWords(comment='#', tiles='TILES', tile='TILE',
                               wire='WIRE', conn='CONN',
                               tile_summary='TILE_SUMMARY', pip='PIP',
                               site='PRIMITIVE_SITE', pinwire='PINWIRE',
                               prim_defs='PRIMITIVE_DEFS',
                               prim_def='PRIMITIVE_DEF', element='ELEMENT',
                               cfg='CFG', pin='PIN',
                               header='XDL_RESOURCE_REPORT', summary='SUMMARY')

TEST_XDLRC = 'xc7a100t.xdlrc'
CORRECT_XDLRC = '/home/reilly/work/xc7a100t.xdlrc'
# TODO: make these paths not hard-coded
SCHEMA_DIR = "/home/reilly/work/RapidWright/interchange/fpga-interchange-schema/interchange"  # noqa
DEVICE_FILE = "/home/reilly/work/xc7a100t.device"
VIVADO_WIRES = "/home/reilly/work/xc7a100tcsg324_wires.json"
VIVADO_NODELESS_WIRES = "/home/reilly/work/xc7a100tcsg324_nodeless_wires.json"
TCL_FILE_OUT = "WireArray.tcl"
TCL_F = None

def tcl_print(tcl):
    TCL_F.write(tcl)

vivado = {}
typeErr = {}

# global _errors
_errors = 0
unknowns = []




def err_print(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)


XDLRC_Exceptions = "XDLRC_Exceptions.txt"
XDLRC_Exceptions_f = None


def eprint(str_in):
    XDLRC_Exceptions_f.write(str_in + '\n')


def file_init(*argv):
    """
    Add line counting and get_line storage to file objects.
    Adds two members to file:
        line_num (int)  - Current line number
        line     (list) - Output of get_line()
    Note: get_line is called to initialize line.
    """

    for f in argv:
        f.line_num = 0
        f.line = []
    get_line(*argv)


def get_line(*argv):
    """
    Get the next eligible line in one or both XDLRC files.
    Strips beginning and end of line of '()\n\t ' characters.  Also
    checks the first word of each line to see if it is a supported XDLRC
    keyword. Uses two global variables - unknowns and lines. Lines is a
    dict that keeps track of line numbers for each file. Unknowns is a
    list of unrecognized XDLRC key words.
    Updates f.line_num to contain current line number.
    Updates f.line to contain the result
    Parameters:
        Any number of (XDLRC) file objects.
    """

    for f in argv:
        line = []
        while True:
            line = f.readline()
            if not line:
                # EOF is reached in this file. end of parse
                print(f"file reached EOF\n\n")
                if unknowns:
                    print(unknowns)
                break

            # keep track of line numbers
            f.line_num += 1

            line = line.strip("()\n\t ")
            if not line:
                continue
            line = line.upper().split()
            key_word = line[0]
            if key_word not in XDLRC_KEY_WORD_KEYS and key_word[0] != XDLRC_KEY_WORD_KEYS.comment:
                if line[0] not in unknowns:
                    print(f"Warning: Unknown Key word {line[0]}. Ignoring line"
                          + f" {f.line_num}")
                    print(line)
                    unknowns.append(line[0])
                continue

            elif key_word == XDLRC_KEY_WORD_KEYS.cfg:  # ignore cfg lines
                eprint(f"CFG_EXCEPTION triggered on line {f.line_num}")

            elif (key_word[0] != XDLRC_KEY_WORD_KEYS.comment and
                  key_word != XDLRC_KEY_WORD_KEYS.header):

                # Make sure token is appropriate length
                expected_len = XDLRC_KEY_WORD[line[0]]
                actual_len = len(line)
                if actual_len < expected_len:
                    line += ['BLANK'] * (expected_len - actual_len)
                break

        # f.line is updated specifically in this way (NOT with =) to
        # support shallow copies of f.line correctly being updated
        f.line.clear()
        f.line.extend(line)


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
        err_print(f"AssertionError caught.\nObj1:\n{obj1}\nObj2:\n{obj2}\n\n")
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


class TileStruct(namedtuple('TileStruct', 'name type wires pips sites')):
    """
    Lightweight class for holding XDLRC tile information.
    __eq__() is overridden for accurate comparison.  It is important to
    note that it assumes that "other" is correct.
    Members:
        name  (str)  - Tile name
        type  (str)  - Tile type
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
        Assumes other is always correct.
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
            err_print("Fatal Error: Tile names do not match. Abort compare.")
            err_print(f"Name1: {self.name} Name2: {other.name}\n\n")
            return False

        err_header = f"Tile: {self.name} Type: {self.type}"
        # compare wires
        keys = (set(self.wires.keys()), set(other.wires.keys()))
        common_wires = keys[0].intersection(keys[1])
        uncommon_wires = keys[0].symmetric_difference(keys[1])

        for wire in uncommon_wires:

            if wire in keys[0]:
                if f"{self.name}/{wire}" in vivado[self.name]['wires']:
                    eprint(
                        f"EXTRA_WIRE_EXCEPTION 011 {err_header} Wire: {wire}")
                else:
                    # Wire is not in Vivado or ISE
                    _errors += 1
                    if self.type not in typeErr.keys():
                        typeErr[self.type] = 1
                    else:
                        typeErr[self.type] += 1
                    err_print(f"{err_header} Extra wire 010 {wire}")
            else:
                if f"{self.name}/{wire}" not in vivado[self.name]['wires']:
                    eprint(
                        f"MISSING_WIRE_EXCEPTION 100 {err_header} Wire {wire}")
                else:
                    # Wire is in Vivado and ISE but not in interchange
                    # if f"{self.name}/{wire}" not in vivado_nodeless[self.name]['wires']:
                    #     tcl_print(f' "{self.name}/{wire}"')
                    #     _errors += 1
                    #     if self.type not in typeErr.keys():
                    #         typeErr[self.type] = 1
                    #     else:
                    #         typeErr[self.type] += 1
                    #     err_print(f"{err_header} Missing Wire 101: {wire}")
                    # else:

                    # TCL script was used to verify that all wires here fall under this category
                    eprint(f"NODELESS_WIRE_EXCEPTION 101 {err_header} Wire {wire}")

        for wire in common_wires:
            conns = self.wires[wire]
            other_conns = other.wires[wire]

            all_conns = (set(conns), set(other_conns))
            uncommon = all_conns[0].symmetric_difference(all_conns[1])

            for conn in uncommon:
                if f"{conn[0]}/{conn[1]}" in vivado[conn[0]]["wires"]:
                    if conn in all_conns[0]:
                        eprint(f"EXTRA_WIRE_EXCEPTION (Conn 011) {err_header} "
                               + "Wire: {wire} Conn: {conn}")
                    else:
                        _errors += 1
                        if self.type not in typeErr.keys():
                            typeErr[self.type] = 1
                        else:
                            typeErr[self.type] += 1
                            err_print(f"{err_header} Missing conn {conn} for "
                                      + "wire {wire} 101")
                else:
                    _errors += 1
                    if self.type not in typeErr.keys():
                        typeErr[self.type] = 1
                    else:
                        typeErr[self.type] += 1
                    if conn in all_conns[0]:
                        err_print(f"{err_header} Extra conn {conn} for wire "
                                  + "{wire} 010")
                    else:
                        err_print(f"{err_header} Missing conn {conn} for wire "
                                  + "{wire} 100")

        # compare pips
        keys = [set(self.pips.keys()), set(other.pips.keys())]
        common_pips = keys[0].intersection(keys[1])
        uncommon_pips = keys[0].symmetric_difference(keys[1])

        for wire_in in uncommon_pips:
            _errors += 1
            if wire_in in keys[0]:
                if self.type not in typeErr.keys():
                    typeErr[self.type] = 1
                else:
                    typeErr[self.type] += 1
                err_print(f"{err_header} Extra Pip {wire_in}")
            else:
                if self.type not in typeErr.keys():
                    typeErr[self.type] = 1
                else:
                    typeErr[self.type] += 1
                err_print(f"{err_header} Missing Pip {wire_in}")

        for wire_in in common_pips:
            wire_outs = self.pips[wire_in]
            other_wire_outs = other.pips[wire_in]

            wire_outs.sort()
            other_wire_outs.sort()

            if wire_outs != other_wire_outs:
                _errors += 1
                if self.type not in typeErr.keys():
                    typeErr[self.type] = 1
                else:
                    typeErr[self.type] += 1
                err_print(f"{err_header} Pip conn mismatch for {wire_in}")

        # compare primitive sites
        keys = [set(self.sites.keys()), set(other.sites.keys())]
        common_sites = keys[0].intersection(keys[1])
        uncommon_sites = keys[0].symmetric_difference(keys[1])

        for site in uncommon_sites:
            _errors += 1
            if site in keys[0]:
                if self.type not in typeErr.keys():
                    typeErr[self.type] = 1
                else:
                    typeErr[self.type] += 1
                err_print(f"{err_header} Extra Site {site}")
            else:
                if self.type not in typeErr.keys():
                    typeErr[self.type] = 1
                else:
                    typeErr[self.type] += 1
                err_print(f"{err_header} Missing Site {site}")

        for site in common_sites:
            pinwires = set(self.sites[site])
            other_pinwires = set(other.sites[site])

            for pw in pinwires.symmetric_difference(other_pinwires):
                _errors += 1
                if self.type not in typeErr.keys():
                    typeErr[self.type] = 1
                else:
                    typeErr[self.type] += 1
                err_print(f"{err_header} PinWire mismatch for {pw}")

        return tmp_err == _errors


def build_tile_db(f, tileName, typeStr):
    """
    Build a TileStruct of a tile by scanning XDLRC f.
    Breaks on tile_summary or on EOF.
    Parameters:
        f (file object) - file to scan for tile information
    Returns:
        tile - TileStruct representing the tile
    """

    tile = TileStruct(tileName, typeStr, {}, {}, {})
    err_header = f"Tile: {tileName} Type: {typeStr}"
    get_line(f)

    while f.line and f.line[0] != XDLRC_KEY_WORD_KEYS.tile_summary:
        if f.line[0] == XDLRC_KEY_WORD_KEYS.wire:

            wire = f.line[1]
            tile.wires[wire] = []
            conns = tile.wires[wire]

            get_line(f)
            while f.line and (f.line[0] == XDLRC_KEY_WORD_KEYS.conn):
                conns.append(tuple([f.line[1], f.line[2]]))
                get_line(f)

        elif f.line[0] == XDLRC_KEY_WORD_KEYS.pip:
            if f.line[2] not in tile.pips.keys():
                tile.pips[f.line[2]] = []
            tile.pips[f.line[2]].append(f.line[3])
            get_line(f)

        elif f.line[0] == XDLRC_KEY_WORD_KEYS.site:
            if f.line[3].upper() == XDLRC_UNSUPPORTED_WORDS[0]:
                eprint(
                    f"PKG_SPECIFIC_EXCEPTION  {err_header} line {f.line_num}:")
                f.line.remove(f.line[3])

            sites_key = f.line[1] + ' ' + f.line[2]
            tile.sites[sites_key] = []
            pin_wires = tile.sites[sites_key]

            get_line(f)
            while (f.line and
                   (f.line[0] == XDLRC_KEY_WORD_KEYS.pinwire)):

                direction = Direction.convert(f.line[2])
                pin_wires.append(
                    PinWire(f.line[1], direction, f.line[3]))
                get_line(f)
        else:
            err_print("Error: build_tile_db() hit default branch")
            err_print("This should not happen if XDLRC files are equal")
            err_print(f"Line {f.line_num}: {f.line}")
            sys.exit()

    return tile


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
    __eq__() is overridden for accurate comparison.  It is important to
    note that it is assumed that the "other" operand is correct.
    Members:
        name     (str)  - Name of Primitive Def
        pins     (dict) - Key: PinWire name (str)
                          Value: PinWire
        elements (dict) - Key: Element name (str)
                          Value: Element details (Element)
    """

    def __eq__(self, other):
        """
        Check two objects for equality.
        Assumes other is always correct.
        Fails immediately upon type mismatch.
        Fails immediately if PrimDef names differ, otherwise does NOT
        fail immediately upon equality violation.  Will check all
        elements and print out all errors found.  Increments global
        _error count.
        """
        if type(self) != type(other):
            return False

        if self.name != other.name:
            err_print("Fatal Error: Primitive Def name mismatch")
            err_print(f"Name1: {self.name} Name2: {other.name}")
            return False

        global _errors
        tmp_err = _errors

        # Check pins
        pins = set(self.pins.keys())
        other_pins = set(other.pins.keys())

        for pin in pins.symmetric_difference(other_pins):
            _errors += 1
            if pin not in pins:
                err_print(f"Prim_Def: {self.name} Extra Pin {self.pins[pin]}")
            else:
                err_print(
                    f"Prim_Def: {self.name} Missing Pin {other.pins[pin]}")

        for pin in pins.intersection(other_pins):
            if self.pins[pin] != other.pins[pin]:
                err_print(f"Prim_Def: {self.name} Pin Mismatch\n"
                          + f"\t{self.pins[pin]}\n\t{other.pins[pin]}")
        # Check elements
        keys = set(self.elements.keys())
        other_keys = set(other.elements.keys())

        for key in keys.symmetric_difference(other_keys):
            _errors += 1
            if key in self.elements.keys():
                err_print(f"Prim_Def {self.name} Extra Element {key}")
            else:
                err_print(f"Prim_Def {self.name} Missing Element {key}")

        for key in keys.intersection(other_keys):
            if self.elements[key] != other.elements[key]:
                _errors += 1
                err_print(f"Prim_Def {self.name} Element Mismatch\n"
                          + f"\t{self.elements[key]}\n\t{other.elements[key]}")

        return tmp_err == _errors


def build_prim_def_db(f, name):
    """
    Build a PrimDef by scanning f.
    Breaks on EOF or new Primitive_Def declaration.
    Parameters:
        f (file object) - file to scan for tile information
    Returns:
        prim_def - PrimDef object representing the primitive_def.
    """
    prim_def = PrimDef(name, {}, {})
    get_line(f)

    while (f.line and (f.line[0] != XDLRC_KEY_WORD_KEYS.prim_def)
           and f.line[0] != XDLRC_KEY_WORD_KEYS.summary):
        if f.line[0] == XDLRC_KEY_WORD_KEYS.pin:
            pin_wire = PinWire(f.line[1], Direction.convert(f.line[2]),
                               f.line[3])
            prim_def.pins[f.line[1]] = pin_wire
            get_line(f)
        elif f.line[0] == XDLRC_KEY_WORD_KEYS.element:
            if f.line[2] != '0':  # make sure there is more than just cfg
                element = Element(f.line[1], [], [])
                prim_def.elements[f.line[1]] = element
                element = prim_def.elements[f.line[1]]
                get_line(f)

                while f.line:
                    if f.line[0] == XDLRC_KEY_WORD_KEYS.pin:
                        element.pins.append(
                            PinWire(f.line[1],
                                    Direction.convert(f.line[2]), ''))
                        get_line(f)
                    elif f.line[0] == XDLRC_KEY_WORD_KEYS.conn:
                        if f.line[3] == '==>':
                            element.conns.append(Conn(f.line[1], f.line[2],
                                                      f.line[4], f.line[5]))
                        else:
                            element.conns.append(Conn(f.line[4], f.line[5],
                                                      f.line[1], f.line[2]))
                        get_line(f)
                    else:
                        break
            else:
                eprint(f"CFG_ELEMENT_EXCEPTION caught on line {f.line_num}")
                get_line(f)
        else:
            err_print(f"Error: build_prim_def_db hit default branch")
            err_print(f"Check syntax on line {f.line_num}")
            get_line(f)

    return prim_def


def compare_tile(f1, f2):
    """
    Parse and compare a single tile.
    Assumes file_init() has been executed for each file parameter.
    """

    # Check Tile Header
    assert_equal(f1.line, f2.line)

    tile1 = build_tile_db(f1, f1.line[3], f1.line[4])
    tile2 = build_tile_db(f2, f2.line[3], f2.line[4])

    # Check Tile contents
    # __eq__ is overridden so this line actually does stuff
    tile1 == tile2

    # Check Tile summary
    # This first check accounts for EXTRA_WIRE_EXCEPTION making the summay
    # wire count be off
    if f1.line[4] != f2.line[4]:
        eprint(f"EXTRA_WIRE_EXCEPTION line {f2.line_num}:"
               + f"{f1.line_num} summary wire count mismatch")
    else:
        assert_equal(f1.line, f2.line)

    get_line(f1, f2)


def compare_prim_defs(f1, f2):
    """
    Compare the primitive_defs.
    Assumes file_init() has been executed for each file parameter.
    """

    # Check primitive_defs declaration
    assert_equal(f1.line, f2.line)
    get_line(f1, f2)

    # Primitive_def checks
    while f1.line and f2.line and f1.line[0] != XDLRC_KEY_WORD_KEYS.summary:

        while f2.line[1] != f1.line[1]:  # Not all ISE prim defs represented
            eprint(f"PRIM_DEF_GENERAL_EXCEPTION caught on line {f2.line_num}."
                   + f"PRIMITIVE_DEF {f2.line[1]} missing.")
            get_line(f2)
            while f2.line[0] != XDLRC_KEY_WORD_KEYS.prim_def:
                get_line(f2)

        # Elements w/ only CFG bits are not supported, so comparing
        # element count will likely fail. So element cnt is dropped.
        if f2.line[3] != f1.line[3]:
            eprint(f"CFG_PRIM_DEF_EXCEPTION caught on line {f2.line_num}")
        f2.line = f2.line[:3]
        f1.line = f1.line[:3]

        assert_equal(f1.line, f2.line)

        prim_def1 = build_prim_def_db(f1, f1.line[1])
        prim_def2 = build_prim_def_db(f2, f2.line[1])

        # __eq__ is overridden so this actually does stuff
        prim_def1 == prim_def2


def compare_xdlrc(f1, f2):
    """
    Compare two xdlrc files for equality.
    Tiles must be listed in the same order. Primitive Def headers must
    be in the same order.  Everything else can be out of order.
    Assumes that file2 has been generated correctly and file1 is being
    checked against it for correctness.
    Assumes file_init() has been executed for each file parameter.
    """

    # check Tiles row_num col_num declaration
    assert_equal(f1.line, f2.line)

    # Tile chekcs
    get_line(f1, f2)
    while (f1.line and f2.line
           and (f1.line[0] != XDLRC_KEY_WORD_KEYS.prim_defs)):
        compare_tile(f1, f2)

    while (f2.line[0] != XDLRC_KEY_WORD_KEYS.prim_defs):
        get_line(f2)
    compare_prim_defs(f1, f2)

    # This will fail due to PRIM_DEF_GENERAL_EXCEPTION
    # TODO pin count is way off
    assert_equal(f1.line, f2.line)


def init(fileName=''):
    """
    Set up the environment for __main__.
    Also useful to run after an import for debugging/testing
    Parameters:
        fileName (str) - Name of file to pass to XDLRC constructor
    """

    device_schema = Interchange(SCHEMA_DIR).device_resources_schema.Device
    return XDLRC(read_capnp_file(device_schema, DEVICE_FILE), fileName)


def argparse_setup():
    """Setup argparse and return parsed arguements."""
    import argparse
    parser = argparse.ArgumentParser(
        description="Generate XLDRC file and check for accuracy")
    parser.add_argument("TEST_XDLRC", help="XDLRC file to test for accuracy",
                        nargs='?', default=TEST_XDLRC)
    parser.add_argument("CORRECT_XDLRC",
                        help="Correct XDLRC file to compare against",
                        nargs='?', default=CORRECT_XDLRC)
    parser.add_argument("dir", help="Directory where files are located",
                        nargs='?', default='')
    parser.add_argument("-e", help="Name of known exception file",
                        default=XDLRC_Exceptions)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-t", "--tile", help="Parse files as single tile",
                       action="store_true")
    group.add_argument("-p", "--prim-defs",
                       help="Parse files as primitive_defs only",
                       action="store_true")
    group.add_argument("--no-gen", help="Do not generate XDLRC file",
                       action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = argparse_setup()

    if not args.no_gen and not (args.tile or args.prim_defs):
        myDevice = init(args.dir+args.TEST_XDLRC)
        start = time.time()
        myDevice.generate_XDLRC()
        finish = time.time() - start
        print(f"XDLRC {args.dir+args.TEST_XDLRC} generated in {finish} sec ")

    if args.e:
        XDLRC_Exceptions = args.e

    XDLRC_Exceptions_f = open(XDLRC_Exceptions, "w")

    # TODO make this optional
    with open(VIVADO_WIRES, "r") as f:
        vivado = json.load(f)

    with open(VIVADO_NODELESS_WIRES, "r") as f:
        vivado_nodeless = json.load(f)

    with (open(args.dir+args.TEST_XDLRC, "r") as f1,
          open(args.dir+args.CORRECT_XDLRC, "r") as f2,
          open(XDLRC_Exceptions, "w") as f3,
          open(TCL_FILE_OUT, "w") as f4):

        XDLRC_Exceptions_f = f3
        eprint("Line numbers are expressed CORRECT_XDLRC:TEST_XDLRC")
        eprint("Some errors are not applicable to both files. These are "
               + "expressed with the appropriate side of the colon empty.")
        eprint("See XDLRC.py for further explanation of file contents\n\n\n")

        
        TCL_F = f4
        tcl_print('array set testWires {')

        file_init(f1, f2)

        start = time.time()

        if args.tile:
            compare_tile(f1, f2)
        elif args.prim_defs:
            compare_prim_defs(f1, f2)
        else:
            compare_xdlrc(f1, f2)

        finish = time.time() - start
        print(f"XDLRC compared in {finish} seconds")

        tcl_print("}\n")

    err_print(f"Done comparing XDLRC files. Errors: {_errors}")
    print(f"Done comparing XDLRC files. Errors: {_errors}")
    print(typeErr)
