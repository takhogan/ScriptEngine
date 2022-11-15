import platform

def os_normalize_path(path):
    return path if platform.system() == 'Windows' else path.replace('\\', '/')