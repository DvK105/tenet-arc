bl_info = {
    "name": "ARC Vision",
    "author": "TENET",
    "version": (2, 1, 0),
    "blender": (4, 0, 0),
    "location": "Properties > Render > ARC Vision  |  N-Panel > ARC",
    "description": "ARC Vision — Advanced Render Cinematics by TENET. Malus Engine. 65mm 1.76:1.",
    "category": "Render",
}
 
import bpy
import math
import os
from bpy.props import BoolProperty, EnumProperty, FloatProperty, StringProperty
from bpy.types import Panel, Operator, PropertyGroup
 
 
# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
 
ARC_SENSOR_WIDTH  = 54.12
ARC_SENSOR_HEIGHT = 30.75       # 54.12 / 1.76
ARC_ASPECT        = 1.76
ARC_RES_X         = 4096
ARC_RES_Y         = int(ARC_RES_X / ARC_ASPECT)   # 2327
 
# Malus Engine — preset is single source of truth for all sample counts
ARC_RENDER_PRESETS = {
    "DRAFT": {
        "base":      64,
        "static":    128,
        "dynamic":   32,
        "threshold": 0.05,
        "bounces":   8,
        "hint":      "Draft  ·  128 static  ·  32 dynamic",
    },
    "QUALITY": {
        "base":      512,
        "static":    1024,
        "dynamic":   256,
        "threshold": 0.01,
        "bounces":   12,
        "hint":      "Quality  ·  1024 static  ·  256 dynamic",
    },
    "PRODUCTION": {
        "base":      2048,
        "static":    4096,
        "dynamic":   1024,
        "threshold": 0.002,
        "bounces":   16,
        "hint":      "Production  ·  4096 static  ·  1024 dynamic",
    },
}
 
ARC_LENS_PRESETS = [
    ("24",  "24mm — Extreme Wide", "Establishing shots, environments"),
    ("35",  "35mm — Wide",         "Most common narrative lens"),
    ("50",  "50mm — Normal",       "Closest to human eye on 65mm"),
    ("75",  "75mm — Short Tele",   "Portraits and mid shots"),
    ("100", "100mm — Telephoto",   "Compression and close-ups"),
]
 
 
# ---------------------------------------------------------------------------
# Property Group
# ---------------------------------------------------------------------------
 
class ARCVisionSettings(PropertyGroup):
 
    enabled: BoolProperty(
        name="ARC Vision",
        default=False,
        update=lambda self, ctx: arc_vision_toggle(self, ctx)
    )
 
    lens_preset: EnumProperty(
        name="Lens",
        items=ARC_LENS_PRESETS,
        default="35",
        update=lambda self, ctx: apply_lens(self, ctx)
    )
 
    render_preset: EnumProperty(
        name="Render Quality",
        items=[
            ("DRAFT",      "Draft",      "Fast — 128 static / 32 dynamic"),
            ("QUALITY",    "Quality",    "Production — 1024 static / 256 dynamic"),
            ("PRODUCTION", "Production", "Delivery — 4096 static / 1024 dynamic"),
        ],
        default="QUALITY",
        update=lambda self, ctx: apply_render_preset(self, ctx)
    )
 
    shutter_angle: FloatProperty(
        name="Shutter Angle",
        default=180.0, min=90.0, max=270.0,
        update=lambda self, ctx: apply_shutter(self, ctx)
    )
 
    output_format: EnumProperty(
        name="Output Format",
        items=[
            ("DRAFT",      "Draft — JPEG",                   "JPEG for client previews"),
            ("QUALITY",    "Quality — OpenEXR 16-bit",       "Half float EXR, production"),
            ("PRODUCTION", "Production — OpenEXR ML 32-bit", "Full float multilayer, all passes"),
        ],
        default="QUALITY",
        update=lambda self, ctx: apply_output_format(self, ctx)
    )
 
    # Cool = Odyssey-style default. Warm = Vision3 500T character.
    colour_temperature: EnumProperty(
        name="Colour Temperature",
        items=[
            ("COOL", "Cool", "Steel blue-grey — Odyssey style (default)"),
            ("WARM", "Warm", "Amber organic — Vision3 500T character"),
        ],
        default="COOL",
        update=lambda self, ctx: build_arc_compositor(ctx)
    )
 
    malus_enabled: BoolProperty(
        name="Malus Engine",
        description="Use Malus static/dynamic pass system for render",
        default=True,
    )
 
    output_path: StringProperty(
        name="Output Path",
        description="Base path for ARC Vision render output and passes",
        default="//ARC_Output/",
        subtype='DIR_PATH',
    )
 
    arc_camera_exists: BoolProperty(default=False)
 
 
# ---------------------------------------------------------------------------
# Toggle
# ---------------------------------------------------------------------------
 
def arc_vision_toggle(self, context):
    if self.enabled:
        activate_arc_vision(context)
    else:
        deactivate_arc_vision(context)
 
 
# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------
 
