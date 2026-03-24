bl_info = {
    "name": "ARC Vision",
    "author": "TENET",
    "version": (1, 1, 0),
    "blender": (4, 0, 0),
    "location": "Properties > Render > ARC Vision  |  N-Panel > ARC",
    "description": "ARC Vision — Advanced Render Cinematics by TENET. 65mm large format film simulation.",
    "category": "Render",
}
 
import bpy
import math
from bpy.props import BoolProperty, EnumProperty, FloatProperty
from bpy.types import Panel, Operator, PropertyGroup
 
 
# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
 
ARC_SENSOR_WIDTH  = 54.12
ARC_SENSOR_HEIGHT = 29.25
ARC_ASPECT        = 1.85
ARC_RES_X         = 4096
ARC_RES_Y         = int(ARC_RES_X / ARC_ASPECT)  # 2214
 
ARC_LENS_PRESETS = [
    ("24",  "24mm — Extreme Wide",  "Establishing shots, environments"),
    ("35",  "35mm — Wide",          "Most common narrative lens"),
    ("50",  "50mm — Normal",        "Closest to human eye on 65mm"),
    ("75",  "75mm — Short Tele",    "Portraits and mid shots"),
    ("100", "100mm — Telephoto",    "Compression and close-ups"),
]
 
ARC_RENDER_PRESETS = {
    "PREVIEW":  {"samples": 64,   "threshold": 0.1,   "bounces": 8,  "hint": "64 samples  ·  Quick checks"},
    "STANDARD": {"samples": 512,  "threshold": 0.01,  "bounces": 12, "hint": "512 samples  ·  Production"},
    "PREMIUM":  {"samples": 2048, "threshold": 0.001, "bounces": 16, "hint": "2048 samples  ·  Final delivery"},
}
 
 
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
            ("PREVIEW",  "Preview",  "Fast draft"),
            ("STANDARD", "Standard", "Balanced production"),
            ("PREMIUM",  "Premium",  "Final delivery"),
        ],
        default="STANDARD",
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
            ("PREVIEW",  "Preview — JPEG",                    "JPEG for client previews"),
            ("STANDARD", "Standard — OpenEXR 16-bit",         "Half float EXR, production"),
            ("MASTER",   "Master — OpenEXR Multilayer 32-bit", "Full float, all passes, archival"),
        ],
        default="STANDARD",
        update=lambda self, ctx: apply_output_format(self, ctx)
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
 
    rd.resolution_x   = ARC_RES_X
    rd.resolution_y   = ARC_RES_Y
    rd.pixel_aspect_x = 1.0
    rd.pixel_aspect_y = 1.0
 
    rd.engine = 'CYCLES'
    try:
        cycles.device = 'GPU'
        bpy.context.preferences.addons['cycles'].preferences.compute_device_type = 'CUDA'
    except Exception:
        pass
 
    cycles.use_adaptive_sampling   = True
    cycles.adaptive_threshold      = 0.01
    cycles.samples                 = 512
    cycles.use_denoising           = True
    cycles.denoiser                = 'OPENIMAGEDENOISE'
    cycles.max_bounces             = 12
    cycles.diffuse_bounces         = 4
    cycles.glossy_bounces          = 4
    cycles.transmission_bounces    = 8
    cycles.volume_bounces          = 2
    cycles.transparent_max_bounces = 8
    cycles.caustics_reflective     = True
    cycles.caustics_refractive     = True
 
    scene.view_settings.view_transform = 'Filmic'
    scene.view_settings.look           = 'Filmic - Soft Contrast'
    scene.view_settings.exposure       = 0.0
    scene.view_settings.gamma          = 1.0
    try:
        scene.sequencer_colorspace_settings.name = 'Filmic Log'
    except Exception:
        pass
 
    apply_shutter(scene.arc_vision, context)
    apply_lens(scene.arc_vision, context)
    apply_output_format(scene.arc_vision, context)
    build_arc_compositor(context)
    safe_pack_all()
 
    print("[ARC Vision] Activated — ARC Engine running.")
 
 
def deactivate_arc_vision(context):
    scene = context.scene
    if scene.use_nodes:
        for node in list(scene.node_tree.nodes):
            if node.name.startswith("ARC_"):
                scene.node_tree.nodes.remove(node)
    print("[ARC Vision] Deactivated.")
 
 
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
    context.scene.render.motion_blur_shutter = self.shutter_angle / 360.0
    context.scene.cycles.motion_blur_position = 'CENTER'
 
 
def apply_render_preset(self, context):
    p = ARC_RENDER_PRESETS.get(self.render_preset, ARC_RENDER_PRESETS["STANDARD"])
    c = context.scene.cycles
    c.samples            = p["samples"]
    c.adaptive_threshold = p["threshold"]
    c.max_bounces        = p["bounces"]
 
 
