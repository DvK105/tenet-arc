import bpy
import os

def load_logo():
    path = os.path.join(os.path.dirname(__file__), "ARC.png")
    if os.path.exists(path):
        return bpy.data.images.load(path, check_existing=True)
    return None

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

        layout.prop(arc, "enabled", text="Enable")

        if not arc.enabled:
            return

        layout.operator("arc.add_camera", text="Add Camera")

        layout.separator()

        layout.label(text="Screenplay")
        layout.prop(arc, "script_input", text="")

        layout.prop(arc, "api_key", text="API Key")

        layout.operator("arc.ai_script", text="Generate Suggestions")

        layout.separator()

        layout.label(text="Suggestions")
        layout.prop(arc, "ai_output", text="")

        layout.operator("arc.apply_camera", text="Apply Camera")
        layout.operator("arc.apply_light", text="Apply Lighting")

classes = [ARC_PT_Main]

def register_ui():
    for c in classes:
        bpy.utils.register_class(c)

def unregister_ui():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)