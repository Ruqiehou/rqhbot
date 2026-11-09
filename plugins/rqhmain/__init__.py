from .main import RqhmainPlugin


def setup(bot):
    """插件入口函数"""
    plugin = RqhmainPlugin()
    bot.register_plugin(plugin)

__all__ = ["RqhmainPlugin"]
