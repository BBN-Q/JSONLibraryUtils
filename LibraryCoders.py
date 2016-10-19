'''
JSON encoders and decoders.

Copyright 2016 Raytheon BBN Technologies
'''

import json, sys

from atom.api import Atom

class LibraryEncoder(json.JSONEncoder):
    """
    Helper for QLab to encode all the classes we use.
    """
    def default(self, obj):
        if isinstance(obj, Atom):
            #Check for a json_encode option
            try:
                jsonDict = obj.json_encode()
            except AttributeError:
                jsonDict = obj.__getstate__()
            except:
                print("Unexpected error encoding to JSON")
                raise

            #Inject the class name for decoding
            jsonDict['x__class__'] = obj.__class__.__name__
            jsonDict['x__module__'] = obj.__class__.__module__

            return jsonDict

        else:
            return super(LibraryEncoder, self).default(obj)

class LibraryDecoder(json.JSONDecoder):

    def __init__(self, **kwargs):
        super(LibraryDecoder, self).__init__(object_hook=self.dict_to_obj, **kwargs)

    def dict_to_obj(self, jsonDict):
        if 'x__class__' in jsonDict or '__class__' in jsonDict:
            #Pop the class and module
            className = jsonDict.pop('x__class__', None)
            if not className:
                className = jsonDict.pop('__class__')
            moduleName = jsonDict.pop('x__module__', None)
            if not moduleName:
                moduleName = jsonDict.pop('__module__')

            __import__(moduleName)

            #Re-encode the strings as ascii for Python 2
            if sys.version_info[0] < 3:
                jsonDict = {k.encode('ascii'):v for k,v in jsonDict.items()}
            inst = getattr(sys.modules[moduleName], className)()
            if hasattr(inst, 'update_from_jsondict'):
                inst.update_from_jsondict(jsonDict)
            else:
                inst = getattr(sys.modules[moduleName], className)(**jsonDict)

            return inst
        else:
            return jsonDict
