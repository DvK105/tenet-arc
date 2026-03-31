bl_info = {
    "name": "ARC Vision",
    "author": "TENET",
    "version": (3, 0, 0),
    "blender": (4, 0, 0),
    "category": "Render",
}

from .arc_core import register_core, unregister_core
from .arc_ui import register_ui, unregister_ui
from .arc_ai import register_ai, unregister_ai

def register():
    register_core()
    register_ai()
    register_ui()

def unregister():
    unregister_ui()
    unregister_ai()
    unregister_core()