def activate_arc_vision(context):
    scene  = context.scene
    rd     = scene.render
    cycles = scene.cycles
 
    # Resolution — 1.76:1
    rd.resolution_x   = ARC_RES_X
    rd.resolution_y   = ARC_RES_Y
    rd.pixel_aspect_x = 1.0
    rd.pixel_aspect_y = 1.0
 
    # Engine
    rd.engine = 'CYCLES'
    try:
        cycles.device = 'GPU'
        bpy.context.preferences.addons['cycles'].preferences.compute_device_type = 'CUDA'
    except Exception:
        pass
 
    # Malus physical accuracy layer
    apply_malus_physical_accuracy(context)
 
    # Colour management
    scene.view_settings.view_transform = 'Filmic'
    scene.view_settings.look           = 'Filmic - Soft Contrast'
    scene.view_settings.exposure       = 0.0
    scene.view_settings.gamma          = 1.0
    try:
        scene.sequencer_colorspace_settings.name = 'Filmic Log'
    except Exception:
        pass
 
    apply_render_preset(scene.arc_vision, context)
    apply_shutter(scene.arc_vision, context)
    apply_lens(scene.arc_vision, context)
    apply_output_format(scene.arc_vision, context)
    build_arc_compositor(context)
    safe_pack_all()
 
    print("[ARC Vision] Activated — Malus Engine running.")
 
 
def deactivate_arc_vision(context):
    scene = context.scene
    if scene.use_nodes:
        for node in list(scene.node_tree.nodes):
            if node.name.startswith("ARC_"):
                scene.node_tree.nodes.remove(node)
    print("[ARC Vision] Deactivated.")
 
 
# ---------------------------------------------------------------------------
# Malus Engine — Physical Accuracy Layer
# ---------------------------------------------------------------------------
 
def apply_malus_physical_accuracy(context):
    scene  = context.scene
    cycles = scene.cycles
 
    cycles.use_adaptive_sampling    = True
    cycles.use_denoising            = True
    cycles.denoiser                 = 'OPENIMAGEDENOISE'
    cycles.caustics_reflective      = True
    cycles.caustics_refractive      = True
    cycles.sample_clamp_direct      = 10.0
    cycles.sample_clamp_indirect    = 5.0
    cycles.max_bounces              = 12
    cycles.diffuse_bounces          = 4
    cycles.glossy_bounces           = 4
    cycles.transmission_bounces     = 8
    cycles.volume_bounces           = 2
    cycles.transparent_max_bounces  = 8
 
    # Enforce inverse square light falloff on all lights
    for obj in scene.objects:
        if obj.type == 'LIGHT':
            obj.data.use_custom_distance = False
            if hasattr(obj.data, 'cycles'):
                obj.data.cycles.use_multiple_importance_sampling = True
 
    # Physical volumetrics
    try:
        cycles.volume_step_rate        = 1.0
        cycles.volume_step_rate_render = 1.0
    except Exception:
        pass
 
    print("[Malus Engine] Physical accuracy layer applied.")
 
 
# ---------------------------------------------------------------------------
# Malus Engine — Scene Analysis
# ---------------------------------------------------------------------------
 
def analyse_scene(scene):
    static_names  = []
    dynamic_names = []
    for obj in scene.objects:
        if obj.type not in {'MESH', 'CURVE', 'SURFACE', 'META',
                            'FONT', 'GPENCIL', 'LIGHT', 'EMPTY'}:
            continue
        if _is_dynamic(obj):
            dynamic_names.append(obj.name)
        else:
            static_names.append(obj.name)
    return static_names, dynamic_names
 
 
def _is_dynamic(obj):
    if obj.animation_data and obj.animation_data.action:
        return True
    if obj.parent and _is_dynamic(obj.parent):
        return True
    for mod in obj.modifiers:
        if mod.type == 'ARMATURE' and mod.object:
            if mod.object.animation_data and mod.object.animation_data.action:
                return True
        if mod.type == 'HOOK' and mod.object:
            if mod.object.animation_data and mod.object.animation_data.action:
                return True
    for constraint in obj.constraints:
        if hasattr(constraint, 'target') and constraint.target:
            if constraint.target.animation_data:
                return True
    return False
 
 
# ---------------------------------------------------------------------------
# Malus Engine — Render Operator
# ---------------------------------------------------------------------------
 
