## XDLRC Generation 
```
usage: XDLRC.py [-h] [-x] [-t TILE | -p] SCHEMA DEVICE FAMILY [FILE]

Generate XLDRC file and check for accuracy

positional arguments:
  SCHEMA                Location of CapnProto Device Schema
  DEVICE                Interchange-CapnProto device representation
  FAMILY                The family of the part
  FILE                  Name of output XDLRC file

optional arguments:
  -h, --help            show this help message and exit
  -x, --extra           Generate XDLRC+ file
  -t TILE, --tile TILE  Generate XDLRC for a single tile
  -p, --prim-defs       Generate XDLRC for Primitive_Defs only
```

Note:
  * If FILE is not specified the default is partName.xdlrc, ie: xc7a100t.xdlrc

## XDLRC+
XDLRC+ contains everthing in the original XDLRC file, with additional key
words to denote more information.

| Key Words | Location | Description |
| --- | ----------- | ---------- |
| alternate_site_types | Right before the "tiles" declaration | Lists the alternate sites for the first site |