def apply_output_format(self, context):
    img = context.scene.render.image_settings
    if self.output_format == "PREVIEW":
        img.file_format = 'JPEG'
        img.quality     = 92
        img.color_mode  = 'RGB'
    elif self.output_format == "STANDARD":
        img.file_format = 'OPEN_EXR'
        img.color_depth = '16'
        img.exr_codec   = 'ZIP'
        img.color_mode  = 'RGBA'
    elif self.output_format == "MASTER":
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
# Compositor
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
        rl = ntree.nodes.new('CompositorNodeRLayers')
        rl.location = (-1000, 400)
    if not out:
        out = ntree.nodes.new('CompositorNodeComposite')
        out.location = (1200, 400)
 
    links = ntree.links
 
    # 1 — Spherical lens distortion
    ld = ntree.nodes.new('CompositorNodeLensDist')
    ld.name = "ARC_LensDistortion"
    ld.location = (-800, 400)
    ld.use_fit  = True
    ld.inputs['Distortion'].default_value = 0.015
    ld.inputs['Dispersion'].default_value = 0.004
 
    # 2 — Vision3 500T colour correction
    cc = ntree.nodes.new('CompositorNodeColorCorrection')
    cc.name = "ARC_ColourCorrection"
    cc.location = (-580, 400)
    cc.shadows.lift         = 0.05
    cc.shadows.saturation   = 0.85
    cc.midtones.gain        = 1.02
    cc.midtones.gamma       = 0.97
    cc.midtones.saturation  = 0.93
    cc.highlights.gain      = 0.95
    cc.highlights.saturation = 0.88
 
    # 3 — Hue/Sat
    hs = ntree.nodes.new('CompositorNodeHueSat')
    hs.name = "ARC_HueSat"
    hs.location = (-360, 400)
    hs.inputs['Saturation'].default_value = 0.92
 
    # 4 — Vignette
    em = ntree.nodes.new('CompositorNodeEllipseMask')
    em.name = "ARC_VignetteMask"
    em.location = (-580, 100)
    em.width = em.height = 0.86
 
    vb = ntree.nodes.new('CompositorNodeBlur')
    vb.name = "ARC_VignetteBlur"
    vb.location = (-360, 100)
    vb.size_x = vb.size_y = 90
 
    vi = ntree.nodes.new('CompositorNodeInvert')
    vi.name = "ARC_VignetteInvert"
    vi.location = (-160, 100)
 
    vm = ntree.nodes.new('CompositorNodeMixRGB')
    vm.name = "ARC_VignetteMix"
    vm.location = (-140, 400)
    vm.blend_type = 'MULTIPLY'
    vm.inputs['Fac'].default_value = 0.30
 
    # 5 — Halation (always on)
    hb = ntree.nodes.new('CompositorNodeBlur')
    hb.name = "ARC_HalationBlur"
    hb.location = (-360, -150)
    hb.size_x = hb.size_y = 14
    hb.filter_type = 'GAUSS'
 
    hc = ntree.nodes.new('CompositorNodeCurveRGB')
    hc.name = "ARC_HalationCurve"
    hc.location = (-160, -150)
 
    hm = ntree.nodes.new('CompositorNodeMixRGB')
    hm.name = "ARC_HalationMix"
    hm.location = (60, 400)
    hm.blend_type = 'SCREEN'
    hm.inputs['Fac'].default_value = 0.07
 
    # 6 — Atmospheric haze
    hz = ntree.nodes.new('CompositorNodeMixRGB')
    hz.name = "ARC_Haze"
    hz.location = (260, 400)
    hz.blend_type = 'ADD'
    hz.inputs['Fac'].default_value = 0.013
    hz.inputs[2].default_value = (0.95, 0.88, 0.74, 1.0)
 
    # 7 — Diffusion (matte behind-glass quality)
    db = ntree.nodes.new('CompositorNodeBlur')
    db.name = "ARC_DiffusionBlur"
    db.location = (260, 180)
    db.size_x = db.size_y = 3
    db.filter_type = 'GAUSS'
 
    dm = ntree.nodes.new('CompositorNodeMixRGB')
    dm.name = "ARC_DiffusionMix"
    dm.location = (460, 400)
    dm.blend_type = 'MIX'
    dm.inputs['Fac'].default_value = 0.03
 
    # 8 — Grain (shadow-intensifying)
    gn = ntree.nodes.new('CompositorNodeTexNoise')
    gn.name = "ARC_Grain"
    gn.location = (460, 150)
    gn.inputs['Scale'].default_value     = 900.0
    gn.inputs['Detail'].default_value    = 8.0
    gn.inputs['Roughness'].default_value = 0.75
 
    gm = ntree.nodes.new('CompositorNodeMixRGB')
    gm.name = "ARC_GrainMix"
    gm.location = (660, 400)
    gm.blend_type = 'OVERLAY'
    gm.inputs['Fac'].default_value = 0.055
 
    # Wire
    links.new(rl.outputs['Image'],  ld.inputs['Image'])
    links.new(ld.outputs['Image'],  cc.inputs['Image'])
    links.new(cc.outputs['Image'],  hs.inputs['Image'])
    links.new(hs.outputs['Image'],  vm.inputs[1])
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
 
    print("[ARC Vision] Compositor built.")
 
 
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
    expected = {"PREVIEW": 'JPEG', "STANDARD": 'OPEN_EXR', "MASTER": 'OPEN_EXR_MULTILAYER'}
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
    bl_description = "Add the ARC Vision large format camera to the scene"
 
    def execute(self, context):
        scene = context.scene
        if get_arc_camera(scene):
            self.report({'WARNING'}, "ARC Vision camera already exists.")
            return {'CANCELLED'}
 
        d = bpy.data.cameras.new("ARC_Vision_Camera")
        d.lens = float(scene.arc_vision.lens_preset)
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
 
        cam = bpy.data.objects.new("ARC_Vision_Camera", d)
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
        row = header.row(align=True)
        row.scale_y = 1.6
        row.label(text="  ARC  VISION", icon='CAMERA_DATA')
        r = row.row()
        r.alignment = 'RIGHT'
        r.prop(arc, "enabled", text="● ON" if arc.enabled else "○ OFF", toggle=True)
        sub = header.row()
        sub.alignment = 'CENTER'
        sub.scale_y = 0.65
        sub.label(text="ADVANCED RENDER CINEMATICS  ·  TENET")
 
        if not arc.enabled:
            layout.separator(factor=0.5)
            layout.box().label(text="Enable ARC Vision to begin.", icon='INFO')
            return
 
        layout.separator(factor=0.4)
        stamp = layout.box()
        stamp.scale_y = 0.78
        c = stamp.column(align=True)
        c.label(text="ARC ENGINE  ·  65mm  ·  1.85:1  ·  Vision3 500T")
        c.label(text="Halation  ·  Grain  ·  Diffusion  ·  Spherical  ·  GPU+CPU")
 
 
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
            layout.operator("arc_vision.add_camera", text="ADD ARC CAMERA", icon='ADD')
 
 