class ARC_OT_MalusRender(Operator):
    bl_idname      = "arc_vision.malus_render"
    bl_label       = "Render with Malus Engine"
    bl_description = "Render static and dynamic passes then auto-composite"
 
    def execute(self, context):
        scene  = context.scene
        arc    = scene.arc_vision
        cycles = scene.cycles
 
        # --- Preset is the single source of truth ---
        preset = ARC_RENDER_PRESETS[arc.render_preset]
 
        base_path   = bpy.path.abspath(arc.output_path)
        passes_path = os.path.join(base_path, "passes")
        os.makedirs(passes_path, exist_ok=True)
 
        static_names, dynamic_names = analyse_scene(scene)
        self.report({'INFO'},
            f"[Malus] {len(static_names)} static, {len(dynamic_names)} dynamic objects.")
 
        # ── STATIC PASS ──────────────────────────────────────────────────────
        self.report({'INFO'}, "[Malus] Rendering static pass...")
 
        for name in dynamic_names:
            obj = scene.objects.get(name)
            if obj: obj.hide_render = True
 
        # Use preset static samples — never cycles.samples
        cycles.samples            = preset["static"]
        cycles.adaptive_threshold = preset["threshold"] * 0.5
 
        static_path           = os.path.join(passes_path, "ARC_static_pass")
        scene.render.filepath = static_path
        _set_exr_output(scene)
        bpy.ops.render.render(write_still=True)
 
        for name in dynamic_names:
            obj = scene.objects.get(name)
            if obj: obj.hide_render = False
 
        # ── DYNAMIC PASS ─────────────────────────────────────────────────────
        self.report({'INFO'}, "[Malus] Rendering dynamic pass...")
 
        for name in static_names:
            obj = scene.objects.get(name)
            if obj: obj.hide_render = True
 
        # Use preset dynamic samples — never cycles.samples
        cycles.samples            = preset["dynamic"]
        cycles.adaptive_threshold = preset["threshold"] * 2.0
 
        dynamic_path          = os.path.join(passes_path, "ARC_dynamic_pass")
        scene.render.filepath = dynamic_path
        _set_exr_output(scene)
        bpy.ops.render.render(write_still=True)
 
        for name in static_names:
            obj = scene.objects.get(name)
            if obj: obj.hide_render = False
 
        # ── COMPOSITE ────────────────────────────────────────────────────────
        self.report({'INFO'}, "[Malus] Compositing passes...")
        _composite_passes(
            context,
            static_path  + ".exr",
            dynamic_path + ".exr",
            base_path
        )
 
        # Restore base samples — preset is still source of truth
        cycles.samples            = preset["base"]
        cycles.adaptive_threshold = preset["threshold"]
 
        self.report({'INFO'}, f"[Malus Engine] Done. Output: {base_path}")
        return {'FINISHED'}
 
 
def _set_exr_output(scene):
    img             = scene.render.image_settings
    img.file_format = 'OPEN_EXR_MULTILAYER'
    img.color_depth = '32'
    img.exr_codec   = 'ZIP'
    img.color_mode  = 'RGBA'
 
 
def _composite_passes(context, static_path, dynamic_path, output_path):
    scene = context.scene
    scene.use_nodes = True
    ntree = scene.node_tree
 
    for node in list(ntree.nodes):
        if node.name.startswith("MALUS_"):
            ntree.nodes.remove(node)
 
    links = ntree.links
 
    static_node          = ntree.nodes.new('CompositorNodeImage')
    static_node.name     = "MALUS_StaticPass"
    static_node.location = (-400, 300)
    if os.path.exists(static_path):
        static_node.image = bpy.data.images.load(static_path, check_existing=True)
 
    dynamic_node          = ntree.nodes.new('CompositorNodeImage')
    dynamic_node.name     = "MALUS_DynamicPass"
    dynamic_node.location = (-400, 0)
    if os.path.exists(dynamic_path):
        dynamic_node.image = bpy.data.images.load(dynamic_path, check_existing=True)
 
    ao          = ntree.nodes.new('CompositorNodeAlphaOver')
    ao.name     = "MALUS_AlphaOver"
    ao.location = (-100, 200)
    ao.inputs['Fac'].default_value = 1.0
 
    composite = next((n for n in ntree.nodes if n.type == 'COMPOSITE'), None)
    if not composite:
        composite          = ntree.nodes.new('CompositorNodeComposite')
        composite.location = (200, 200)
 
    links.new(static_node.outputs['Image'],  ao.inputs[1])
    links.new(dynamic_node.outputs['Image'], ao.inputs[2])
    links.new(ao.outputs['Image'],           composite.inputs['Image'])
 
    scene.render.filepath = os.path.join(output_path, "ARC_final_composite")
    bpy.ops.render.render(write_still=True)
    print("[Malus Engine] Composite complete.")
 
 
# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------
 
def apply_lens(self, context):
    cam = get_arc_camera(context.scene)
    if cam:
        cam.data.lens         = float(self.lens_preset)
        cam.data.sensor_width  = ARC_SENSOR_WIDTH
        cam.data.sensor_height = ARC_SENSOR_HEIGHT
        cam.data.sensor_fit    = 'HORIZONTAL'
 
 
def apply_shutter(self, context):
    context.scene.render.motion_blur_shutter  = self.shutter_angle / 360.0
    context.scene.cycles.motion_blur_position = 'CENTER'
 
 
def apply_render_preset(self, context):
    p = ARC_RENDER_PRESETS.get(self.render_preset, ARC_RENDER_PRESETS["QUALITY"])
    c = context.scene.cycles
    # When Malus is active, base is only used for viewport preview.
    # Static/dynamic pass samples are set exclusively inside ARC_OT_MalusRender.
    c.samples            = p["base"]
    c.adaptive_threshold = p["threshold"]
    c.max_bounces        = p["bounces"]
 
 
