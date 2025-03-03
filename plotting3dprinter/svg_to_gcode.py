import xml.etree.ElementTree as et
from .svg_interpreter import svg_to_coordinate_chomper, repart, svg_to_segment_blocks
from .raycaster import cast_rays
import matplotlib.pyplot as plt
import matplotlib
from copy import copy
import numpy as np

def get_optimal_scaler(bed_size_x:int,bed_size_y:int,im_length_x:int, im_length_y:int, longest_edge:float, scale_factor:float):
    X = bed_size_x
    Y = bed_size_y
    a = im_length_x
    b = im_length_y
    if ((X/Y)-1)*((a/b)-1) >= 0: # if the aspect ratio of the image and the print bed are similar...
        S = np.linspace(0,1,10000)
        dfds = np.array([-2*a*(X-s*a) - 2*b*(Y-s*b) for s in S]) # obtained from the derivative of f(s) = ((X - a*s)^2 + (Y - b*s)^2) where s is the scaler
        condition = np.array([(Y - s*b) >= 0 and (X - s*a) >= 0 for s in S])
        scaler_idx = np.argmin(np.abs(dfds)[condition])
        scaler = S[scaler_idx]
    else:
        scale_x = longest_edge/im_length_x
        scale_y = longest_edge/im_length_y
        scaler = min(scale_x,scale_y)
    return scaler * scale_factor

def get_pass_list(z_surface:float, z_bottom:float, passes:int) -> list:
    return np.linspace(z_surface,z_bottom,passes).tolist()

def get_optimal_ordering(blockset):
    remaining_blocks = copy(blockset)
    i = 0

    current_block = remaining_blocks.pop()
    yield current_block[-1]

    while len(remaining_blocks)>0:
        # find nearest block
        if len(remaining_blocks)==0:
            return
        end = current_block[-1][-1][1]

        best = None
        best_dist = None
        best_idx = None

        for j,rblock in enumerate(remaining_blocks):

            (xstart,ystart) = rblock[-1][0][0]

            dist = np.sqrt( np.power(xstart-end[0],2) +
                           np.power(ystart-end[1],2))
            #print(dist)
            if best is None or dist<best_dist:
                best = rblock
                best_dist=dist
                best_idx=j

        print('next best block is ',best_idx, best_dist )
        current_block = best

        yield best[-1]
        remaining_blocks.pop(best_idx)

def svg_to_gcode(svg_path,
                gcode_path,
                precision=10,
                xy_feedrate = 4600,
                z_feedrate = 250,
                x_offset = 50,
                y_offset = 50,
                z_surface = 5,
                z_up = 7,
                z_safe = 20, # the z-coordinate of the CNC tool where it is well-above the surface
                cut_depth = 0,
                create_outline=True,
                create_fill=False,
                min_fill_segment_size=2, # Don't fill with lines shorter than this value
                longest_edge = None, # Rescale longest edge to this value
                bed_size_x=250,
                bed_size_y=200,
                verbose=False,
                passes=1, # number of passes (relevant for cutting material)
                scale_factor=1,
                 drill_on=False,
 ):
    assert cut_depth >= 0, 'The cut depth must be a positive value [mm] (or 0 in the case of drawing).'
    z_bottom = z_surface - cut_depth

    assert z_surface < z_up, 'The z-coordinate of the drawing/cutting surface must be below the safe travel height of the CNC tool.'
    assert z_safe >= z_up, 'The safe height of the CNC tool must be higher than the height at which the tool moves over the surface.'

    if z_bottom == z_surface:
        assert passes == 1, 'You only need to do 1 pass with the CNC tool since the bottom z-coordinate is equal to the surface z-coordinate.'
    else:
        assert passes > 1, 'You should set passes to a value greater than 1 since the bottom z-coordinate is lower than the surface coordinate.'

    cmdcolor = {
        'L':'r',
        'l':'r',
        'M':'k',
        'V':'b',
        'v':'b',
        'H':'b',
        'h':'b'

    }

    tree = et.parse(svg_path)
    # Add namespace for svg
    ns = {'sn': 'http://www.w3.org/2000/svg'}
    # get root element
    root = tree.getroot()

    # Find coordinate extends, for rescaling
    max_x = None
    min_x = None
    max_y = None
    min_y = None

    for i,path in enumerate(root.findall('.//sn:path', ns)):
        # Parse thew path in d:
        d  = path.attrib['d'].replace(',', ' ')
        parts = d.split()

        #coordinates = np.array(list(
    #        map(list, list( svg_to_coordinate_chomper(
    #        inp=repart(parts), PRECISION=precision) ))
