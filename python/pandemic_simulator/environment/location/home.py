# Confidential, Copyright 2020, Sony Corporation of America, All rights reserved.

from dataclasses import dataclass

from ..interfaces import LocationState, Location, ContactRate, SimTime, SimTimeTuple, LocationRule, globals, BaseLocation

__all__ = ['Home', 'HomeState']


@dataclass
class HomeState(LocationState):
    contact_rate: ContactRate = ContactRate(0, 1, 0, 0.5, 0.3, 0.3)
    visitor_time = SimTimeTuple(hours=tuple(range(15, 20)), days=tuple(globals.numpy_rng.randint(0, 365, 12)))
    apartment = None
    elevator_time = 1 # 1 minute for elevator

class Home(BaseLocation[HomeState]):
    """Class that implements a standard Home location. """
    state_type = HomeState
    cache = []S
    def sync(self, sim_time: SimTime) -> None:
        super().sync(sim_time)
        self._state.social_gathering_event = sim_time in self._state.visitor_time

    def update_rules(self, new_rule: LocationRule) -> None:
        pass
    
    def update_apartment_complex(self, apt:Location):
        self._state.apartment = apt
    
    def process_apartment(self, start_min: int):
        if self._state.apartment is not None:
            #do contact for apartment here
