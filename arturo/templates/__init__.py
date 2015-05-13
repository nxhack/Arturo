#  _____     _               
# |  _  |___| |_ _ _ ___ ___ 
# |     |  _|  _| | |  _| . |
# |__|__|_| |_| |___|_| |___|
# http://32bits.io/Arturo/
#
import os

from arturo import __app_name__, __lib_name__
import jinja2
from jinja2.loaders import PackageLoader


class JinjaTemplates(object):
    
    JINJASUFFIX = ".jinja"
    
    MAKEFILE_LOCALPATHS = "LocalPaths.mk"
    MAKEFILE_TARGETS    = "MakeTargets.mk"
    MAKEFILE            = "Makefile"
    
    @classmethod
    def getRelPathToTemplatesFromPackage(cls):
        return os.path.relpath(os.path.dirname(__file__), __lib_name__)
    
    @classmethod
    def createJinjaEnvironmentForTemplates(cls):
        env = jinja2.Environment(loader=PackageLoader(__lib_name__, cls.getRelPathToTemplatesFromPackage()))
        env.globals['templates'] = {
            'make_toolchain':cls.MAKEFILE_LOCALPATHS,
            'make_targets':cls.MAKEFILE_TARGETS,
            'makefile':cls.MAKEFILE
        }
        return env
        
    @classmethod
    def getTemplate(cls, jinjaEnvironment, templateName):
        return jinjaEnvironment.get_template(templateName + cls.JINJASUFFIX)