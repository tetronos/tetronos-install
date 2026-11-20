'''
tetronos-install main spec
'''

from libspec import Spec
from . import install


class MainSpec(Spec):
    def modules(self):
        return [install]
