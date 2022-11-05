

from abc import ABCMeta
from typing import cast, Tuple, Type, TypeVar, ClassVar

from .ids import PersonID
from .location_base import BaseLocation
from .location_rules import LocationRule, BusinessLocationRule, NonEssentialBusinessLocationRule
from .location_states import LocationState
from .pandemic_types import DEFAULT
from .sim_time import SimTime, SimTimeTuple


__all__ = ['ApartmentBaseLocation']
_ApartmentState = TypeVar('_ApartmentState', bound=ApartmentState)

class ApartmentBaseLocation(BaseLocation[_ApartmentState],metaclass=ABCMeta):
    _apartments: []
    def __init__(self):
        self._apartments = []
        