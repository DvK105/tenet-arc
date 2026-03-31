import bpy
import os

LOGO_IMAGE = None

def load_logo():
    global LOGO_IMAGE

    if LOGO_IMAGE and LOGO_IMAGE.name in bpy.data.images:
        return LOGO_IMAGE

    path = os.path.join(os.path.dirname(__file__), "ARC.png")
    if os.path.exists(path):
        LOGO_IMAGE = bpy.data.images.load(path, check_existing=True)
    else:
        LOGO_IMAGE = None

    return LOGO_IMAGE


class ARC_PT_Main(bpy.types.Panel):
    bl_label = ""
    bl_idname = "ARC_PT_MAIN"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "ARC"

    def draw(self, context):
        layout = self.layout
        arc = context.scene.arc_vision

        logo = load_logo()
        if logo:
            layout.template_icon(icon_value=logo.preview.icon_id, scale=6)

        layout.prop(arc, "enabled")

        if not arc.enabled:
            return

        layout.operator("arc.add_camera")

        layout.separator()

        box_script = layout.box()
        box_script.label(text="Screenplay")
        box_script.prop(arc, "script_input", text="")

        layout.prop(arc, "api_key")

        layout.operator("arc.ai_script")

        layout.separator()

        box_suggestions = layout.box()
        box_suggestions.label(text="Suggestions")
        box_suggestions.prop(arc, "ai_output", text="")

        layout.operator("arc.apply_camera")
        layout.operator("arc.apply_light")


classes = [ARC_PT_Main]

def register_ui():
    for c in classes:
        if not hasattr(bpy.types, c.__name__):
            bpy.utils.register_class(c)

def unregister_ui():
    for c in reversed(classes):
        if hasattr(bpy.types, c.__name__):
            bpy.utils.unregister_class(c)