class ARC_PT_RenderPanel(Panel):
    bl_label       = "RENDER"
    bl_idname      = "ARC_PT_render"
    bl_space_type  = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context     = "render"
    bl_parent_id   = "ARC_PT_main"
    bl_options     = {'DEFAULT_CLOSED'}
 
    @classmethod
    def poll(cls, context):
        return context.scene.arc_vision.enabled
 
    def draw_header(self, context):
        self.layout.label(text="", icon='RENDER_STILL')
 
    def draw(self, context):
        layout = self.layout
        arc    = context.scene.arc_vision
        col = layout.column(align=True)
        col.scale_y = 1.2
        col.prop(arc, "render_preset", text="Quality")
        layout.separator(factor=0.4)
        hint = layout.box()
        hint.scale_y = 0.75
        hint.label(text=ARC_RENDER_PRESETS[arc.render_preset]["hint"], icon='INFO')
 
 
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
        if arc.output_format == "PREVIEW":
            hint.label(text="JPEG 92%  ·  RGB  ·  Client previews", icon='INFO')
        elif arc.output_format == "STANDARD":
            hint.label(text="EXR 16-bit  ·  RGBA  ·  Production", icon='INFO')
        elif arc.output_format == "MASTER":
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
# UI — N-Panel (press N in viewport)
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
            cam_box.operator("arc_vision.add_camera", text="ADD ARC CAMERA", icon='ADD')
 
        layout.separator(factor=0.3)
 
        rnd = layout.box()
        rnd.label(text="RENDER  ·  OUTPUT", icon='RENDER_STILL')
        rnd.prop(arc, "render_preset",  text="Quality")
        rnd.prop(arc, "output_format",  text="Format")
 
        layout.separator(factor=0.3)
        layout.operator("arc_vision.package_for_render",
                        text="PACKAGE FOR RENDER", icon='EXPORT')
 
 
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
    ARC_PT_NPanel,
]
 
 
def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.arc_vision = bpy.props.PointerProperty(type=ARCVisionSettings)
    bpy.app.handlers.save_pre.append(arc_auto_pack)
    bpy.app.handlers.depsgraph_update_post.append(arc_settings_guard)
    print("[ARC Vision] Registered.")
 
 
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
 