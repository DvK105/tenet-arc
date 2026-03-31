import bpy
import json

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
        return "ERROR: Install 'google-generativeai'."

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel("gemini-pro")

        prompt = f"""
You are a professional cinematographer.

Convert this screenplay into STRICT JSON.

Rules:
- Output ONLY valid JSON
- No explanations
- No markdown

Schema:
{{
  "lens": 24 | 35 | 50 | 75,
  "shot": "close-up | medium | wide",
  "lighting": {{
    "type": "low_key | high_key",
    "intensity": number,
    "position": [x, y, z]
  }}
}}

Script:
{script}
"""

        response = model.generate_content(prompt)
        return response.text if hasattr(response, "text") else "No response"

    except Exception as e:
        return f"AI Error: {str(e)}"


# ---------------- JSON PARSER ---------------- #

def parse_ai_json(text):
    try:
        return json.loads(text)
    except:
        return None


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

        # Pretty format if valid JSON
        parsed = parse_ai_json(result)
        if parsed:
            arc.ai_output = json.dumps(parsed, indent=2)
        else:
            arc.ai_output = result

        self.report({'INFO'}, "AI Updated")
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

        data = parse_ai_json(arc.ai_output)

        if not data:
            self.report({'ERROR'}, "Invalid AI JSON.")
            return {'CANCELLED'}

        lens = data.get("lens")

        if lens:
            cam.data.lens = lens
            self.report({'INFO'}, f"Lens set to {lens}mm")

        return {'FINISHED'}


# ---------------- APPLY LIGHTING ---------------- #

class ARC_OT_ApplyLighting(bpy.types.Operator):
    bl_idname = "arc.apply_light"
    bl_label = "Apply Lighting"

    def execute(self, context):
        arc = context.scene.arc_vision
        scene = context.scene

        data = parse_ai_json(arc.ai_output)

        if not data:
            self.report({'ERROR'}, "Invalid AI JSON.")
            return {'CANCELLED'}

        lighting = data.get("lighting", {})

        intensity = lighting.get("intensity", 1000)
        position = lighting.get("position", [3, -3, 5])

        light = bpy.data.objects.get("ARC_Key")

        if light is None:
            light_data = bpy.data.lights.new(name="ARC_Key", type='AREA')
            light = bpy.data.objects.new("ARC_Key", light_data)
            scene.collection.objects.link(light)
        else:
            light_data = light.data

        light.location = position
        light_data.energy = intensity

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