def apply_output_format(self, context):
    img = context.scene.render.image_settings
    if self.output_format == "DRAFT":
        img.file_format = 'JPEG'
        img.quality     = 92
        img.color_mode  = 'RGB'
    elif self.output_format == "QUALITY":
        img.file_format = 'OPEN_EXR'
        img.color_depth = '16'
        img.exr_codec   = 'ZIP'
        img.color_mode  = 'RGBA'
    elif self.output_format == "PRODUCTION":
        img.file_format = 'OPEN_EXR_MULTILAYER'
        img.color_depth = '32'
        img.exr_codec   = 'ZIP'
        img.color_mode  = 'RGBA'
        vl = context.scene.view_layers[0]
        vl.use_pass_diffuse_color     = True
        vl.use_pass_diffuse_direct    = True
        vl.use_pass_diffuse_indirect  = True
        vl.use_pass_glossy_direct     = True
        vl.use_pass_glossy_indirect   = True
        vl.use_pass_shadow            = True
        vl.use_pass_z                 = True
        vl.use_pass_ambient_occlusion = True
        vl.use_pass_emit              = True
 
 
# ---------------------------------------------------------------------------
# Compositor — ARC Vision Look
# Two colour modes: COOL (Odyssey default) and WARM (Vision3 500T)
# ---------------------------------------------------------------------------
 
