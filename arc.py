bl_info = {
    "name": "ARC Vision",
    "author": "TENET LABS",
    "version": (1, 0, 0),
    "blender": (4, 0, 0),
    "location": "Properties > Render > ARC Vision",
    "description": "ARC Vision — Advanced Render Cinematics by TENET LABS. Large format 65mm film simulation for Cycles.",
    "category": "Render",
}

import bpy
import math
from bpy.props import BoolProperty, EnumProperty, FloatProperty
from bpy.types import Panel, Operator, PropertyGroup


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ARC_SENSOR_WIDTH = 54.12   # 65mm large format sensor width in mm
ARC_SENSOR_HEIGHT = 25.59  # 1.85:1 aspect ratio derived height
ARC_ASPECT = 1.85

ARC_LENS_PRESETS = [
    ("24", "24mm — Extreme Wide", "Establishing shots, environments"),
    ("35", "35mm — Wide", "Most common narrative lens"),
    ("50", "50mm — Normal", "Closest to human eye on 65mm"),
    ("75", "75mm — Short Tele", "Portraits and mid shots"),
    ("100", "100mm — Telephoto", "Compression and close-ups"),
]

ARC_RENDER_PRESETS = {
    "PREVIEW": {
        "samples": 64,
        "noise_threshold": 0.1,
        "use_denoising": True,
    },
    "STANDARD": {
        "samples": 512,
        "noise_threshold": 0.01,
        "use_denoising": True,
    },
    "PREMIUM": {
        "samples": 2048,
        "noise_threshold": 0.001,
        "use_denoising": True,
    },
}


# ---------------------------------------------------------------------------
# Property Group
# ---------------------------------------------------------------------------

class ARCVisionSettings(PropertyGroup):

    enabled: BoolProperty(
        name="ARC Vision",
        image="ARC.png",
        description="Enable ARC Vision format and ARC Engine",
        default=False,
        update=lambda self, ctx: arc_vision_toggle(self, ctx)
    )

    lens_preset: EnumProperty(
        name="Lens",
        description="ARC Vision prime lens preset",
        items=ARC_LENS_PRESETS,
        default="35",
        update=lambda self, ctx: apply_lens(self, ctx)
    )

    render_preset: EnumProperty(
        name="Render Quality",
        description="ARC Engine render quality preset",
        items=[
            ("PREVIEW", "Preview", "Fast draft at correct ratio"),
            ("STANDARD", "Standard", "Balanced quality and time"),
            ("PREMIUM", "Premium", "Full cinematic quality"),
        ],
        default="STANDARD",
        update=lambda self, ctx: apply_render_preset(self, ctx)
    )

    shutter_angle: FloatProperty(
        name="Shutter Angle",
        description="Film shutter angle in degrees (180° = cinema standard)",
        default=180.0,
        min=90.0,
        max=270.0,
        update=lambda self, ctx: apply_shutter(self, ctx)
    )

    arc_camera_exists: BoolProperty(default=False)

    output_format: EnumProperty(
        name="Output Format",
        description="ARC Vision output file format",
        items=[
            ("PREVIEW", "Preview — JPEG", "Fast JPEG for client previews and quick checks"),
            ("STANDARD", "Standard — OpenEXR 16-bit", "Half float EXR, smaller files, cinematic quality"),
            ("MASTER", "Master — OpenEXR Multilayer 32-bit", "Full float multilayer EXR, complete passes, archival"),
        ],
        default="STANDARD",
        update=lambda self, ctx: apply_output_format(self, ctx)
    )


# ---------------------------------------------------------------------------
# Core Functions
# ---------------------------------------------------------------------------

def arc_vision_toggle(self, context):
    if self.enabled:
        activate_arc_vision(context)
    else:
        deactivate_arc_vision(context)


