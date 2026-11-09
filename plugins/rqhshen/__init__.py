from .main import RqhshenPlugin


def setup(bot):
    """插件入口函数"""
    plugin = RqhshenPlugin()
    bot.register_plugin(plugin)

__all__ = ["RqhshenPlugin"]
