import importlib
import logging
import os
import sys
from shellmate.config.defaults import get_default_config

logger = logging.getLogger("shellmate.plugins")


def discover_plugins():
    config = get_default_config()
    plugin_dir = config["plugins"]["directory"]

    if not os.path.isdir(plugin_dir):
        return []

    if plugin_dir not in sys.path:
        sys.path.insert(0, plugin_dir)

    plugins = []
    for item in sorted(os.listdir(plugin_dir)):
        item_path = os.path.join(plugin_dir, item)
        if os.path.isdir(item_path) and os.path.exists(os.path.join(item_path, "__init__.py")):
            try:
                module = importlib.import_module(item)
                if hasattr(module, "register_plugin"):
                    plugin = module.register_plugin()
                    plugins.append(plugin)
                    logger.info(f"Loaded plugin: {plugin.name} v{plugin.version}")
                else:
                    logger.debug(f"Skipping {item}: no register_plugin() function")
            except Exception as e:
                logger.error(f"Failed to load plugin {item}: {e}")

    return plugins


def load_plugin_class(entry_point: str):
    module_name, class_name = entry_point.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, class_name)()
