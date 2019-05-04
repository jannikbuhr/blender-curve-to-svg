bl_info = {
    'name': "Export 2D Curve to SVG",
    'author': "Aryel Mota Góis",
    'version': (0, 0, 1),
    'blender': (2, 77, 0),
    'location': "Properties > Data > Export SVG",
    'description': "Generate a SVG file from selected 2D Curves",
    'warning': "Curve splines may be inverted, so self intersections can be wrong after export",
    'wiki_url': "https://github.com/aryelgois/blender-curve-to-svg",
    'tracker_url': "https://github.com/aryelgois/blender-curve-to-svg/issues",
    'category': "Import-Export"}


import bpy
from xml.etree import ElementTree
from xml.dom import minidom # for prettify()


class CurveExportSVGPanel(bpy.types.Panel):
    """Creates a Panel in the data context of the properties editor"""
    bl_label = "Export SVG"
    bl_idname = 'DATA_PT_exportsvg'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = 'data'

    def draw(self, context):
        show = 0
        for obj in context.selected_objects:
            if obj.type == 'CURVE' and obj.data.dimensions == '2D':
                show += 1
            else:
                show -= 1

        scene = context.scene
        layout = self.layout
        if show > 0:
            row = layout.row()
            row.prop(scene, 'export_svg_minify')

            row = layout.row()
            row.prop(scene, 'export_svg_precision')

            row = layout.row()
            row.prop(scene, 'export_svg_output', text="")

            row = layout.row()
            row.operator('curve.export_svg', text="Export")
        else:
            layout.label(text="Must select only 2D Curve")

    @classmethod
    def poll(cls, context):
        return context.object.type == 'CURVE'


