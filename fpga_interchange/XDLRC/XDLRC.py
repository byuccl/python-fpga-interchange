"""
Code to generate XDLRC files based on the information provided in
RapidWright interchange DeviceResources capnp device representations.
Contains class XDLRC, which extends the DeviceResources class found in
this repository's device_resource.py.  This class uses the Python
DeviceResources object in conjunction with the Python capnproto object
to generate the information found in an ISE XDLRC file of a device.
The XDLRC generator will print out the tile and primitive_def
declarations in the same order as ISE; however the internal declarations
for these data types are not the same order.
There are some differences between the ISE file and XDLRC file produced
by this code.  They are outlined below:

CARRY4_EXCEPTION: On SLICELs and SLICEMs there are elements in addition
to the CARRY4, like CARRY4_XOR, that are not listed in ISE.

CFG_EXCEPTION: From what we can tell, there is no way to pull the cfg
declarations from the interchange representation.  This means that they
simply just are not generated in these XDLRC files.

CFG_ELEMENT_EXCEPTION: Some elements only have CFG bits declared inside
them.  These elements also are not found in interchange.

CFG_PRIM_DEF_EXCEPTION: Since some elements do not show up, the element
count is often off for a primitive_def.

CIN_PRECYINIT_EXCEPTION: In SLICEL and SLICEM, ISE does not document the
connection between the CIN pinwire and the PRECYINIT MUX.

EXTRA_INTERCHANGE_PIP_EXCEPTION: Sometimes a pip appears where one of
the wires is documented by interchange and Vivado but not ISE.  However,
neither ISE or Vivado mention the pip.

EXTRA_PIP_EXCEPTION: Sometimes interchange has pips not in ISE.  These
pips are found in Vivado.

EXTRA_WIRE_EXCEPTION: For some reason, interchange has wire information
for tiles that is not included in ISE.  This wire information can be
found in Vivado 2020.  The earliest occurance for this is tile
TERM_CMT_X8Y208.  Interchange includes information on 4 wires that
connect to this tile for part xc7a100t.  ISE's XDLRC for xc7a100tcsg-1
does not show any wires for this tile, and there is no conn statement
for a wire connecting to this tile in the rest of the XDLRC.
This also extends to wire conn statements.  Naturally the "extra" wires
are found in the conns of other matching wires.  These are tagged as the
same exception.  These wires can also be found in pips and likewise are
tagged with the same exception.

MISSING_WIRE_EXCEPTION: Sometimes ISE prints out wires for a tile that
are not currently represented in Vivado.  These instances are marked
appropriately.

PKG_SPECIFIC_EXCEPTION: Sometimes primitive_defs are classified as
'unbonded' because their IOBs are not connected on the package that ISE
generated an XDLRC file for.  This code does not generate a package
specific XDLRC file; only part specific.  Interchange does contain
package specific information, but we are not integrating that at this
point.  Therefore, this specifal identifier is not included.

NODELESS_WIRE_EXCEPTION: Wire conns are generated by examining the
interchange wire-node list.  Some wires do not have nodes, but in ISE
they do have conns.  Even though these wires are found in Vivado and
interchange, in Vivado and interchange there are not associated nodes,
so the conns cannot be properly generated.

PRIM_DEF_GENERAL_EXCEPTION: Not all primitive_defs generated by ISE are
included in the interchange representation.  One example for the
xc7a100t part is the AMS_ADC, which shows up in ISE's XDLRC for
xc7a100tcsg-1.  It seems that ISE prints the primitive_defs for all
7-series parts, regardless of if they are used on the specific chip.

ROUTETHROUGH_EXCEPTION: So far we do not see a way to generate the
information for _ROUTETHROUGH keywords on pips. This also means that
_ROUTETHROUGH PrimDef elements are not included.

"""

from fpga_interchange.interchange_capnp import Interchange, read_capnp_file
from fpga_interchange.device_resources import DeviceResources, convert_direction
from fpga_interchange.logical_netlist import Direction


