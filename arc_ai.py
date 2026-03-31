import bpy
import re

# ---------------- SAFE IMPORT ---------------- #

def get_genai():
    try:
        import google.generativeai as genai
        return genai
    except ImportError:
        return None


# ---------------- AI FUNCTION ---------------- #

def generate_scene_suggestions(script, api_key):

    if not script.strip():
        return "ERROR: No screenplay provided."

    if not api_key:
        return "ERROR: Please enter your API key."

    genai = get_genai()
    if not genai:
        return "ERROR: Gemini not installed. Please install 'google-generativeai'."

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-pro")

        prompt = f"""
You are a professional cinematographer.

Convert this screenplay into clear, practical suggestions.

Script:
{script}

Format:

SHOTS:
- shot type, lens, movement

LIGHTING:
- key light
- fill
- mood

CAMERA:
- lens (mm)
- angle
"""

        response = model.generate_content(prompt)
        return response.text if hasattr(response, "text") else "No response"

    except Exception as e:
        return f"AI Error: {str(e)}"


# ---------------- SAFE LENS PARSING ---------------- #

def extract_lens(text):
    match = re.search(r"\b(24|35|50|75)\s*mm\b", text.lower())
    return int(match.group(1)) if match else None


# ---------------- OPERATORS ---------------- #

class ARC_OT_AI_Script(bpy.types.Operator):
    bl_idname = "arc.ai_script"
    bl_label = "Generate Suggestions"

    def execute(self, context):
        arc = context.scene.arc_vision

        arc.ai_output = generate_scene_suggestions(
            arc.script_input,
            arc.api_key
        )

        self.report({'INFO'}, "AI Updated")
        return {'FINISHED'}


class ARC_OT_ApplyCamera(bpy.types.Operator):
    bl_idname = "arc.apply_camera"
    bl_label = "Apply Camera"

    def execute(self, context):
        arc = context.scene.arc_vision
        cam = context.scene.camera

        if not cam:
            self.report({'WARNING'}, "No camera found.")
            return {'CANCELLED'}

        lens = extract_lens(arc.ai_output)

        if lens:
            cam.data.lens = lens
            self.report({'INFO'}, f"Lens set to {lens}mm")
        else:
            self.report({'WARNING'}, "No valid lens found in AI output.")

        return {'FINISHED'}


class ARC_OT_ApplyLighting(bpy.types.Operator):
    bl_idname = "arc.apply_light"
    bl_label = "Apply Lighting"

    def execute(self, context):
        scene = context.scene

        light = bpy.data.objects.get("ARC_Key")

        if light is None:
            light_data = bpy.data.lights.new(name="ARC_Key", type='AREA')
            light = bpy.data.objects.new("ARC_Key", light_data)
            scene.collection.objects.link(light)
        else:
            light_data = light.data

        if isinstance(light_data, bpy.types.Light):
            light.location = (3, -3, 5)
            light_data.energy = 1000

        self.report({'INFO'}, "Lighting applied")
        return {'FINISHED'}


classes = [
    ARC_OT_AI_Script,
    ARC_OT_ApplyCamera,
    ARC_OT_ApplyLighting
]

def register_ai():
    for c in classes:
        bpy.utils.register_class(c)

def unregister_ai():
    for c in reversed(classes):
        bpy.utils.unregister_class(c)