def activate_arc_vision(context):
    scene = context.scene
    rd = scene.render
    cycles = scene.cycles

    # --- Resolution & Aspect ---
    rd.resolution_x = 4096
    rd.resolution_y = int(4096 / ARC_ASPECT)  # 2214
    rd.pixel_aspect_x = 1.0
    rd.pixel_aspect_y = 1.0

    # --- Render Engine ---
    rd.engine = 'CYCLES'
    cycles.device = 'GPU'
    bpy.context.preferences.addons['cycles'].preferences.compute_device_type = 'CUDA'

    # --- ARC Engine: Path Tracing ---
    cycles.use_adaptive_sampling = True
    cycles.adaptive_threshold = 0.01
    cycles.samples = 512
    cycles.use_denoising = True
    cycles.denoiser = 'OPENIMAGEDENOISE'

    # --- Light Bounces (cinematic) ---
    cycles.max_bounces = 12
    cycles.diffuse_bounces = 4
    cycles.glossy_bounces = 4
    cycles.transmission_bounces = 8
    cycles.volume_bounces = 2
    cycles.transparent_max_bounces = 8

    # --- Caustics ---
    cycles.caustics_reflective = True
    cycles.caustics_refractive = True

    # --- Colour Management: Filmic (Vision3 500T character) ---
    scene.view_settings.view_transform = 'Filmic'
    scene.view_settings.look = 'Filmic - Soft Contrast'
    scene.view_settings.exposure = 0.0
    scene.view_settings.gamma = 1.0
    scene.sequencer_colorspace_settings.name = 'Filmic Log'

    # --- Apply shutter angle ---
    apply_shutter(scene.arc_vision, context)

    # --- Apply lens preset to ARC camera if present ---
    apply_lens(scene.arc_vision, context)

    # --- Build compositor (grain, halation, haze, vignette) ---
    build_arc_compositor(context)

    # --- Apply output format ---
    apply_output_format(scene.arc_vision, context)

    # --- Auto-pack assets ---
    bpy.ops.file.pack_all()

    print("[ARC Vision] Activated — ARC Engine running.")


def deactivate_arc_vision(context):
    scene = context.scene
    # Remove ARC compositor nodes
    if scene.use_nodes:
        ntree = scene.node_tree
        for node in list(ntree.nodes):
            if node.name.startswith("ARC_"):
                ntree.nodes.remove(node)
    print("[ARC Vision] Deactivated.")


def apply_lens(self, context):
    scene = context.scene
    focal = float(self.lens_preset)
    # Apply to active ARC camera
    arc_cam = get_arc_camera(scene)
    if arc_cam:
        cam_data = arc_cam.data
        cam_data.lens = focal
        cam_data.sensor_width = ARC_SENSOR_WIDTH
        cam_data.sensor_height = ARC_SENSOR_HEIGHT
        cam_data.sensor_fit = 'HORIZONTAL'


def apply_shutter(self, context):
    scene = context.scene
    cycles = scene.cycles
    fps = scene.render.fps
    # Convert shutter angle to Blender motion blur shutter (fraction of frame)
    shutter_fraction = self.shutter_angle / 360.0
    cycles.motion_blur_position = 'CENTER'
    scene.render.motion_blur_shutter = shutter_fraction


def apply_output_format(self, context):
    scene = context.scene
    rd = scene.render
    image_settings = rd.image_settings

    if self.output_format == "PREVIEW":
        image_settings.file_format = 'JPEG'
        image_settings.quality = 92
        image_settings.color_mode = 'RGB'

    elif self.output_format == "STANDARD":
        image_settings.file_format = 'OPEN_EXR'
        image_settings.color_depth = '16'
        image_settings.exr_codec = 'ZIP'
        image_settings.color_mode = 'RGBA'

    elif self.output_format == "MASTER":
        image_settings.file_format = 'OPEN_EXR_MULTILAYER'
        image_settings.color_depth = '32'
        image_settings.exr_codec = 'ZIP'
        image_settings.color_mode = 'RGBA'
        # Enable render passes for multilayer
        view_layer = scene.view_layers[0]
        view_layer.use_pass_diffuse_color = True
        view_layer.use_pass_diffuse_direct = True
        view_layer.use_pass_diffuse_indirect = True
        view_layer.use_pass_glossy_direct = True
        view_layer.use_pass_glossy_indirect = True
        view_layer.use_pass_shadow = True
        view_layer.use_pass_z = True
        view_layer.use_pass_ambient_occlusion = True
        view_layer.use_pass_emit = True