#        ))

        coordinates = []
        commands = []
        for t in svg_to_coordinate_chomper(
            inp=repart(parts), PRECISION=precision, verbose=verbose):
            #print(t)
            (x,y),c = t

            coordinates.append([x,y])
            commands.append(c)

        #coordinates = [ [x,y]  for (x,y),c in  svg_to_coordinate_chomper(
    #        inp=repart(parts), PRECISION=precision)]
        coordinates = np.array(coordinates)

        print(coordinates)

        bot = np.nanmin( coordinates[:,0])
        if min_x is None or bot<min_x:
            min_x = bot

        top = np.nanmax( coordinates[:,0])
        if max_x is None or top>max_x:
            max_x = top


        bot = np.nanmin( coordinates[:,1])
        if min_y is None or bot<min_y:
            min_y = bot

        top = np.nanmax( coordinates[:,1])
        if max_y is None or top>max_y:
            max_y = top

    # perform scaling such that the longest edge < longest_edge mm
    if longest_edge is not None:
        scaler = get_optimal_scaler(bed_size_x,bed_size_y,max_x - min_x, max_y - min_y, longest_edge, scale_factor)

    fig, ax = plt.subplots()


    pathcolors = plt.get_cmap('tab10')
    with open(gcode_path,'w') as o:

        # Move pen up:
        o.write(f'G01 Z{z_safe} F{z_feedrate}\n') # Perform up
        o.write('G28 X0 Y0\n') # perform home
        o.write(f'G01 Z{z_up} F{z_feedrate}\n') # Perform up

        if drill_on:
          o.write(f'M04 S700\n')

        # loop over passes
        pass_list = get_pass_list(z_surface, z_bottom, passes)
        for z_pass in pass_list:

            segment_blocks = list( svg_to_segment_blocks(svg_path) )
            prev=None
            # Determine block, start and ends
            blockset = []
            for block in segment_blocks:
                blockset.append([block[0][0], block[-1][1], block])

            if create_outline:
                prev = None
                for block in get_optimal_ordering(blockset):
                    for ii,( (x1,y1),(x2,y2) ) in enumerate( block ):

                        if longest_edge is not None:
                            x1-=min_x
                            x2-=min_x
                            y1-=min_y
                            y2-=min_y
                            # Convert video coordinates to xy coordinates (flip y)
                            y1 = (max_y-min_y)-(y1)
                            y2 = (max_y-min_y)-(y2)
                            # Scale
                            x1*=scaler
                            x2*=scaler
                            y1*=scaler
                            y2*=scaler

                        # clip the coordinates to prevent negative values
                        x1, y1, x2, y2 = np.clip(x1, 0, None), np.clip(y1, 0, None), np.clip(x2, 0, None), np.clip(y2, 0, None)

                        if x1>bed_size_x or y1>bed_size_y or x2>bed_size_x or y2>bed_size_y:
                            raise ValueError(f'Coordinates generated which fall outside of supplied printer bed size, adjust printer bed size or add "-longest_edge {min(bed_size_x,bed_size_y)}" to the command to scale the coordinates')

                        if prev is None or prev!=(x1,y1):
                            # Perform travel move:
                            print('traveling ...', (x1,y1))
                            if prev is not None:
                                # go up first
                                o.write(f'G01 X{x_offset+prev[0]:.2f} Y{y_offset+prev[1]:.2f} Z{z_up} F{z_feedrate}\n')
                                plt.plot([prev[0],x1],[prev[1],y2],c='grey')
                            o.write(f'G01 X{x_offset+x1:.2f} Y{y_offset+y1:.2f} Z{z_up} F{xy_feedrate}\n')
                            # Drop pen down at current position
                            o.write(f'G01 X{x_offset+x1:.2f} Y{y_offset+y1:.2f} Z{z_pass} F{z_feedrate}\n')

                        #if prev!=(x1,y1):
                        #    print(x1,y1)

                        o.write(f'G01 X{x_offset+x1:.2f} Y{y_offset+y1:.2f} Z{z_pass} F{xy_feedrate}\n')
                        #print(x2,y2)
                        o.write(f'G01 X{x_offset+x2:.2f} Y{y_offset+y2:.2f} Z{z_pass} F{xy_feedrate}\n')

                        plt.plot([x1,x2],[y1,y2],c='r')
                        prev = (x2,y2)

            # block ended.. travel
            o.write(f'G01 X{x_offset+x2:.2f} Y{y_offset+y2:.2f} Z{z_up} F{z_feedrate}\n')

        o.write(f'G01 Z{z_safe} F{xy_feedrate}\n')
        o.write(f'M05\n')
        o.write(f'G28 X0 Y0') # go back to home position

        #plt.plot( coordinates[:,0],  coordinates[:,1])

        print('All done')
        plt.xlim(-bed_size_x * 0.1, 1.1 * bed_size_x)
        plt.ylim(-bed_size_y * 0.1, 1.1 * bed_size_y)

        plt.axvline(0,c='r',ls=':')
        plt.axvline(bed_size_x,c='r',ls=':')
        plt.axvline(bed_size_x-x_offset,c='r',ls=':')

        plt.axhline(0,c='r',ls=':')
        plt.axhline(bed_size_y,c='r',ls=':')
        plt.axhline(bed_size_y-y_offset,c='r',ls=':')

        # set aspect ratio of the figure to be based on the bed size x and bed size y
        plt.gca().set_aspect('equal', adjustable='box')

        plt.savefig(f'{gcode_path.replace(".gcode","")}.png', dpi=300)