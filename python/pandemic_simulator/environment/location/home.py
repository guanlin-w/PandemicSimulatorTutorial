# Confidential, Copyright 2020, Sony Corporation of America, All rights reserved.

from dataclasses import dataclass

from ..interfaces import LocationState, Location, ContactRate, SimTime, SimTimeTuple, LocationRule, globals, BaseLocation

__all__ = ['Home', 'HomeState']


@dataclass
class HomeState(LocationState):
    contact_rate: ContactRate = ContactRate(0, 1, 0, 0.5, 0.3, 0.3)
    visitor_time = SimTimeTuple(hours=tuple(range(15, 20)), days=tuple(globals.numpy_rng.randint(0, 365, 12)))
    apartment = None

class Home(BaseLocation[HomeState]):
    """Class that implements a standard Home location. """
    state_type = HomeState

    def sync(self, sim_time: SimTime) -> None:
        super().sync(sim_time)
        self._state.social_gathering_event = sim_time in self._state.visitor_time

    def update_rules(self, new_rule: LocationRule) -> None:
        pass
    
    """ Assign the home to an Apartment Complex """
    def update_apartment_complex(self, apt:Location):
        self._state.apartment = apt
        self._coordinates = apt.coordinates
    