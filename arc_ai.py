import bpy
import sys
import subprocess

# ---------------- AUTO INSTALL ---------------- #

def ensure_gemini():
    try:
        import google.generativeai
    except ImportError:
        python_exe = sys.executable
        subprocess.call([python_exe, "-m", "pip", "install", "google-generativeai"])


# ---------------- AI FUNCTION ---------------- #

def generate_scene_suggestions(script, api_key):

    if not script.strip():
        return "ERROR: No screenplay provided."

    if not api_key:
        return "ERROR: Please enter your API key."

    try:
        ensure_gemini()
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-pro")

        prompt = f"""
You are a professional cinematographer.

Convert this screenplay into clear, practical filmmaking suggestions.

Script:
{script}

Return in this format:

SHOTS:
- shot type, lens, movement

LIGHTING:
- key light position
- fill light
- mood

CAMERA:
- lens (mm)
- angle
- movement

Keep it short and actionable.
"""

        response = model.generate_content(prompt)

        if not response or not hasattr(response, "text"):
            return "AI Error: No response."

        return response.text

    except Exception as e:
        return f"AI Error: {str(e)}"


# ---------------- OPERATORS ---------------- #

class ARC_OT_AI_Script(bpy.types.Operator):
    bl_idname = "arc.ai_script"
    bl_label = "Generate Suggestions"

    def execute(self, context):
        arc = context.scene.arc_vision

        result = generate_scene_suggestions(
            arc.script_input,
            arc.api_key
        )

        arc.ai_output = result

        self.report({'INFO'}, "AI Suggestions Updated")
        return {'FINISHED'}


# ---------------- APPLY CAMERA ---------------- #

class ARC_OT_ApplyCamera(bpy.types.Operator):
    bl_idname = "arc.apply_camera"
    bl_label = "Apply Camera"

    def execute(self, context):
        arc = context.scene.arc_vision
        cam = context.scene.camera

        if not cam:
            self.report({'WARNING'}, "No camera found.")
            return {'CANCELLED'}

        txt = arc.ai_output.lower()

        if "75" in txt:
            cam.data.lens = 75
        elif "50" in txt:
            cam.data.lens = 50
        elif "35" in txt:
            cam.data.lens = 35
        elif "24" in txt:
            cam.data.lens = 24

        self.report({'INFO'}, "Camera updated")
        return {'FINISHED'}


# ---------------- APPLY LIGHTING ---------------- #

class ARC_OT_ApplyLighting(bpy.types.Operator):
    bl_idname = "arc.apply_light"
    bl_label = "Apply Lighting"

    def execute(self, context):
        scene = context.scene

        light_data = bpy.data.lights.new(name="ARC_Key", type='AREA')
        light = bpy.data.objects.new("ARC_Key", light_data)

        light.location = (3, -3, 5)
        light_data.energy = 1000

        scene.collection.objects.link(light)

        self.report({'INFO'}, "Lighting added")
        return {'FINISHED'}


# ---------------- REGISTER ---------------- #

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