def build_arc_compositor(context):
    scene = context.scene
    scene.use_nodes = True
    ntree = scene.node_tree
 
    for node in list(ntree.nodes):
        if node.name.startswith("ARC_"):
            ntree.nodes.remove(node)
 
    rl  = next((n for n in ntree.nodes if n.type == 'R_LAYERS'), None)
    out = next((n for n in ntree.nodes if n.type == 'COMPOSITE'), None)
 
    if not rl:
        rl          = ntree.nodes.new('CompositorNodeRLayers')
        rl.location = (-1000, 400)
    if not out:
        out          = ntree.nodes.new('CompositorNodeComposite')
        out.location = (1200, 400)
 
    links = ntree.links
    arc   = scene.arc_vision
    cool  = arc.colour_temperature == "COOL"
 
    # 1 — Spherical lens distortion
    ld          = ntree.nodes.new('CompositorNodeLensDist')
    ld.name     = "ARC_LensDistortion"
    ld.location = (-800, 400)
    ld.use_fit  = True
    ld.inputs['Distortion'].default_value = 0.015
    ld.inputs['Dispersion'].default_value = 0.004
 
    # 2 — Colour correction
    # COOL: steel blue-grey, desaturated, low contrast midtones
    # WARM: amber lifted shadows, rich mids, Vision3 500T
    cc          = ntree.nodes.new('CompositorNodeColorCorrection')
    cc.name     = "ARC_ColourCorrection"
    cc.location = (-580, 400)
 
    if cool:
        cc.shadows.lift         = 0.05      # lifted but cool
        cc.shadows.saturation   = 0.60      # desaturated shadows
        cc.shadows.gain         = 0.95
        cc.midtones.gain        = 0.97      # slightly dark midtones
        cc.midtones.gamma       = 1.02      # flat, dense
        cc.midtones.saturation  = 0.70      # heavily desaturated mids
        cc.highlights.gain      = 0.90      # restrained highlights
        cc.highlights.saturation = 0.55     # cool, pale highlights
    else:
        cc.shadows.lift         = 0.05      # warm lifted shadows
        cc.shadows.saturation   = 0.85
        cc.midtones.gain        = 1.02
        cc.midtones.gamma       = 0.97      # dense warm mids
        cc.midtones.saturation  = 0.93
        cc.highlights.gain      = 0.95
        cc.highlights.saturation = 0.88
 
    # 3 — Hue/Sat
    hs          = ntree.nodes.new('CompositorNodeHueSat')
    hs.name     = "ARC_HueSat"
    hs.location = (-360, 400)
    hs.inputs['Saturation'].default_value = 0.65 if cool else 0.92
    hs.inputs['Hue'].default_value        = 0.50  # neutral hue shift
 
    # 4 — Colour balance — push cool blue tint in shadows/mids when cool mode
    cb          = ntree.nodes.new('CompositorNodeColorBalance')
    cb.name     = "ARC_ColourBalance"
    cb.location = (-160, 400)
    cb.correction_method = 'LIFT_GAMMA_GAIN'
 
    if cool:
        # Push shadows and mids toward steel blue
        cb.lift  = (0.92, 0.94, 1.04, 1.0)   # cool blue lift
        cb.gamma = (0.94, 0.96, 1.06, 1.0)   # cool blue gamma
        cb.gain  = (0.96, 0.97, 1.02, 1.0)   # slight blue gain
    else:
        # Warm amber push
        cb.lift  = (1.02, 0.99, 0.95, 1.0)   # warm lift
        cb.gamma = (1.02, 1.00, 0.96, 1.0)   # warm gamma
        cb.gain  = (1.01, 1.00, 0.97, 1.0)   # warm gain
 
    # 5 — Vignette
    em          = ntree.nodes.new('CompositorNodeEllipseMask')
    em.name     = "ARC_VignetteMask"
    em.location = (-580, 100)
    em.width = em.height = 0.86
 
    vb          = ntree.nodes.new('CompositorNodeBlur')
    vb.name     = "ARC_VignetteBlur"
    vb.location = (-360, 100)
    vb.size_x = vb.size_y = 90
 
    vi          = ntree.nodes.new('CompositorNodeInvert')
    vi.name     = "ARC_VignetteInvert"
    vi.location = (-160, 100)
 
    vm          = ntree.nodes.new('CompositorNodeMixRGB')
    vm.name     = "ARC_VignetteMix"
    vm.location = (60, 400)
    vm.blend_type = 'MULTIPLY'
    vm.inputs['Fac'].default_value = 0.32
 
    # 6 — Halation — always on
    # Cool mode: halation is blue-white. Warm mode: orange-amber.
    hb          = ntree.nodes.new('CompositorNodeBlur')
    hb.name     = "ARC_HalationBlur"
    hb.location = (-360, -150)
    hb.size_x = hb.size_y = 14
    hb.filter_type = 'GAUSS'
 
    hc          = ntree.nodes.new('CompositorNodeCurveRGB')
    hc.name     = "ARC_HalationCurve"
    hc.location = (-160, -150)
 
    hm          = ntree.nodes.new('CompositorNodeMixRGB')
    hm.name     = "ARC_HalationMix"
    hm.location = (260, 400)
    hm.blend_type = 'SCREEN'
    hm.inputs['Fac'].default_value = 0.06
 
    # 7 — Atmospheric haze
    # Cool: grey-blue mist. Warm: amber haze.
    hz          = ntree.nodes.new('CompositorNodeMixRGB')
    hz.name     = "ARC_Haze"
    hz.location = (460, 400)
    hz.blend_type = 'ADD'
    hz.inputs['Fac'].default_value = 0.018 if cool else 0.013
    if cool:
        hz.inputs[2].default_value = (0.78, 0.82, 0.92, 1.0)   # cool blue-grey mist
    else:
        hz.inputs[2].default_value = (0.95, 0.88, 0.74, 1.0)   # warm amber haze
 
    # 8 — Diffusion — matte behind-glass quality
    db          = ntree.nodes.new('CompositorNodeBlur')
    db.name     = "ARC_DiffusionBlur"
    db.location = (460, 180)
    db.size_x = db.size_y = 3
    db.filter_type = 'GAUSS'
 
    dm          = ntree.nodes.new('CompositorNodeMixRGB')
    dm.name     = "ARC_DiffusionMix"
    dm.location = (660, 400)
    dm.blend_type = 'MIX'
    dm.inputs['Fac'].default_value = 0.03
 
    # 9 — Grain — shadow-intensifying
    gn          = ntree.nodes.new('CompositorNodeTexNoise')
    gn.name     = "ARC_Grain"
    gn.location = (660, 150)
    gn.inputs['Scale'].default_value     = 900.0
    gn.inputs['Detail'].default_value    = 8.0
    gn.inputs['Roughness'].default_value = 0.75
 
    gm          = ntree.nodes.new('CompositorNodeMixRGB')
    gm.name     = "ARC_GrainMix"
    gm.location = (860, 400)
    gm.blend_type = 'OVERLAY'
    gm.inputs['Fac'].default_value = 0.055
 
    # Wire
    links.new(rl.outputs['Image'],  ld.inputs['Image'])
    links.new(ld.outputs['Image'],  cc.inputs['Image'])
    links.new(cc.outputs['Image'],  hs.inputs['Image'])
    links.new(hs.outputs['Image'],  cb.inputs['Image'])
    links.new(cb.outputs['Image'],  vm.inputs[1])
    links.new(em.outputs['Mask'],   vb.inputs['Image'])
    links.new(vb.outputs['Image'],  vi.inputs['Color'])
    links.new(vi.outputs['Color'],  vm.inputs[2])
    links.new(vm.outputs['Image'],  hm.inputs[1])
    links.new(rl.outputs['Image'],  hb.inputs['Image'])
    links.new(hb.outputs['Image'],  hc.inputs['Image'])
    links.new(hc.outputs['Image'],  hm.inputs[2])
    links.new(hm.outputs['Image'],  hz.inputs[1])
    links.new(hz.outputs['Image'],  dm.inputs[1])
    links.new(hz.outputs['Image'],  db.inputs['Image'])
    links.new(db.outputs['Image'],  dm.inputs[2])
    links.new(dm.outputs['Image'],  gm.inputs[1])
    links.new(gn.outputs['Color'],  gm.inputs[2])
    links.new(gm.outputs['Image'],  out.inputs['Image'])
 
    mode = "Cool — Odyssey" if cool else "Warm — Vision3 500T"
    print(f"[ARC Vision] Compositor built — {mode}.")
 
 
