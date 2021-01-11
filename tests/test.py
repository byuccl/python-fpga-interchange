'''
Temporary test file for new functionality

This code is meant to quickly setup the test environment and is designed
to by used with 'from test import *'
'''

from fpga_interchange.interchange_capnp import Interchange, read_capnp_file

SCHEMA_DIR = "/home/reilly/RW/RapidWright/interchange"

TEST_DEVICE_FILE = "/home/reilly/RW/RapidWright/xc7a100t.device"

myDevice = Interchange(SCHEMA_DIR).read_device_resources(TEST_DEVICE_FILE)

print(myDevice.tile_name_to_tile['T_TERM_INT_X4Y208'])
tile = myDevice.get_tile_type(74)
print(tile.string_index_to_wire_id_in_tile_type)
myDevice.strs[3554]