def apply_render_preset(self, context):
    cycles = context.scene.cycles
    preset = ARC_RENDER_PRESETS.get(self.render_preset, ARC_RENDER_PRESETS["STANDARD"])
    cycles.samples = preset["samples"]
    cycles.adaptive_threshold = preset["noise_threshold"]
    cycles.use_denoising = preset["use_denoising"]


# ---------------------------------------------------------------------------
# Compositor — ARC Vision Look
# ---------------------------------------------------------------------------

def build_arc_compositor(context):
    scene = context.scene
    scene.use_nodes = True
    ntree = scene.node_tree

    # Remove old ARC nodes
    for node in list(ntree.nodes):
        if node.name.startswith("ARC_"):
            ntree.nodes.remove(node)

    # Find or create Render Layers and Composite nodes
    render_layers = None
    composite = None
    for node in ntree.nodes:
        if node.type == 'R_LAYERS':
            render_layers = node
        if node.type == 'COMPOSITE':
            composite = node

    if not render_layers:
        render_layers = ntree.nodes.new('CompositorNodeRLayers')
        render_layers.location = (-800, 300)

    if not composite:
        composite = ntree.nodes.new('CompositorNodeComposite')
        composite.location = (800, 300)

    # --- Colour Correction: Vision3 500T warmth + matte ---
    cc = ntree.nodes.new('CompositorNodeColorCorrection')
    cc.name = "ARC_ColourCorrection"
    cc.location = (-400, 300)
    # Lift shadows (matte, fogged base)
    cc.shadows.gain = 1.0
    cc.shadows.lift = 0.04      # lifts blacks — matte/fogged character
    cc.shadows.gamma = 1.0
    cc.shadows.saturation = 0.85
    # Warm midtones
    cc.midtones.gain = 1.02
    cc.midtones.gamma = 0.97    # slightly dense midtones
    cc.midtones.saturation = 0.95
    # Highlight rolloff
    cc.highlights.gain = 0.96   # pulls back highlights — soft rolloff
    cc.highlights.saturation = 0.9

    # --- Hue/Saturation: olive greens, teal blues ---
    hue_sat = ntree.nodes.new('CompositorNodeHueSat')
    hue_sat.name = "ARC_HueSat"
    hue_sat.location = (-200, 300)
    hue_sat.inputs['Saturation'].default_value = 0.92
    hue_sat.inputs['Value'].default_value = 1.0

    # --- Vignette (subtle natural lens falloff) ---
    ellipse_mask = ntree.nodes.new('CompositorNodeEllipseMask')
    ellipse_mask.name = "ARC_VignetteMask"
    ellipse_mask.location = (-400, 0)
    ellipse_mask.width = 0.85
    ellipse_mask.height = 0.85

    blur_vignette = ntree.nodes.new('CompositorNodeBlur')
    blur_vignette.name = "ARC_VignetteBlur"
    blur_vignette.location = (-200, 0)
    blur_vignette.size_x = 80
    blur_vignette.size_y = 80

    invert_vignette = ntree.nodes.new('CompositorNodeInvert')
    invert_vignette.name = "ARC_VignetteInvert"
    invert_vignette.location = (0, 0)

    mix_vignette = ntree.nodes.new('CompositorNodeMixRGB')
    mix_vignette.name = "ARC_VignetteMix"
    mix_vignette.location = (200, 300)
    mix_vignette.blend_type = 'MULTIPLY'
    mix_vignette.inputs['Fac'].default_value = 0.35

    # --- Halation (warm bleed around highlights — always on) ---
    halation_blur = ntree.nodes.new('CompositorNodeBlur')
    halation_blur.name = "ARC_HalationBlur"
    halation_blur.location = (-200, -200)
    halation_blur.size_x = 12
    halation_blur.size_y = 12
    halation_blur.filter_type = 'GAUSS'

    halation_colour = ntree.nodes.new('CompositorNodeCurveRGB')
    halation_colour.name = "ARC_HalationColour"
    halation_colour.location = (0, -200)

    mix_halation = ntree.nodes.new('CompositorNodeMixRGB')
    mix_halation.name = "ARC_HalationMix"
    mix_halation.location = (400, 300)
    mix_halation.blend_type = 'SCREEN'
    mix_halation.inputs['Fac'].default_value = 0.08

    # --- Grain (shadow-intensifying, Vision3 character) ---
    grain = ntree.nodes.new('CompositorNodeTexNoise')
    grain.name = "ARC_Grain"
    grain.location = (0, -400)
    grain.inputs['Scale'].default_value = 800.0
    grain.inputs['Detail'].default_value = 8.0
    grain.inputs['Roughness'].default_value = 0.75
    grain.inputs['Distortion'].default_value = 0.0

    grain_mix = ntree.nodes.new('CompositorNodeMixRGB')
    grain_mix.name = "ARC_GrainMix"
    grain_mix.location = (600, 300)
    grain_mix.blend_type = 'OVERLAY'
    grain_mix.inputs['Fac'].default_value = 0.06

    # --- Atmospheric Haze ---
    haze_mix = ntree.nodes.new('CompositorNodeMixRGB')
    haze_mix.name = "ARC_Haze"
    haze_mix.location = (400, 100)
    haze_mix.blend_type = 'ADD'
    haze_mix.inputs['Fac'].default_value = 0.015
    haze_mix.inputs[2].default_value = (0.95, 0.88, 0.75, 1.0)  # warm haze tint

    # --- Wire nodes together ---
    links = ntree.links

    # Render → Colour Correction
    links.new(render_layers.outputs['Image'], cc.inputs['Image'])
    # CC → HueSat
    links.new(cc.outputs['Image'], hue_sat.inputs['Image'])
    # HueSat → Vignette mix (image input)
    links.new(hue_sat.outputs['Image'], mix_vignette.inputs[1])
    # Vignette mask chain
    links.new(ellipse_mask.outputs['Mask'], blur_vignette.inputs['Image'])
    links.new(blur_vignette.outputs['Image'], invert_vignette.inputs['Color'])
    links.new(invert_vignette.outputs['Color'], mix_vignette.inputs[2])
    # Vignette → Halation mix
    links.new(mix_vignette.outputs['Image'], mix_halation.inputs[1])
    # Halation chain
    links.new(render_layers.outputs['Image'], halation_blur.inputs['Image'])
    links.new(halation_blur.outputs['Image'], halation_colour.inputs['Image'])
    links.new(halation_colour.outputs['Image'], mix_halation.inputs[2])
    # Halation → Haze
    links.new(mix_halation.outputs['Image'], haze_mix.inputs[1])
    # Haze → Grain mix
    links.new(haze_mix.outputs['Image'], grain_mix.inputs[1])
    links.new(grain.outputs['Color'], grain_mix.inputs[2])
    # Grain → Composite
    links.new(grain_mix.outputs['Image'], composite.inputs['Image'])

    print("[ARC Vision] Compositor built.")


