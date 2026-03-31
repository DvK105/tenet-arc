import bpy
from bpy.props import *

ARC_ASPECT = 1.76

class ARCVisionSettings(bpy.types.PropertyGroup):

    enabled: BoolProperty(name="Enabled", default=False)

    lens: EnumProperty(
        name="Lens",
        items=[("24","24mm",""),("35","35mm",""),("50","50mm",""),("75","75mm","")],
        default="35"
    )

    render_quality: EnumProperty(
        name="Quality",
        items=[("DRAFT","Draft",""),("QUALITY","Quality",""),("PROD","Production","")],
        default="QUALITY"
    )

    look: EnumProperty(
        name="Look",
        items=[("NEUTRAL","Neutral",""),("WARM","Warm","")],
        default="NEUTRAL"
    )

    script_input: StringProperty(name="Screenplay")
    ai_output: StringProperty(name="Suggestions")

    api_key: StringProperty(
        name="API Key",
        subtype='PASSWORD'
    )

def apply_aspect(scene):
    rd = scene.render
    rd.resolution_percentage = 100
    rd.resolution_x = 4096
    rd.resolution_y = int(4096 / ARC_ASPECT)
    rd.pixel_aspect_x = 1.0
    rd.pixel_aspect_y = 1.0

def get_arc_camera(scene):
    for obj in scene.objects:
        if obj.type == 'CAMERA' and obj.get("arc_cam"):
            return obj
    return None

class ARC_OT_AddCamera(bpy.types.Operator):
    bl_idname = "arc.add_camera"
    bl_label = "Add Camera"

    def execute(self, context):
        cam_data = bpy.data.cameras.new("ARC_Cam")
        cam = bpy.data.objects.new("ARC_Cam", cam_data)

        cam["arc_cam"] = True
        context.scene.collection.objects.link(cam)
        context.scene.camera = cam

        apply_aspect(context.scene)

        return {'FINISHED'}

def set_visibility(names, state, scene):
    for n in names:
        obj = scene.objects.get(n)
        if obj:
            obj.hide_render = state

classes = [ARCVisionSettings, ARC_OT_AddCamera]

def register_core():
    for c in classes:
        bpy.utils.register_class(c)
    bpy.types.Scene.arc_vision = PointerProperty(type=ARCVisionSettings)

def unregister_core():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)
    del bpy.types.Scene.arc_vision