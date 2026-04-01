import bpy
from bpy.props import BoolProperty, StringProperty, PointerProperty

ARC_ASPECT = 1.76

class ARCVisionSettings(bpy.types.PropertyGroup):
    enabled: BoolProperty(name="Enable", default=False)

    script_input: StringProperty(
        name="Screenplay"
    )

    ai_output: StringProperty(
        name="Suggestions"
    )

    api_key: StringProperty(
        name="API Key",
        subtype='PASSWORD'
    )

def apply_aspect(scene):
    rd = scene.render
    rd.resolution_x = 4096
    rd.resolution_y = int(4096 / ARC_ASPECT)
    rd.pixel_aspect_x = 1.0
    rd.pixel_aspect_y = 1.0

class ARC_OT_AddCamera(bpy.types.Operator):
    """Add an ARC camera to the scene"""
    bl_idname = "arc.add_camera"
    bl_label = "Add Camera"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        cam_data = bpy.data.cameras.new("ARC_Cam")
        cam = bpy.data.objects.new("ARC_Cam", cam_data)

        cam["arc_cam"] = True
        context.scene.collection.objects.link(cam)
        context.scene.camera = cam

        apply_aspect(context.scene)
        return {'FINISHED'}

classes = [ARCVisionSettings, ARC_OT_AddCamera]

def register_core():
    for c in classes:
        try:
            bpy.utils.register_class(c)
        except ValueError:
            pass  # Class already registered
    try:
        bpy.types.Scene.arc_vision = PointerProperty(type=ARCVisionSettings)
    except TypeError:
        pass  # Property already registered

def unregister_core():
    try:
        del bpy.types.Scene.arc_vision
    except AttributeError:
        pass  # Property not registered
    for c in reversed(classes):
        try:
            bpy.utils.unregister_class(c)
        except ValueError:
            pass  # Class not registered