# ---------------------------------------------------------------------------
# ARC Camera
# ---------------------------------------------------------------------------

def get_arc_camera(scene):
    for obj in scene.objects:
        if obj.type == 'CAMERA' and obj.get("arc_vision_camera"):
            return obj
    return None


class ARC_OT_AddCamera(Operator):
    bl_idname = "arc_vision.add_camera"
    bl_label = "Add ARC Camera"
    bl_description = "Add the ARC Vision large format camera to the scene"

    def execute(self, context):
        scene = context.scene

        # Only one ARC camera allowed
        if get_arc_camera(scene):
            self.report({'WARNING'}, "ARC Vision camera already exists in scene.")
            return {'CANCELLED'}

        # Create camera data
        cam_data = bpy.data.cameras.new("ARC_Vision_Camera")
        cam_data.lens = float(scene.arc_vision.lens_preset)
        cam_data.sensor_width = ARC_SENSOR_WIDTH
        cam_data.sensor_height = ARC_SENSOR_HEIGHT
        cam_data.sensor_fit = 'HORIZONTAL'

        # Depth of field — physically driven
        cam_data.dof.use_dof = True
        cam_data.dof.aperture_fstop = 2.8
        cam_data.dof.aperture_blades = 8          # Octagonal bokeh
        cam_data.dof.aperture_rotation = 0.0
        cam_data.dof.aperture_ratio = 1.0

        # Motion blur
        cam_data.show_passepartout = True
        cam_data.passepartout_alpha = 0.85

        # Create camera object
        cam_obj = bpy.data.objects.new("ARC_Vision_Camera", cam_data)
        cam_obj["arc_vision_camera"] = True  # Tag it

        # Place at current view or default position
        cam_obj.location = (0, -8, 2)
        cam_obj.rotation_euler = (math.radians(80), 0, 0)

        scene.collection.objects.link(cam_obj)
        scene.camera = cam_obj

        scene.arc_vision.arc_camera_exists = True
        self.report({'INFO'}, "ARC Vision camera added and set as active.")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Package for Render
