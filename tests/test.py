'''
Temporary test file for new functionality

This code is meant to quickly setup the test environment and is designed
to by used with 'from tests.test import *'
'''

from fpga_interchange.interchange_capnp import Interchange, read_capnp_file

SCHEMA_DIR = "/home/reilly/RW/RapidWright/interchange"

TEST_DEVICE_FILE = "/home/reilly/RW/RapidWright/xc7a100t.device"

myDevice = Interchange(SCHEMA_DIR).read_device_resources(TEST_DEVICE_FILE)
myDevice.generate_XDLRC()
# tile_raw = myDevice.tiles[4]
# tile_name = myDevice.strs[tile_raw.name]
# tile_type = myDevice.get_tile_type(tile_raw.type)

# print(myDevice.tile_name_to_tile[tile_name])
# for i in tile_type.string_index_to_wire_id_in_tile_type.keys():
#     if myDevice.strs[i] == 'T_TERM_UTURN_INT_ER1BEG_S0':
#         wire_idx = i

# wire_name = myDevice.strs[wire_idx]
# wire_id_in_tile = tile_type.string_index_to_wire_id_in_tile_type[wire_idx]
# n = myDevice.node(tile_name, wire_name)
# myNode = myDevice.device_resource_capnp.nodes[n.node_index]
# for w in myNode.wires:
#     wire1 = myDevice.device_resource_capnp.wires[w]
#     print(myDevice.strs[wire1.tile] + ' ' + myDevice.strs[wire1.wire])