class DummyFile():
    """Fake file"""
    def write(*args, **kwargs):
        return

    def close(*args, **kwargs):
        return


class XDLRC(DeviceResources):
    """
    Class for generating XDLRC files from Interchange device resources.
    This class contains the main/helper routines associated with
    generating a XDLRC file.  Creating an instance of the class
    automatically will generate the XDLRC file.
    Constructor Parameters:
    device_rep (DeviceResources)
    file_name (String) - filename for xdlrc file (.xdlrc extension will
                         be appended).
                         Default: device_resource_capnp.name
    """

    def __sort_tile_cols__(tile):
        """
        Helper function for sort.

        NOT designed for use outside of being a key function for sort().
        Helps sort() sort the tiles based on col number

        NOTE: self is purposely not included as the first arguement.
        """
        return tile.col

    def __init__(self, device_resource, fileName='', family="artix7"):
        """
        Initialize the XDLRC object.
        Parameters:
            device_resource - Object to obtain device information from.
                              Can be instance of DeviceResources or
                              interchange_capnp.read_capnp_file() output
            fileName (str)  - Name of file to create/write to.  Can be
                              none for no file operations.
        """

        if type(device_resource) is DeviceResources:
            # TODO test this feature
            self.__dict__ = device_resource.__dict__.copy()
        else:
            super().__init__(device_resource)

        self.tiles = []
        tiles_by_row = [[]]
        for tile in self.device_resource_capnp.tileList:
            # Create a list of lists of tiles by row
            if len(tiles_by_row) <= tile.row:
                for i in range(tile.row - len(tiles_by_row)):
                    tiles_by_row.append([])
                tiles_by_row.append([tile])
            else:
                tiles_by_row[tile.row].append(tile)

        # sort each row list by column and then attach to master tile list
        for tile_row in tiles_by_row:
            tile_row.sort(key=XDLRC.__sort_tile_cols__)
            self.tiles += tile_row

        # set up file to write to
        if fileName is not None:
            if fileName == '':
                fileName = self.device_resource_capnp.name + ".xdlrc"
            self.xdlrc = open(fileName, "w+")
        else:
            self.xdlrc = DummyFile()

        # set family
        self.family = family

    def close_file(self):
        self.xdlrc.close()

    def generate_alt_site_types(self):
        for site in self.device_resource_capnp.siteTypeList:
            if len(site.altSiteTypes) != 0:
                self.xdlrc.write(
                    f"(alternate_site_types {self.strs[site.name]}")
                for alt in site.altSiteTypes:
                    name = self.device_resource_capnp.siteTypeList[alt].name
                    self.xdlrc.write(f" {self.strs[name]}")
                self.xdlrc.write(f")\n")

    def _generate_tile(self, tile):
        """
        The heavy lifting for generating xdlrc for a tile.

        Returns a tuple(num_sites, num_pips)
        """

        # Some pointers for abbreviated reference
        raw_repr = self.device_resource_capnp
        xdlrc = self.xdlrc

        tile_name = self.strs[tile.name]

        tile_type = self.get_tile_type(tile.type)
        tile_type_r = raw_repr.tileTypeList[tile_type.tile_type_index]
        wires = tile_type.wires
        pips = tile_type.pips
        num_sites = len(tile.sites)
        xdlrc.write(f"\t(tile {tile.row} {tile.col} {tile_name} "
                    + f"{tile_type.name} {num_sites}\n")

        num_wires = 0
        num_pips = len(pips)
        num_pinwires = 0

        pin_tile_wires = set()

        # PRIMITIVE_SITE declaration
        for site in tile.sites:
            site_name = self.strs[site.name]
            site_type_in_tile_type = tile_type_r.siteTypes[site.type]
            site_type_r_idx = site_type_in_tile_type.primaryType
            site_type_r = raw_repr.siteTypeList[site_type_r_idx]
            site_t_name = self.strs[site_type_r.name]
            site = self.site_name_to_site[site_name][site_t_name]

            site_t = self.get_site_type(site.site_type_index)
            # bond = ""
            # if (("IOB" in site_t_name) or ("IPAD" == site_t_name) or
            #         "OPAD" == site_t_name):
            #     bond = "unkown "
            bond = "unknown "  # just mark all sites as unkown for now
            xdlrc.write(f"\t\t(primitive_site {site_name} {site_t_name} "
                        + f"{bond}{len(site_t.site_pins.keys())}\n")

            # PINWIRE declaration
            # site_pin to tile_wire list
            site_to_tile = site_type_in_tile_type.primaryPinsToTileWires
            for idx, pin in enumerate(site_type_r.pins):
                pin_name = self.strs[pin.name]
                tile_wire = self.strs[site_to_tile[idx]]
                pin = site_t.site_pins[pin_name]
                direction = pin[3].name.lower()
                num_pinwires += 1
                pin_tile_wires.add(tile_wire)
                xdlrc.write(f"\t\t\t(pinwire {pin_name} {direction} "
                            + f"{tile_wire})\n")
            xdlrc.write(f"\t\t)\n")

        # WIRE declaration
        tile_wires = set()
        for idx in tile_type.string_index_to_wire_id_in_tile_type.keys():
            wire_name = self.strs[idx]
            try:
                node_idx = self.node(tile_name, wire_name).node_index
            except AssertionError as e:
                continue
            myNode = raw_repr.nodes[node_idx]

            num_wires += 1
            tile_wires.add(wire_name)
            xdlrc.write(f"\t\t(wire {wire_name} {len(myNode.wires) -1}")

            if len(myNode.wires) == 1:  # no CONNs
                xdlrc.write(')\n')
                continue
            else:
                xdlrc.write('\n')

            # CONN declaration
            for w in myNode.wires:
                wire = raw_repr.wires[w]
                conn_tile = self.strs[wire.tile]
                conn_wire = self.strs[wire.wire]

                if (conn_wire != wire_name) or (conn_tile != tile_name):
                    xdlrc.write(f"\t\t\t(conn {conn_tile} {conn_wire})\n")

            xdlrc.write(f"\t\t)\n")

        for wire in (pin_tile_wires - tile_wires):
            num_wires += 1
            xdlrc.write(f"\t\t(wire {wire} {0})\n")

        # PIP declaration
        for p in pips:
            if p.directional:
                xdlrc.write(f"\t\t(pip {tile_name} {self.strs[wires[p.wire0]]}"
                            + f" -> {self.strs[wires[p.wire1]]})\n")
            else:
                xdlrc.write(f"\t\t(pip {tile_name} {self.strs[wires[p.wire0]]}"
                            + f" =- {self.strs[wires[p.wire1]]})\n")
                xdlrc.write(f"\t\t(pip {tile_name} {self.strs[wires[p.wire1]]}"
                            + f" =- {self.strs[wires[p.wire0]]})\n")

        # TILE_SUMMARY declaration
        xdlrc.write(f"\t\t(tile_summary {tile_name} {tile_type.name} ")
        xdlrc.write(f"{num_pinwires} {num_wires} {num_pips})\n")
        xdlrc.write(f"\t)\n")
        return (num_sites, num_pips, num_pinwires)

    def generate_tile(self, tile_name):
        """
        Generate a single tile representation for tile_name (str).

        Returns a tuple(num_sites, num_pips)
        """
        for tile in self.tiles:
            name = self.strs[tile.name]
            if name == tile_name:
                return self._generate_tile(tile)

    def generate_prim_defs(self):
        """Generate the primitive_defs."""
        # some pointers for abbreviated reference
        raw_repr = self.device_resource_capnp
        xdlrc = self.xdlrc

        # PRIMITIVE_DEFS declaration
        xdlrc.write(f" (primitive_defs {len(raw_repr.siteTypeList)}\n")

        # PRIMITIVE_DEF declarations
        # Semantics to ensure primitive_defs are added alphabetically
        site_types = {}
        for idx in range(len(raw_repr.siteTypeList)):
            site_t = self.get_site_type(idx)
            site_types[site_t.site_type] = site_t

        site_type_names = list(site_types.keys())
        site_type_names.sort()

        for i in site_type_names:
            site_t = site_types[i]
            # TODO Symbiflow added this to the python SiteType class
            site_t_r = raw_repr.siteTypeList[site_t.site_type_index]
            site_wires = site_t_r.siteWires

            xdlrc.write(f"\t(primitive_def {site_t.site_type} "
                        + f"{len(site_t.site_pins)} {len(site_t.bels)}\n")
            # PIN declaration
            for pin_name, pin in site_t.site_pins.items():
                direction = pin[3].name.lower()
                xdlrc.write(
                    f"\t\t(pin {pin_name} {pin_name} {direction})\n")

            # ELEMENT declaration
            for bel in site_t.bels:
                xdlrc.write(f"\t\t(element {bel.name} {len(bel.bel_pins)}\n")

                # 1 is the enum for routing
                add_cfg = [] if (bel.category == 1) else None

                # TODO Symbiflow adjusted bel pin representation in SiteType
                for bel_pin in bel.bel_pins:
                    # PIN declaration
                    bel_pin_index = site_t.bel_pin_index[bel_pin]
                    bel_pin_name = bel_pin_index[1]
                    bel_info = site_t.bel_pins[bel_pin_index]
                    direction = bel_info[2].name.lower()
                    if direction == 'inout' or direction == 'input':
                        xdlrc.write(f"\t\t\t(pin {bel_pin_name} input)\n")
                        if add_cfg is not None:
                            add_cfg.append(bel_pin_name)
                    else:
                        xdlrc.write(f"\t\t\t(pin {bel_pin_name} output)\n")

                    # CONN declaration
                    site_wire_index = bel_info[1]

                    if site_wire_index is None:
                        # sometimes an element pin has no conn statements
                        continue

                    if direction == 'input':
                        direction_str = '<=='
                    elif direction == 'inout':
                        direction = ''
                    else:
                        direction_str = '==>'

                    for pin_idx in site_wires[site_wire_index].pins:
                        bel_pin2_r = site_t_r.belPins[pin_idx]
                        bel2_name = self.strs[bel_pin2_r.bel]
                        if bel2_name != bel.name:
                            bel_pin2_name = self.strs[bel_pin2_r.name]
                            direction2 = convert_direction(
                                bel_pin2_r.dir).name.lower()
                            if not direction:
                                if direction2 == 'input':
                                    xdlrc.write(f"\t\t\t(conn {bel.name} "
                                                + f"{bel_pin_name} ==> "
                                                + f"{bel2_name} "
                                                + f"{bel_pin2_name})\n")
                                elif direction2 == 'inout':
                                    xdlrc.write(f"\t\t\t(conn {bel.name} "
                                                + f"{bel_pin_name} <== "
                                                + f"{bel2_name} "
                                                + f"{bel_pin2_name})\n")
                                    xdlrc.write(f"\t\t\t(conn {bel.name} "
                                                + f"{bel_pin_name} ==> "
                                                + f"{bel2_name} "
                                                + f"{bel_pin2_name})\n")
                                else:
                                    xdlrc.write(f"\t\t\t(conn {bel.name} "
                                                + f"{bel_pin_name} <== "
                                                + f"{bel2_name} "
                                                + f"{bel_pin2_name})\n")
                            elif direction2 != direction:
                                xdlrc.write(f"\t\t\t(conn {bel.name} "
                                            + f"{bel_pin_name} "
                                            + f"{direction_str} {bel2_name}"
                                            + f" {bel_pin2_name})\n")
                if add_cfg is not None:
                    xdlrc.write(
                        f"\t\t\t(cfg {' '.join(e for e in add_cfg)})\n")
                xdlrc.write(f"\t\t)\n")
            xdlrc.write(f"\t)\n")
        xdlrc.write(f")\n")

    def generate_XDLRC(self):
        """
        UNDER CONSTRUCTION
        Generate an XDLRC file based on the DeviceResources Device.
        """

        # HEADER
        self.xdlrc.write(f"(xdl_resource_report v0.2 "
                         + f"{self.device_resource_capnp.name} {self.family}\n")

        # TILES declaration
        num_rows = self.tiles[-1].row + 1
        num_cols = self.tiles[-1].col + 1
        self.xdlrc.write(f"(tiles {num_rows} {num_cols}\n")

        # TILE declarations
        num_sites = 0
        num_pips = 0
        num_pins = 0
        for tile in self.tiles:
            tmp_sites, tmp_pips, tmp_pins = self._generate_tile(tile)
            num_sites += tmp_sites
            num_pips += tmp_pips
            num_pins += tmp_pins

        self.xdlrc.write(")\n")

        # PRIMITIVE_DEFS
        self.generate_prim_defs()

        # SUMMARY
        self.xdlrc.write(f"(summary tiles={len(self.tiles)} sites={num_sites} "
                         + f"sitedefs={len(self.site_types)} "
                         + f"numpins={num_pins} numpips={num_pips})\n)")
        # cleanup
        self.close_file()

    def generate_XDLRC_PLUS(self):
        # HEADER
        self.xdlrc.write(f"(xdl_resource_report v0.2 "
                         + f"{self.device_resource_capnp.name} {self.family}\n")

        # ALTERNATE_SITE_TYPES
        self.generate_alt_site_types()

        # TILES declaration
        num_rows = self.tiles[-1].row + 1
        num_cols = self.tiles[-1].col + 1
        self.xdlrc.write(f"(tiles {num_rows} {num_cols}\n")

        # TILE declarations
        num_sites = 0
        num_pips = 0
        for tile in self.tiles:
            tmp_sites, tmp_pips = self._generate_tile(tile)
            num_sites += tmp_sites
            num_pips += tmp_pips

        self.xdlrc.write(")\n")

        # PRIMITIVE_DEFS
        num_pins = self.generate_prim_defs()

        # SUMMARY
        self.xdlrc.write(f"(summary tiles={len(self.tiles)} sites={num_sites} "
                         + f"sitedefs={len(self.site_types)} "
                         + f"numpins={num_pins} numpips={num_pips})\n)")
        # cleanup
        self.close_file()


def argparse_setup():
    """Setup argparse and return parsed arguements."""
    import argparse
    parser = argparse.ArgumentParser(
        description="Generate XLDRC file and check for accuracy")
    parser.add_argument("SCHEMA", help="Location of CapnProto Device Schema")
    parser.add_argument("DEVICE",
                        help="Interchange-CapnProto device representation")
    parser.add_argument("FAMILY", help="The family of the part")
    parser.add_argument("FILE", help="Name of output XDLRC file",
                        nargs='?', default="")
    parser.add_argument("-x", "--extra", help="Generate XDLRC+ file",
                        action="store_true")
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "-t", "--tile", help="Generate XDLRC for a single tile")
    group.add_argument("-p", "--prim-defs",
                       help="Generate XDLRC for Primitive_Defs only", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = argparse_setup()

    device_schema = Interchange(args.SCHEMA).device_resources_schema.Device
    device = XDLRC(read_capnp_file(device_schema, args.DEVICE), args.FILE)

    if args.tile:
        device.generate_tile(args.tile)
        device.close_file()
    elif args.prim_defs:
        device.generate_prim_defs()
        device.close_file()
    elif args.extra:
        device.generate_XDLRC_PLUS()
    else:
        device.generate_XDLRC()