# ---------------------------------------------------------------------------
# Settings Guard
# ---------------------------------------------------------------------------
 
def arc_settings_guard(scene):
    if not hasattr(scene, 'arc_vision') or not scene.arc_vision.enabled:
        return
    rd = scene.render
    if rd.resolution_x != ARC_RES_X or rd.resolution_y != ARC_RES_Y:
        rd.resolution_x = ARC_RES_X
        rd.resolution_y = ARC_RES_Y
    expected = {
        "DRAFT":      'JPEG',
        "QUALITY":    'OPEN_EXR',
        "PRODUCTION": 'OPEN_EXR_MULTILAYER',
    }
    if rd.image_settings.file_format != expected.get(scene.arc_vision.output_format):
        apply_output_format(scene.arc_vision, bpy.context)
 
 
# ---------------------------------------------------------------------------
# Safe Pack
# ---------------------------------------------------------------------------
 
def safe_pack_all():
    for img in bpy.data.images:
        if img.packed_file is None and img.filepath:
            try: img.pack()
            except Exception: pass
    for font in bpy.data.fonts:
        if font.packed_file is None and font.filepath not in ('', '<builtin>'):
            try: font.pack()
            except Exception: pass
    print("[ARC Vision] Assets packed.")
 
 
def arc_auto_pack(dummy):
    scene = bpy.context.scene
    if hasattr(scene, 'arc_vision') and scene.arc_vision.enabled:
        safe_pack_all()
 
 
# ---------------------------------------------------------------------------
# Camera
# ---------------------------------------------------------------------------
 
def get_arc_camera(scene):
    for obj in scene.objects:
        if obj.type == 'CAMERA' and obj.get("arc_vision_camera"):
            return obj
    return None
 
 
class ARC_OT_AddCamera(Operator):
    bl_idname      = "arc_vision.add_camera"
    bl_label       = "Add ARC Camera"
    bl_description = "Add the ARC Vision 65mm large format camera"
 
    def execute(self, context):
        scene = context.scene
        if get_arc_camera(scene):
            self.report({'WARNING'}, "ARC Vision camera already exists.")
            return {'CANCELLED'}
 
        d               = bpy.data.cameras.new("ARC_Vision_Camera")
        d.lens          = float(scene.arc_vision.lens_preset)
        d.sensor_width  = ARC_SENSOR_WIDTH
        d.sensor_height = ARC_SENSOR_HEIGHT
        d.sensor_fit    = 'HORIZONTAL'
        d.dof.use_dof           = True
        d.dof.aperture_fstop    = 2.8
        d.dof.aperture_blades   = 8
        d.dof.aperture_rotation = 0.0
        d.dof.aperture_ratio    = 1.0
        d.show_passepartout     = True
        d.passepartout_alpha    = 0.85
 
        cam                    = bpy.data.objects.new("ARC_Vision_Camera", d)
        cam["arc_vision_camera"] = True
 
        if scene.camera:
            cam.location       = scene.camera.location.copy()
            cam.rotation_euler = scene.camera.rotation_euler.copy()
        else:
            cam.location       = (0, -8, 2)
            cam.rotation_euler = (math.radians(80), 0, 0)
 
        scene.collection.objects.link(cam)
        scene.camera = cam
        scene.arc_vision.arc_camera_exists = True
        self.report({'INFO'}, "ARC Vision camera added.")
        return {'FINISHED'}
 
 
# ---------------------------------------------------------------------------
# Package
# ---------------------------------------------------------------------------
 
class ARC_OT_PackageForRender(Operator):
    bl_idname      = "arc_vision.package_for_render"
    bl_label       = "Package for ARC Render"
    bl_description = "Bake all ARC Vision settings into .blend — farm-ready"
 
    def execute(self, context):
        safe_pack_all()
        build_arc_compositor(context)
        arc = context.scene.arc_vision
        apply_lens(arc, context)
        apply_shutter(arc, context)
        apply_render_preset(arc, context)
        apply_output_format(arc, context)
        self.report({'INFO'}, "ARC Vision: Packaged and farm-ready.")
        return {'FINISHED'}
 
 
# ---------------------------------------------------------------------------
# UI — Properties Panel
# ---------------------------------------------------------------------------
 
class ARC_PT_MainPanel(Panel):
    bl_label       = ""
    bl_idname      = "ARC_PT_main"
    bl_space_type  = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context     = "render"
    bl_options     = {'HIDE_HEADER'}
 
    def draw(self, context):
        layout = self.layout
        arc    = context.scene.arc_vision
 
        header = layout.box()
        row    = header.row(align=True)
        row.scale_y = 1.6
        row.label(text="  ARC  VISION", icon='CAMERA_DATA')
        r = row.row()
        r.alignment = 'RIGHT'
        r.prop(arc, "enabled",
               text="● ON" if arc.enabled else "○ OFF",
               toggle=True)
        sub = header.row()
        sub.alignment = 'CENTER'
        sub.scale_y   = 0.65
        sub.label(text="ADVANCED RENDER CINEMATICS  ·  TENET")
 
        if not arc.enabled:
            layout.separator(factor=0.5)
            layout.box().label(text="Enable ARC Vision to begin.", icon='INFO')
            return
 
        layout.separator(factor=0.4)
        stamp = layout.box()
        stamp.scale_y = 0.78
        c = stamp.column(align=True)
        c.label(text="MALUS ENGINE  ·  65mm  ·  1.76:1  ·  Vision3 500T")
        mode_text = "Cool — Odyssey" if arc.colour_temperature == "COOL" else "Warm — Vision3 500T"
        c.label(text=f"Grade: {mode_text}  ·  Halation  ·  Diffusion  ·  Grain")
 
 
