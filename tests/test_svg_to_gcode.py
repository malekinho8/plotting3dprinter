import os
import sys; sys.path.append(os.getcwd())
from plotting3dprinter.svg_to_gcode import svg_to_gcode

def test_svg_to_gcode():
    svg_path = os.path.join('examples','mustang','mustang(1).svg') # "examples\\square\\square.svg"
    gcode_path = os.path.join('examples','mustang','mustang(1).gcode')
    svg_to_gcode(svg_path, gcode_path, xy_feedrate=750, z_feedrate=250, x_offset=0, y_offset=0, bed_size_x=8, bed_size_y=8, longest_edge=8, verbose=True, z_up=0, z_surface=-1, cut_depth=5, passes=4, z_safe=0, scale_factor=0.3)

test_svg_to_gcode()