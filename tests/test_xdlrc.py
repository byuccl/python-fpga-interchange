"""
Functions for comparing two XDLRC files.

Used to test the output of DeviceResources.generate_xdlrc()
Tiles are expected to be in the same order in both files.  Everything
else can be out of order.  Only XDLRC_KEY_WORD declarations supported.
"""

XDLRC_KEY_WORD = ['#', 'tiles', 'tile', 'wire', 'conn', 'tile_summary']


def get_line(*argv):
    """
    Get the next eligible line in one or both XDLRC files.

    Strips beginning and end of line of '()\n\t ' characters.  Also
    checks the first word of each line to see if it is a supported XDLRC
    keyword.

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
            line = f.readline().strip("()\n\t ").lower()
            if not line:
                line = []
                break
            line = line.split()
            if line[0] not in XDLRC_KEY_WORD:
                print(f"Warning: Unknown Key word {line[0]}. Ignoring line.")
            elif line[0][0] != '#':
                break
        ret.append(line)
    if len(ret) == 1:
        return ret[0]
    else:
        return ret


def build_tile_db(myFile):
    """
    Build a list of all wires in the tile and a dictionary of all the
    conns for each wire.

    Scans myFile for wire and conn statements. Breaks on tile_summary or
    on EOF.
    Parameters:
        myFile (file object) - file to scan for wires and conns

    Returns:
        [[], {}, []] - List containing 1) a list of wires, 2) a
        dictionary where tile wires are keys and values are a list of
        tuples of the (tile, wire) for the corresponding conns, 3) the
        last output of get_line() (tile_summary or empty for EOF)
    """

    wires = []
    conns = {}
    line = get_line(myFile)
    while line and line[0] != 'tile_summary':
        if line[0] == 'wire':
            wires.append(line[1])
            conns[line[1]] = []
            line = get_line(myFile)
            while line and line[0] != 'wire' and line[0] != 'tile_summary':
                conns[wires[-1]].append(tuple([line[1], line[2]]))
                line = get_line(myFile)
    return [wires, conns, line]


def compare_xdlrc(file1, file2):
    with open(file1, "r") as f1, open(file2, "r") as f2:
        line1 = [None]
        line2 = [None]
        while line1 and line2:
            line1, line2 = get_line(f1, f2)
            assert line1 == line2  # check tile row_num col_num declaration

            line1, line2 = get_line(f1, f2)
            assert line1 == line2  # check tile declaration

            wires1, conns1, line1 = build_tile_db(f1)
            wires2, conns2, line2 = build_tile_db(f2)

            wires1.sort()
            wires2.sort()

            assert wires1 == wires2

            for w1, w2 in zip(wires1, wires2):
                c1 = conns1[w1].sort()
                c2 = conns2[w2].sort()
                assert c1 == c2
            assert line1 == line2

        print(f"file {'1' if not line1 else ''} {'2' if not line2 else ''}"
              + f" reached EOF")