# ---------------------------------------------------------------------------

class ARC_OT_PackageForRender(Operator):
    bl_idname = "arc_vision.package_for_render"
    bl_label = "Package for ARC Render"
    bl_description = "Bake all ARC Vision settings into the .blend file and pack all assets. Farm-ready."

    def execute(self, context):
        # Pack all external assets
        bpy.ops.file.pack_all()

        # Rebuild compositor to bake latest settings
        build_arc_compositor(context)

        # Apply all current settings
        apply_lens(context.scene.arc_vision, context)
        apply_shutter(context.scene.arc_vision, context)
        apply_render_preset(context.scene.arc_vision, context)

        self.report({'INFO'}, "ARC Vision: Scene packaged and ready for render farm.")
        return {'FINISHED'}


# ---------------------------------------------------------------------------
# Auto-pack on save
# ---------------------------------------------------------------------------

def arc_auto_pack(dummy):
    scene = bpy.context.scene
    if hasattr(scene, 'arc_vision') and scene.arc_vision.enabled:
        bpy.ops.file.pack_all()


# ---------------------------------------------------------------------------
# UI — ARC Vision Panels
# ---------------------------------------------------------------------------

class ARC_PT_MainPanel(Panel):
    bl_label = ""
    bl_idname = "ARC_PT_main"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"
    bl_options = {'HIDE_HEADER'}

    def draw(self, context):
        layout = self.layout
        arc = context.scene.arc_vision

        # ── HEADER ───────────────────────────────────────────────────────────
        header = layout.box()

        # Logo row
        title_row = header.row(align=True)
        title_row.scale_y = 1.6
        title_row.label(text="  ARC  VISION", icon='CAMERA_DATA')
        toggle = title_row.row()
        toggle.alignment = 'RIGHT'
        toggle.prop(arc, "enabled",
                    text="● ON" if arc.enabled else "○ OFF",
                    toggle=True)

        # Byline
        byline = header.row()
        byline.alignment = 'CENTER'
        byline.scale_y = 0.65
        byline.label(text="ADVANCED RENDER CINEMATICS  ·  TENET")

        if not arc.enabled:
            layout.separator(factor=0.8)
            off = layout.box()
            off.label(text="ARC Vision is off.", icon='INFO')
            return

        layout.separator(factor=0.5)

        # ── FORMAT STAMP ─────────────────────────────────────────────────────
        stamp = layout.box()
        stamp.scale_y = 0.8
        col = stamp.column(align=True)
        r1 = col.row()
        r1.label(text="65mm  ·  1.85:1  ·  Vision3 500T  ·  8-Blade")
        r2 = col.row()
        r2.label(text="Halation  ·  Grain  ·  Haze  ·  Hybrid GPU+CPU")


# ── CAMERA ────────────────────────────────────────────────────────────────────

class ARC_PT_CameraPanel(Panel):
    bl_label = "CAMERA"
    bl_idname = "ARC_PT_camera"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"
    bl_parent_id = "ARC_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.scene.arc_vision.enabled

    def draw_header(self, context):
        self.layout.label(text="", icon='CAMERA_DATA')

    def draw(self, context):
        layout = self.layout
        arc = context.scene.arc_vision
        arc_cam = get_arc_camera(context.scene)

        if arc_cam:
            # Active camera badge
            badge = layout.box()
            badge_row = badge.row()
            badge_row.label(text=arc_cam.name, icon='CHECKMARK')

            layout.separator(factor=0.3)

            # Controls — clean two-row layout
            col = layout.column(align=True)
            col.scale_y = 1.2
            col.prop(arc, "lens_preset", text="Lens")
            col.prop(arc, "shutter_angle", text="Shutter °")

            layout.separator(factor=0.5)

            # Rig placeholder — one clean line
            rig = layout.box()
            rig.label(text="Camera Rig  —  Coming Soon", icon='ARMATURE_DATA')

        else:
            warn = layout.box()
            warn.label(text="No ARC camera in scene.", icon='ERROR')
            layout.separator(factor=0.3)
            layout.operator("arc_vision.add_camera",
                            text="ADD ARC CAMERA", icon='ADD')


