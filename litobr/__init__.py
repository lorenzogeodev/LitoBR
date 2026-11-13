# -*- coding: utf-8 -*-
def classFactory(iface):
    from .plugin import LitoBRPlugin
    return LitoBRPlugin(iface)
