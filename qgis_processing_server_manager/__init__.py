def classFactory(iface):
    from .plugin import ProcessingServerManagerPlugin

    return ProcessingServerManagerPlugin(iface)