class ARC_PT_CameraPanel(Panel):
    bl_label       = "CAMERA"
    bl_idname      = "ARC_PT_camera"
    bl_space_type  = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context     = "render"
    bl_parent_id   = "ARC_PT_main"
    bl_options     = {'DEFAULT_CLOSED'}
 
    @classmethod
    def poll(cls, context):
        return context.scene.arc_vision.enabled
 
    def draw_header(self, context):
        self.layout.label(text="", icon='CAMERA_DATA')
 
    def draw(self, context):
        layout = self.layout
        arc    = context.scene.arc_vision
        cam    = get_arc_camera(context.scene)
 
        if cam:
            layout.box().label(text=cam.name, icon='CHECKMARK')
            layout.separator(factor=0.3)
            col = layout.column(align=True)
            col.scale_y = 1.2
            col.prop(arc, "lens_preset",   text="Lens")
            col.prop(arc, "shutter_angle", text="Shutter °")
            layout.separator(factor=0.4)
            layout.box().label(text="Camera Rig  —  Coming Soon", icon='ARMATURE_DATA')
        else:
            layout.box().label(text="No ARC camera in scene.", icon='ERROR')
            layout.separator(factor=0.3)
            layout.operator("arc_vision.add_camera",
                            text="ADD ARC CAMERA", icon='ADD')
 
 
class ARC_PT_MalusPanel(Panel):
    bl_label       = "MALUS ENGINE"
    bl_idname      = "ARC_PT_malus"
    bl_space_type  = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context     = "render"
    bl_parent_id   = "ARC_PT_main"
    bl_options     = {'DEFAULT_CLOSED'}
 
    @classmethod
    def poll(cls, context):
        return context.scene.arc_vision.enabled
 
    def draw_header(self, context):
        self.layout.label(text="", icon='PHYSICS')
 
    def draw(self, context):
        layout = self.layout
        arc    = context.scene.arc_vision
        preset = ARC_RENDER_PRESETS[arc.render_preset]
 
        col = layout.column(align=True)
        col.scale_y = 1.2
        col.prop(arc, "render_preset", text="Quality")
 
        layout.separator(factor=0.4)
 
        passes = layout.box()
        passes.scale_y = 0.8
        c = passes.column(align=True)
        c.label(text=f"Static Pass    ·  {preset['static']} samples",  icon='MESH_DATA')
        c.label(text=f"Dynamic Pass   ·  {preset['dynamic']} samples", icon='ARMATURE_DATA')
        c.label(text=f"Threshold      ·  {preset['threshold']}",       icon='INFO')
 
        layout.separator(factor=0.4)
        layout.prop(arc, "output_path", text="Output")
        layout.separator(factor=0.4)
        layout.operator("arc_vision.malus_render",
                        text="RENDER WITH MALUS ENGINE", icon='RENDER_STILL')
        layout.separator(factor=0.3)
        note = layout.box()
        note.scale_y = 0.72
        note.label(text="Static pass first at high samples.", icon='INFO')
        note.label(text="Dynamic pass second at efficient samples.")
        note.label(text="Auto-composites and saves all passes.")
 
 
class ARC_PT_GradePanel(Panel):
    bl_label       = "COLOUR GRADE"
    bl_idname      = "ARC_PT_grade"
    bl_space_type  = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context     = "render"
    bl_parent_id   = "ARC_PT_main"
    bl_options     = {'DEFAULT_CLOSED'}
 
    @classmethod
    def poll(cls, context):
        return context.scene.arc_vision.enabled
 
    def draw_header(self, context):
        self.layout.label(text="", icon='COLOR')
 
    def draw(self, context):
        layout = self.layout
        arc    = context.scene.arc_vision
 
        col = layout.column(align=True)
        col.scale_y = 1.2
        col.prop(arc, "colour_temperature", text="Grade")
 
        layout.separator(factor=0.4)
        hint = layout.box()
        hint.scale_y = 0.75
        if arc.colour_temperature == "COOL":
            hint.label(text="Steel blue-grey  ·  Desaturated  ·  Dense", icon='INFO')
            hint.label(text="Low contrast mids  ·  Cool pale highlights")
        else:
            hint.label(text="Amber organic  ·  Warm mids  ·  Rich shadows", icon='INFO')
            hint.label(text="Soft highlight rolloff  ·  Vision3 500T character")
 
 
