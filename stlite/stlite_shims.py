"""Import stubs so lokigi imports inside Pyodide (stlite build only).

lokigi's __init__ eagerly imports mapping/spatial modules (geopandas, contextily, pysal, ...)
that tab 3 never uses and that Pyodide can't install. Under emscripten this puts a finder
first on sys.meta_path that answers for those names with empty stand-in modules.
Does nothing anywhere else.
"""

import importlib.abc
import importlib.machinery
import sys
import types

STUBBED = {
    "geopandas", "shapely", "contextily", "esda", "pysal", "libpysal",
    "folium", "branca", "adjustText", "tqdm", "joblib", "requests",
    "osmium", "polyline", "valhalla", "r5py", "numba", "llvmlite",
}


class _StubModule(types.ModuleType):
    __path__ = []  # lets submodules (pysal.lib, requests.exceptions, ...) resolve

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        # Works for `from x import Y`, subclassing and `except Y`
        cls = type(name, (Exception,), {})
        setattr(self, name, cls)
        return cls


class _StubFinder(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split(".")[0] in STUBBED:
            return importlib.machinery.ModuleSpec(fullname, self, is_package=True)
        return None

    def create_module(self, spec):
        return _StubModule(spec.name)

    def exec_module(self, module):
        pass


if sys.platform == "emscripten" and not any(isinstance(f, _StubFinder) for f in sys.meta_path):
    sys.meta_path.insert(0, _StubFinder())
