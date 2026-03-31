bl_info = {
    "name": "ARC Vision",
    "author": "TENET",
    "version": (3, 2, 0),
    "blender": (5, 0, 1),
    "category": "Render",
}

from .arc_core import register_core, unregister_core
from .arc_ai import register_ai, unregister_ai
from .arc_ui import register_ui, unregister_ui

def register():
    register_core()
    register_ai()
    register_ui()

def unregister():
    unregister_ui()
    unregister_ai()
    unregister_core()