# ── RENDER ────────────────────────────────────────────────────────────────────

class ARC_PT_RenderPanel(Panel):
    bl_label = "RENDER"
    bl_idname = "ARC_PT_render"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"
    bl_parent_id = "ARC_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.scene.arc_vision.enabled

    def draw_header(self, context):
        self.layout.label(text="", icon='RENDER_STILL')

    def draw(self, context):
        layout = self.layout
        arc = context.scene.arc_vision

        col = layout.column(align=True)
        col.scale_y = 1.2
        col.prop(arc, "render_preset", text="Quality")

        layout.separator(factor=0.5)

        # One-line context hint per preset
        hint = layout.box()
        hint.scale_y = 0.75
        if arc.render_preset == "PREVIEW":
            hint.label(text="64 samples  ·  Fast checks", icon='INFO')
        elif arc.render_preset == "STANDARD":
            hint.label(text="512 samples  ·  Production", icon='INFO')
        elif arc.render_preset == "PREMIUM":
            hint.label(text="2048 samples  ·  Final delivery", icon='INFO')


# ── OUTPUT ────────────────────────────────────────────────────────────────────

class ARC_PT_OutputPanel(Panel):
    bl_label = "OUTPUT"
    bl_idname = "ARC_PT_output"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"
    bl_parent_id = "ARC_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.scene.arc_vision.enabled

    def draw_header(self, context):
        self.layout.label(text="", icon='IMAGE_DATA')

    def draw(self, context):
        layout = self.layout
        arc = context.scene.arc_vision

        col = layout.column(align=True)
        col.scale_y = 1.2
        col.prop(arc, "output_format", text="Format")

        layout.separator(factor=0.5)

        hint = layout.box()
        hint.scale_y = 0.75
        if arc.output_format == "PREVIEW":
            hint.label(text="JPEG 92%  ·  RGB  ·  Client previews", icon='INFO')
        elif arc.output_format == "STANDARD":
            hint.label(text="EXR 16-bit  ·  RGBA  ·  Production", icon='INFO')
        elif arc.output_format == "MASTER":
            hint.label(text="EXR 32-bit Multilayer  ·  All passes  ·  Delivery", icon='INFO')


# ── EXPORT ────────────────────────────────────────────────────────────────────

class ARC_PT_ExportPanel(Panel):
    bl_label = "EXPORT"
    bl_idname = "ARC_PT_export"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"
    bl_parent_id = "ARC_PT_main"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.scene.arc_vision.enabled

    def draw_header(self, context):
        self.layout.label(text="", icon='EXPORT')

    def draw(self, context):
        layout = self.layout

        layout.operator("arc_vision.package_for_render",
                        text="PACKAGE FOR ARC RENDER", icon='EXPORT')

        layout.separator(factor=0.5)

        note = layout.box()
        note.scale_y = 0.75
        note.label(text="Bakes all ARC settings into .blend.", icon='INFO')
        note.label(text="Farm-ready. No add-on needed on farm.")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = [
    ARCVisionSettings,
    ARC_OT_AddCamera,
    ARC_OT_PackageForRender,
    ARC_PT_MainPanel,
    ARC_PT_CameraPanel,
    ARC_PT_RenderPanel,
    ARC_PT_OutputPanel,
    ARC_PT_ExportPanel,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.arc_vision = bpy.props.PointerProperty(type=ARCVisionSettings)
    bpy.app.handlers.save_pre.append(arc_auto_pack)
    print("[ARC Vision] Add-on registered.")


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.arc_vision
    if arc_auto_pack in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(arc_auto_pack)
    print("[ARC Vision] Add-on unregistered.")


if __name__ == "__main__":
    register()
