# Requires valid Vivado project for part xc7a100tcsg324-1 with synthesis and
# implementation runs completed.

# project location goes here
open_project {C:/Users/reill/OneDrive - BYU/Documents/PhD/XDLRC/ExamplePrjXC7A100T/project_1/project_1.xpr}
# name of completed implementation run goes here
open_run impl_1

# source the array of wires output from test_xdlrc
source WireArray.tcl

proc tile_wires_to_json {file_name inputArray} { 
    set f [open $file_name w]
    set tile_list [get_tiles]
    set tile_count [llength $tile_list]
	set k 0
    for {set i 0} {$i < $tile_count} {incr i} { 
        set T [lindex $tile_list $i]
        set wire_list [get_wires -of_objects $T]
        set wire_count [llength $wire_list]
        for {set j 0} {$j < $wire_count} {incr j} { 
            set wire [lindex $wire_list $j]
			if {$wire == [lindex $inputArray $k]} {
				incr k
				set node [get_nodes -of_objects $wire]
				if {[llength $node] != 0} {
                    # wires that do have a node will be printed to the file
                    # if the run is successful, the file should be empty
					if { $j==[expr {$wire_count-1} ]} {
						puts $f "\"$wire\""
					} else {
						puts $f "\"$wire\","
					}
				}
			}
        }        
    }
    close $f
}

tile_wires_to_json "wire_check_results" testWires