class ARC_PT_OutputPanel(Panel):
    bl_label       = "OUTPUT"
    bl_idname      = "ARC_PT_output"
    bl_space_type  = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context     = "render"
    bl_parent_id   = "ARC_PT_main"
    bl_options     = {'DEFAULT_CLOSED'}
 
    @classmethod
    def poll(cls, context):
        return context.scene.arc_vision.enabled
 
    def draw_header(self, context):
        self.layout.label(text="", icon='IMAGE_DATA')
 
    def draw(self, context):
        layout = self.layout
        arc    = context.scene.arc_vision
 
        col = layout.column(align=True)
        col.scale_y = 1.2
        col.prop(arc, "output_format", text="Format")
 
        layout.separator(factor=0.4)
        hint = layout.box()
        hint.scale_y = 0.75
        if arc.output_format == "DRAFT":
            hint.label(text="JPEG 92%  ·  RGB  ·  Client previews", icon='INFO')
        elif arc.output_format == "QUALITY":
            hint.label(text="EXR 16-bit  ·  RGBA  ·  Production", icon='INFO')
        elif arc.output_format == "PRODUCTION":
            hint.label(text="EXR 32-bit Multilayer  ·  All passes  ·  Delivery", icon='INFO')
 
 
class ARC_PT_ExportPanel(Panel):
    bl_label       = "EXPORT"
    bl_idname      = "ARC_PT_export"
    bl_space_type  = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context     = "render"
    bl_parent_id   = "ARC_PT_main"
    bl_options     = {'DEFAULT_CLOSED'}
 
    @classmethod
    def poll(cls, context):
        return context.scene.arc_vision.enabled
 
    def draw_header(self, context):
        self.layout.label(text="", icon='EXPORT')
 
    def draw(self, context):
        layout = self.layout
        layout.operator("arc_vision.package_for_render",
                        text="PACKAGE FOR ARC RENDER", icon='EXPORT')
        layout.separator(factor=0.4)
        note = layout.box()
        note.scale_y = 0.75
        note.label(text="Bakes all settings into .blend.", icon='INFO')
        note.label(text="Farm-ready. No add-on needed on farm.")
 
 
# ---------------------------------------------------------------------------
# UI — N-Panel
# ---------------------------------------------------------------------------
 
class ARC_PT_NPanel(Panel):
    bl_label       = "ARC Vision"
    bl_idname      = "ARC_PT_npanel"
    bl_space_type  = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category    = "ARC"
 
    def draw(self, context):
        layout = self.layout
        arc    = context.scene.arc_vision
 
        header = layout.box()
        row    = header.row(align=True)
        row.scale_y = 1.5
        row.label(text="ARC  VISION", icon='CAMERA_DATA')
        header.prop(arc, "enabled",
                    text="● ON" if arc.enabled else "○ OFF",
                    toggle=True)
 
        if not arc.enabled:
            return
 
        layout.separator(factor=0.3)
 
        cam_box = layout.box()
        cam_box.label(text="CAMERA", icon='CAMERA_DATA')
        cam = get_arc_camera(context.scene)
        if cam:
            cam_box.prop(arc, "lens_preset",   text="Lens")
            cam_box.prop(arc, "shutter_angle", text="Shutter °")
        else:
            cam_box.operator("arc_vision.add_camera",
                             text="ADD ARC CAMERA", icon='ADD')
 
        layout.separator(factor=0.3)
 
        malus = layout.box()
        malus.label(text="MALUS ENGINE", icon='PHYSICS')
        malus.prop(arc, "render_preset",       text="Quality")
        malus.prop(arc, "colour_temperature",  text="Grade")
        malus.prop(arc, "output_format",       text="Format")
 
        layout.separator(factor=0.3)
        layout.operator("arc_vision.malus_render",
                        text="RENDER WITH MALUS", icon='RENDER_STILL')
        layout.operator("arc_vision.package_for_render",
                        text="PACKAGE FOR RENDER", icon='EXPORT')
 
 
# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
 
classes = [
    ARCVisionSettings,
    ARC_OT_AddCamera,
    ARC_OT_MalusRender,
    ARC_OT_PackageForRender,
    ARC_PT_MainPanel,
    ARC_PT_CameraPanel,
    ARC_PT_MalusPanel,
    ARC_PT_GradePanel,
    ARC_PT_OutputPanel,
    ARC_PT_ExportPanel,
    ARC_PT_NPanel,
]
 
 
def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.arc_vision = bpy.props.PointerProperty(type=ARCVisionSettings)
    bpy.app.handlers.save_pre.append(arc_auto_pack)
    bpy.app.handlers.depsgraph_update_post.append(arc_settings_guard)
    print("[ARC Vision] v2.1 Registered — Malus Engine ready.")
 
 
def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.arc_vision
    if arc_auto_pack in bpy.app.handlers.save_pre:
        bpy.app.handlers.save_pre.remove(arc_auto_pack)
    if arc_settings_guard in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(arc_settings_guard)
    print("[ARC Vision] Unregistered.")
 
 
if __name__ == "__main__":
    register()
 