class DATA_OT_CurveExportSVG(bpy.types.Operator):
    """Generates a SVG file from selected 2D Curves"""
    bl_label = "Export SVG"
    bl_idname = 'curve.export_svg'

    # guide https://css-tricks.com/svg-path-syntax-illustrated-guide/
    # will be used: M L C S Z
    commands = {
        'moveto':     "M {x},{y}",
        'lineto':     "L {x},{y}",
       #'lineto_h':   "H {x}",
       #'lineto_v':   "V {y}",
        'curveto':    "C {h1x},{h1y} {h2x},{h2y} {x},{y}",       # h = handle_point
        'curveto_s':  "S {h2x},{h2y} {x},{y}",                   # mirror handle from previous C or S
       #'curveto_q':  "Q {hx},{hy} {x},{y}",                     # both handles in same position
       #'curveto_qs': "T {x},{y}",                               # mirror handle from previous Q or T
       #'arc':        "A {rx},{ry} {rot} {arc} {sweep} {x},{y}", # arc, sweep -> 0 or 1. it's to choose between four possibilities of arc
        'closepath':  "Z"}

    #handle_type = {'AUTO', 'ALIGNED', 'VECTOR', 'FREE'}

    def execute(self, context):
        scene = context.scene

        svg = ElementTree.Element('svg')
        svg.set('xmlns', "http://www.w3.org/2000/svg")
        svg.set('version', "1.1")
        svg.append(ElementTree.Comment("Generated by export_svg.py v{} for Blender".format('.'.join(str(x) for x in (bl_info['version'])))))

        svg_g = ElementTree.SubElement(svg, 'g')
        svg_g.set('transform', "scale(1 -1)") # the Y axis is inverted
        box = [0, 0, 0, 0]

        for obj in context.selected_objects:
            if obj.type != 'CURVE' or obj.data.dimensions != '2D':
                continue
            origin = obj.location.to_2d().to_tuple(scene.export_svg_precision)
            paths = {}
            for spline in obj.data.splines:
                id_ = spline.material_index
                d = []
                prev = []
                ## TODO
                #if spline.bezier_points:
                #    pass
                #elif spline.points:
                #    pass # use command lineto
                #else:
                #    pass # can not make path
                ##
                for point in spline.bezier_points: # TODO: fix when points are in inverted order (problem: some paths do union instead of difference)
                    d.append(self.command_calc(scene, obj, spline, point, origin, d, prev, box))
                if spline.use_cyclic_u:
                    d.append(self.command_calc(scene, obj, spline, spline.bezier_points[0], origin, d, prev, box))
                    d.append(self.commands['closepath'])
                if id_ in paths:
                    paths[id_].attrib['d'] += ' ' + ' '.join(d)
                else:
                    paths[id_] = ElementTree.SubElement(svg_g, 'path')
                    paths[id_].set('id', obj.name)
                    paths[id_].set('transform', "translate({} {})".format(*origin))
                    if obj.data.materials and obj.data.materials[id_] is not None:
                        paths[id_].set('style', "fill: {};".format(self.col_to_hex(obj.data.materials[id_].diffuse_color)))
                    paths[id_].set('d', ' '.join(d))

        svg.set('viewBox', ' '.join(str(x) for x in (box[0], -box[3], box[2] - box[0], box[3] - box[1])))
        if scene.export_svg_minify:
            result = "<?xml version=\"1.0\" ?>" + ElementTree.tostring(svg, 'unicode')
        else:
            result = self.prettify(svg)
        f = open(scene.export_svg_output, 'w') # TODO: search if is there a better approach
        f.write(result)
        f.close()
        return {'FINISHED'}


    def command_calc(self, scene, obj, spline, point, origin, d, prev, box): # TODO: get all these values without having to pass (except 'point')
        """Calculates the path's next command"""

        precision = scene.export_svg_precision
        p = point.co.to_2d().to_tuple(precision)
        r = [point.handle_right.to_2d().to_tuple(precision), point.handle_right_type] # TODO: type will be used for choose between L C S commands
        l = [point.handle_left.to_2d().to_tuple(precision), point.handle_left_type]   # C can do all the job, but using the others can reduce the svg
        values = {'x': p[0], 'y': p[1]}
        # first command is moveto first point, then curveto others points
        if not d:
            result = self.commands['moveto'].format(**values)
        else:
            values.update({'h1x': prev[0][0], 'h1y': prev[0][1], 'h2x': l[0][0], 'h2y': l[0][1]})
            result = self.commands['curveto'].format(**values)
        # update prev
        del prev[:]
        prev.extend(r)
        # update boundingbox
        box[0] = min([box[0], origin[0] + p[0], origin[0] + r[0][0], origin[0] + l[0][0]])
        box[1] = min([box[1], origin[1] + p[1], origin[1] + r[0][1], origin[1] + l[0][1]])
        box[2] = max([box[2], origin[0] + p[0], origin[0] + r[0][0], origin[0] + l[0][0]])
        box[3] = max([box[3], origin[1] + p[1], origin[1] + r[0][1], origin[1] + l[0][1]])
        # done
        return result

    @staticmethod
    def col_to_hex(col):
        """Converts a gamma-corrected Color to hexadecimal"""

        result = '#'
        gamma = 1.0 / 2.2607278 #2.2 wasn't too precise :p but it's not exactly. TODO: figure out how to properly convert Color object to #hex
        for ch in col:
            result += format(round(pow(ch, gamma) * 255), 'x')
        return result

    @staticmethod
    def prettify(elem):
        """Returns a pretty-printed XML string for the Element"""

        rough_string = ElementTree.tostring(elem, 'utf-8')
        reparsed = minidom.parseString(rough_string)
        return reparsed.toprettyxml(indent='  ')


def register():
    bpy.types.Scene.export_svg_precision = bpy.props.IntProperty(
            name="Precision",
            description="Precision of floating point Vectors",
            default=4,
            min=0,
            max=21)

    bpy.types.Scene.export_svg_minify = bpy.props.BoolProperty(
            name="Minify",
            description="SVG in one line",
            default=False)

    bpy.types.Scene.export_svg_output = bpy.props.StringProperty(
            name="Output",
            description="Path to output file",
            default="output.svg",
            subtype='FILE_PATH')

    bpy.utils.register_class(DATA_OT_CurveExportSVG)
    bpy.utils.register_class(CurveExportSVGPanel)


def unregister():
    bpy.utils.unregister_class(CurveExportSVGPanel)
    bpy.utils.unregister_class(DATA_OT_CurveExportSVG)

    del bpy.types.Scene.export_svg_precision
    del bpy.types.Scene.export_svg_minify
    del bpy.types.Scene.export_svg_output


if __name__ == '__main__':
    register()
