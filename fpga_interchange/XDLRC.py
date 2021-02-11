from .device_resources import DeviceResources


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

    def __init__(self, device_resource, fileName=''):
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

        self.generate_XDLRC(fileName)

    def generate_XDLRC(self, fileName=''):
        """
        UNDER CONSTRUCTION
        Generate an XDLRC file based on the DeviceResources Device.

        fileName (String) - filename for xdlrc file (.xdlrc extension
            will be appended). Default: self.device_resource_capnp.name
        """

        # "Pointer" to raw capnp device resource data (reduce typing)
        raw_repr = self.device_resource_capnp

        if fileName == '':
            fileName = raw_repr.name

        fileName = fileName + '.xdlrc'

        xdlrc = open(fileName, "w+")

        # TILES declaration
        num_rows = self.tiles[-1].row + 1
        num_cols = self.tiles[-1].col + 1
        xdlrc.write(f"(tiles {num_rows} {num_cols}\n")

        # TILE declaration
        for tile in self.tiles:
            tile_name = self.strs[tile.name]

            tile_type = self.get_tile_type(tile.type)
            wires = tile_type.wires
            pips = tile_type.pips
            xdlrc.write(f"\t(tile {tile.row} {tile.col} {tile_name} "
                        + f"{tile_type.name} {len(tile.sites)}\n")

            num_wires = len(wires)
            num_pips = len(pips)
            num_primitive_sites = len(tile.sites)

            # PRIMITIVE_SITE declaration
            for site in tile.sites:
                site_name = self.strs[site.name]
                site_t_infos = self.site_name_to_site[
                    site_name]

                for site_t_name, site in site_t_infos.items():
                    site_t = self.get_site_type(site.site_type_index)
                    xdlrc.write(f"\t\t(primitive_site {site_name} "
                                + f"{site_t_name} "
                                + f"{len(site_t.site_pins.keys())}\n")

                    # PINWIRE declaration
                    for idx, pin in enumerate(site_t.site_pins.items()):
                        try:
                            pin_wire = self.get_site_pin(site, idx).wire_name
                        except IndexError as e:
                            # TODO investigate
                            if 'BRAM' not in tile_name:
                                print("Error pin idx out of bounds.")
                                print(f"tile_name {tile_name} Site {site}")
                        pin_name = pin[0]  # key value is pin_name
                        pin = pin[1]  # value is pin data
                        direction = pin[3].name.lower()
                        xdlrc.write(f"\t\t\t(pinwire {pin_name} "
                                    + f"{direction} {pin_wire})\n")
                    xdlrc.write(f"\t\t)\n")

            # WIRE declaration
            for idx in tile_type.string_index_to_wire_id_in_tile_type.keys():  # noqa
                wire_name = self.strs[idx]
                try:
                    node_idx = self.node(tile_name, wire_name).node_index
                except AssertionError as e:
                    num_wires -= 1
                    continue
                myNode = raw_repr.nodes[node_idx]
                xdlrc.write(
                    f"\t\t(wire {wire_name} {len(myNode.wires) -1}\n")

                # CONN declaration
                for w in myNode.wires:
                    wire = raw_repr.wires[w]
                    conn_tile = self.strs[wire.tile]
                    conn_wire = self.strs[wire.wire]

                    if conn_wire != wire_name:
                        xdlrc.write(
                            f"\t\t\t(conn {conn_tile} {conn_wire})\n")

                xdlrc.write(f"\t\t)\n")

            # PIP declaration
            for p in pips:
                xdlrc.write(
                    f"\t\t(pip {tile_name} {self.strs[wires[p.wire0]]} ->"
                    + f" {self.strs[wires[p.wire1]]})\n")

            # TILE_SUMMARY declaration
            xdlrc.write(f"\t\t(tile_summary {tile_name} {tile_type.name} ")
            xdlrc.write(f"{num_primitive_sites} {num_wires} {num_pips})\n")
            xdlrc.write(f"\t)\n")

        # PRIMITIVE_DEFS declaration
        # TODO calculate total # primitive defs
        xdlrc.write(f")\n (primitive_defs {''}\n")

        # PRIMITIVE_DEF declaration
        # Semantics to ensure primitive_defs are added alphabetically
        site_types = {}
        for idx in range(len(raw_repr.siteTypeList)):
            site_t = self.get_site_type(idx)
            site_types[site_t.site_type] = site_t

        site_type_names = list(site_types.keys()).sort()

        for i in site_type_names:
            site_t = site_types[i]
            site_t_raw = raw_repr.siteTypeList[site_t.site_type_index]
            site_wires = site_t_raw.siteWires

            # PIN declaration
            for pin_name, pin in site_t.site_pins.items():
                direction = pin[3].name.lower()
                # TODO make sure pin_name == wire_name
                xdlrc.write(
                    f"\t\t(pin {pin_name} {pin_name} {direction})\n")

            # ELEMENT declaration
            for bel in site_t.bels:
                xdlrc.write(f"\t\t(element {bel.name} {len(bel.bel_pins)}\n")
                for bel_pin in bel.bel_pins:
                    # PIN declaration
                    bel_pin_index = site_t.bel_pin_index[bel_pin]
                    bel_pin_name = bel_pin_index[1]
                    bel_info = site_t.bel_pins[bel_pin_index]
                    direction = bel_info[2].name.lower()
                    xdlrc.write(
                        f"\t\t\t(pin {bel_pin_name} {direction})\n")

                    # CONN declaration
                    site_wire_index = bel_info[1]
                    for bel_pin2 in site_wires[site_wire_index].pins:
                        if bel_pin2[0] != bel.name:
                            bel2_name = bel_pin2[0]
                            bel_pin2_name = bel_pin2[1]

                            direction = bel_info[2]
                            direction_str = ''
                            if direction == Direction.Input:
                                direction_str = '<=='
                            elif direction == Direction.Output:
                                direction_str = '==>'

                            xdlrc.write(f"\t\t\t(conn {bel.name} "
                                        + f"{bel_pin_name} "
                                        + f"{direction_str} {bel2_name}"
                                        + f" {bel_pin2_name})\n")
